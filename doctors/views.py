import os
import json
import redis
import re
from django.core.cache import cache
import mysql.connector
from openai import OpenAI
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from elasticsearch.exceptions import ConnectionError
from dotenv import load_dotenv
from .models import *
from .serializers import UserSerializer
from .documents import UserDocument
from django_ratelimit.decorators import ratelimit
from django.db import OperationalError, transaction
from elasticsearch.helpers import bulk
from circuitbreaker import circuit
from .laravel_encryption import encrypt_laravel_style
from json import JSONDecodeError
from django.core.cache import cache
import logging
import time
import msgpack

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

INFOMANIAK_API_KEY = os.getenv("INFOMANIAK_API_KEY")

if not INFOMANIAK_API_KEY:
    logger.error("API key is missing")
    raise EnvironmentError("Invalid INFOMANIAK_API_KEY API key")

ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200")

# Initialize OpenAI client
client = OpenAI(
    base_url="https://api.infomaniak.com/1/ai/104209/openai",
    api_key=INFOMANIAK_API_KEY,
    timeout=15.0,
)


# System prompt for the medical assistant
SYSTEM_PROMPT = """You are an AI medical assistant for Doctomed.ch, operating under Swiss healthcare regulations (FADP/GDPR). Follow these rules strictly:

Role & Compliance:
1. Maintain HIPAA-level data privacy for all interactions
2. Adhere to SwissMedic guidelines for healthcare recommendations.
3. If asked about anything unrelated to the medical field, dont answer that just tell that what you can do for them.


Strict Location Handling Rules:
1. If user asks about their location/city/country/address:
   - respond with their registered location {patient_city}, {patient_country} only when asked about patients own location.
   - NEVER ask for location confirmation, When {patient_city}, {patient_country} are available
     
Location Data Sources:
   - Always use patient_city from: {patient_city}
   - Always use patient_country from: {patient_country}
   

3. If no location exists:
   - Respond: "No location registered. Please update your profile first." 

Strict Prohibitions:
- NEVER provide medical diagnosis or possible causes
- NEVER list medical tests or treatment options
- NEVER explain symptoms or conditions
- NEVER return JSON unless recommending a specialist_type
- ALWAYS RETURN RESPONSES AS TEXT, NEVER USE NUMERIC CODES

Structured Data Extraction (if given by user):
1. Direct Requests (when users ask something to find/recommend/search doctors or writes specialist name):
- Extract: 
```json
{
  "specialist_type": "string",
  "city": "string or null",
  "country": "string or null",
  "language": "string or null",
  "telehealth_appropriate": true/false,
  "urgent": true/false,
  "questioning_complete": true
}
- Always return questioning_complete true for Direct Requests.
- if country, city and telehealth_appropriate isnt mention just keep it null and false, dont ask questions for it.
- Maintain conversation context

2. Symptom Analysis:
- Only ask about symptoms if user describes health issues
- Ask only ONE targeted question per response
- After 2-3 questions, provide:

```json
{
  "symptoms": ["list", "of", "identified", "symptoms"],
  "city": "string or null",
  "country": "string or null",
  "language": "string or null",
  "specialist_type": "most appropriate specialist type",
  "gp_appropriate": true/false,
  "telehealth_appropriate": true/false,
  "urgent": true/false,
  "questioning_complete": true/false
}
```
NOTE:
- ONLY return 'telehealth_appropriate': True, when user asks for it.
- MUST mention country if only city is given in both cases of JSON either Direct Requests or Symptom Analysis
- IMPORTANT: Always include the JSON block (not in number form) at the end when recommending a specialist. Example response:
- Here are the best {specialist_type}s recommended for you:\n\n"
  ```json
  {"specialist_type": "psychiatrist", ...}
- Add "Here are the best {specialist_type}s recommended for you:\n\n" before returning JSON
- This JSON must be machine-parsable and should be at the END of your helpful response.
"""



REDIS_HOST = os.environ.get('REDISHOST')
REDIS_PASSWORD = os.environ.get('REDISPASSWORD')
REDIS_PORT = os.environ.get('REDISPORT')

redis_pool = redis.ConnectionPool(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    db=0,
    max_connections=1000,
    socket_timeout=15
)


class ConversationManager:
    def __init__(self):
        self.redis = redis.Redis(connection_pool=redis_pool)
        self.expiration = 86400

    def save_conversation(self, patient_id, dialogue, symptoms):
        key = f"conversation:{str(patient_id)}"
        try:
            data = msgpack.packb({
                'dialogue': dialogue,
                'symptoms': symptoms,
                'updated_at': time.time()
            })
            self.redis.setex(key, self.expiration, data)
        except Exception as e:
            logger.error(f"Error saving conversation: {str(e)}")

    def get_conversation(self, patient_id):
        key = f"conversation:{str(patient_id)}"
        try:
            data = self.redis.get(key)
            if not data:
                return [], []

            try:
                decoded = msgpack.unpackb(data, raw=False)
                return decoded.get('dialogue', []), decoded.get('symptoms', [])
            except msgpack.exceptions.ExtraData:

                try:
                    decoded = json.loads(data)
                    return decoded.get('dialogue', []), decoded.get('symptoms', [])
                except json.JSONDecodeError:
                    return [], []

        except Exception as e:
            logger.error(f"Error decoding conversation data: {str(e)}")
            return [], []

    def update_conversation(self, patient_id, role, content, symptoms=None):
        """Append to existing conversation"""
        dialogue, existing_symptoms = self.get_conversation(patient_id)
        dialogue.append({"role": role, "content": content})

        if symptoms is not None:
            existing_symptoms.extend(symptoms)

        self.save_conversation(patient_id, dialogue, existing_symptoms)
        return dialogue

    def reset_conversation(self, patient_id):
        """Reset conversation to initial state with system prompt"""
        logger.info(f"Executing reset_conversation for patient: {patient_id}")

        system_content = SYSTEM_PROMPT

        try:
            patient_location = get_patient_location(patient_id) or {}
            patient_city = patient_location.get('city')
            patient_country = patient_location.get('country')

            if patient_city and patient_country:
                system_content = SYSTEM_PROMPT \
                    .replace('{patient_city}', patient_city) \
                    .replace('{patient_country}', patient_country)

                logger.info(f"Initialized system prompt with location: {patient_city}, {patient_country}")
            else:
                system_content = SYSTEM_PROMPT.replace(
                    "Location information is stored in your profile",
                    "No location registered in your profile"
                )

        except Exception as e:
            logger.error(f"Failed to add location during reset: {str(e)}", exc_info=True)

        dialogue = [{
            "role": "system",
            "content": system_content
        }]

        symptoms = []

        self.save_conversation(patient_id, dialogue, symptoms)

        new_dialogue, _ = self.get_conversation(patient_id)
        logger.info(f"Reset complete. New dialogue length: {len(new_dialogue)}")

        return dialogue

    def should_reset_conversation(self, user_message: str, patient_id: str) -> bool:
        """Use LLM to detect conversation reset intent"""
        cache_key = f"reset_check:{hash(user_message.lower())}"
        logger.info(f"Checking if message requires reset: '{user_message}'")

        if cached := cache.get(cache_key):
            return cached

        try:
            dialogue, _ = self.get_conversation(patient_id)

            context_messages = []
            for msg in dialogue[-3:]:
                if msg['role'] in ['user', 'assistant']:
                    context_messages.append(f"{msg['role'].upper()}: {msg['content']}")

            context_text = "\n".join(context_messages) if context_messages else "No previous conversation"

            response = client.chat.completions.create(
                model="llama3",
                messages=[{
                    "role": "system",
                    "content": """Analyze if the user's message indicates a desire to start a completely new conversation.

                    Given the PREVIOUS CONVERSATION and the NEW MESSAGE, determine if this is a topic change or reset.

                    Return YES ONLY if:
                    1. The user start talking about something completely different. 
                    2. The user suddenly introduces a topic unrelated to the previous conversation (e.g., a new condition, different body system, different specialist).
                    3. When user say greetings 

                    Return NO if:
                    1. The message is a follow-up to a previous question
                    2. The message provides additional information about a medical concern
                    3. The message continue asking  about previous doctors, specialists, or medical services
                    4. The message is answering a question that was previously asked by the assistant

                    IMPORTANT: Medical chatbots should maintain conversation context. Only reset when truly necessary.
                    RESPOND WITH EXACTLY 'YES' OR 'NO', NOTHING ELSE."""
                }, {
                    "role": "user",
                    "content": f"PREVIOUS CONVERSATION:\n{context_text}\n\nNEW MESSAGE:\n{user_message}\n\nShould the conversation be reset?"
                }],
                max_tokens=10,
                timeout=10.0
            )
            result_text = response.choices[0].message.content.strip().upper()
            result = result_text == "YES"

            logger.info(f"LLM reset detection response: '{result_text}' → Reset: {result}")

            cache.set(cache_key, result, 3600)
            return result
        except Exception as e:
            logger.error(f"Error in reset detection: {str(e)}", exc_info=True)
            return False

async def handle_message(user_message):
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(
            pool,
            lambda: requests.post(API_ENDPOINT, json=user_message)
        )


@ratelimit(key='user', rate='100/m', block=True)
@csrf_exempt
def chatbot(request):
    start_time = time.time()
    if request.method != "POST":
        return JsonResponse({"response": "Invalid request method."}, status=405)
    logger.info(f"Request headers: {request.headers}")
    logger.info(f"Request body: {request.body}")

    cm = ConversationManager()
    patient_id = None
    dialogue = []
    bot_reply = None
    json_data = None
    clean_reply = None
    logger.info(f"Redis connection status: {cm.redis.ping()}")

    try:
        if request.user.is_authenticated:
            patient_id = str(request.user.id)
        else:
            data = json.loads(request.body)
            patient_id = str(data.get("patient_id"))
            if not patient_id:
                return JsonResponse({"response": "Authentication or patient_id required"}, status=401)
    except Exception as e:
        logger.error(f"Auth error: {str(e)}")
        return JsonResponse({"response": "Authentication failed"}, status=401)

    try:

        timing = {}
        t0 = time.time()

        data = json.loads(request.body)
        patient_id = data.get("patient_id")
        if not patient_id:
            return JsonResponse({"response": "Patient ID is required."}, status=400)
        user_message = data.get("message", "")

        logger.info(f"Checking reset intent for message: '{user_message}'")
        t0 = time.time()
        should_reset = cm.should_reset_conversation(user_message, patient_id)
        timing['reset_check'] = time.time() - t0
        logger.info(f"Reset decision: {should_reset}")

        if should_reset:
            logger.info(f"LLM detected reset intent: {user_message}")
            dialogue = cm.reset_conversation(patient_id)
        else:
            dialogue, symptoms = cm.get_conversation(patient_id)

        country = data.get("country")
        city = data.get("city")
        user_lat = data.get("latitude")
        user_lng = data.get("longitude")
        preferred_language = data.get("language")
        telehealth_preference = data.get("telehealth_appropriate", False)
        try:
            t0 = time.time()
            patient_location = get_patient_location(patient_id) or {}
            timing['location'] = time.time() - t0
        except Exception as e:
            logger.error(f"Error getting location: {str(e)}")
            patient_location = {}

        patient_city = patient_location.get('city')
        patient_country = patient_location.get('country')
        has_location = bool(patient_city and patient_country)

        dialogue, symptoms = cm.get_conversation(patient_id)
        logger.info(f"Initial dialogue length: {len(dialogue)}")

        # Initialize if empty
        if not dialogue or dialogue[0]['role'] != 'system':
            logger.warning("Resetting conversation with system prompt")
            dialogue = [{"role": "system", "content": SYSTEM_PROMPT}]
            symptoms = []
            cm.save_conversation(patient_id, dialogue, symptoms)

            if has_location:
                dialogue.append({
                    "role": "system",
                    "content": f"PATIENT LOCATION LOCK: {patient_city}, {patient_country}"
                })
                cm.save_conversation(patient_id, dialogue, symptoms)
                logger.info(f"Added location information to conversation: {patient_city}, {patient_country}")

        elif dialogue[0]['content'] != SYSTEM_PROMPT:
            logger.warning("Updating system prompt to latest version")
            dialogue[0]['content'] = SYSTEM_PROMPT
            cm.save_conversation(patient_id, dialogue, symptoms)

        dialogue = cm.update_conversation(patient_id, "user", user_message)

        logger.info(f"User message: {user_message}")

        max_retries = 2
        retry_count = 0
        base_delay = 0.3
        while retry_count < max_retries:
            try:
                completion = client.chat.completions.create(
                    model="llama3",
                    messages=dialogue,
                )

                bot_reply = completion.choices[0].message.content
                break
            except Exception as e:
                retry_count += 1
                logger.warning(f"API call failed (attempt {retry_count}/{max_retries}): {str(e)}")
                if retry_count >= max_retries:
                    return JsonResponse(
                        {"response": "Sorry, I'm having trouble connecting to the service. Please try again later."},
                        status=503)
                delay = base_delay * (2 ** retry_count) + random.uniform(0, 0.1)
                time.sleep(delay)

        if patient_city and patient_country and bot_reply:
            bot_reply = bot_reply.replace('{patient_city}', patient_city) \
                .replace('{patient_country}', patient_country) \
                .replace('{location}', f"{patient_city}, {patient_country}")

        clean_reply = remove_json_from_reply(bot_reply) if bot_reply else ""
        json_data = extract_json_from_response(bot_reply, dialogue, patient_id) if bot_reply else {}
        logger.info(f"Raw bot reply: {bot_reply}")
        logger.info(f"Extracted JSON data: {json_data}")

        final_response = clean_reply
        specialists = []
        symptoms_provided = False

        if not isinstance(json_data, dict):
            json_data = {}

        if json_data:
            if isinstance(json_data, dict):
                symptoms = json_data.get("symptoms", [])
                specialist_type = str(json_data.get("specialist_type") or "").strip().lower()
            else:
                symptoms = []
                specialist_type = ""
                json_data = None

            specialist_type = str(json_data.get("specialist_type") or "").strip().lower()
            original_specialist_type = specialist_type

            symptoms_provided = bool(symptoms)

            if symptoms:
                dialogue = cm.update_conversation(
                    patient_id=patient_id,
                    role="system",
                    content=SYSTEM_PROMPT,
                    symptoms=symptoms
                )
                logger.info(f"Updated symptoms for user {patient_id}: {symptoms}")


            if specialist_type:
                telehealth_required = json_data.get("telehealth_appropriate", False)
                if telehealth_preference:
                    telehealth_required = True

                logger.info(f"Searching for specialist type: {specialist_type}")

                country = json_data.get('country')
                city = json_data.get('city')

                location_source = "database" if patient_location else "user input"
                logger.info(f"Patient location - Valid: {bool(patient_city and patient_country)} City={patient_city or 'None'}, Country={patient_country or 'None'}")

                if "near me" in user_message.lower():
                    json_data.update({
                        'city': patient_city,
                        'country': patient_country,
                        'use_db_location': True
                    })

                    json_data['city'] = patient_city
                    json_data['country'] = patient_country
                    logger.info("Using database location for 'near me' request")


                    logger.info("Resetting location for 'near me' request")
                    logger.info(f"Final search location - City: {city or 'None'} "
                        f"(Source: {'user input' if json_data.get('city') else 'patient record'}), "
                        f"Country: {country or 'None'} "
                        f"(Source: {'user input' if json_data.get('country') else 'patient record'})")

                    # Specialist search logging
                logger.info(f"Initiating specialist search with parameters: "
                                f"Type={specialist_type}, City={city}, Country={country}, "
                                f"Telehealth={telehealth_required}")

                user_provided_location = (json_data.get('city') is not None) or (json_data.get('country') is not None)

                # First search parameters
                search_country = json_data.get('country')
                search_city = json_data.get('city')

                if not user_provided_location:
                    logger.info("No user-provided location - using patient location for initial search")
                    search_country = patient_country
                    search_city = patient_city
                # Find doctors
                specialists = find_doctors_with_elasticsearch(
                    specialist_type=json_data.get('specialist_type'),
                    country=search_country,
                    city=search_city,
                    language=json_data.get('language'),
                    telehealth_required=json_data.get('telehealth_appropriate', False),
                    patient_city=patient_city,
                    patient_country=patient_country
                )

                logger.info(f"Found specialists: {len(specialists) if specialists else 0}")

                if not specialists and not user_provided_location:
                    logger.info("Attempting locationless search since user didn't specify location")
                    specialists = find_doctors_with_elasticsearch(
                        specialist_type=json_data.get('specialist_type'),
                        country=None,
                        city=None,
                        language=json_data.get('language'),
                        telehealth_required=json_data.get('telehealth_appropriate', False),
                        patient_city=None,
                        patient_country=None
                    )
                    logger.info(f"Found specialists in locationless search: {len(specialists) if specialists else 0}")

                if not specialists:
                    no_specialists_prompt = (
                        f"We couldn't find any {original_specialist_type}s available on our website based on the user's criteria. "
                        f"Please provide a polite and very concise response that acknowledges this and maintains the conversation context. "
                        f"Dont use 'search' word"
                    )

                    try:
                        no_specialists_dialogue = [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_message},
                            {"role": "system", "content": no_specialists_prompt}
                        ]
                        logger.info(
                            f"Attempting to generate no specialists response with dialogue: {no_specialists_dialogue}")

                        no_specialists_completion = client.chat.completions.create(
                            model="llama3",
                            messages=no_specialists_dialogue
                        )

                        clean_reply = no_specialists_completion.choices[0].message.content
                        clean_reply = remove_json_from_reply(clean_reply)
                        logger.info(f"Successfully generated no specialists response: {clean_reply}")
                    except Exception as e:
                        # Improved error logging
                        logger.error(f"Failed to generate no specialists response: {str(e)}", exc_info=True)
                        clean_reply = f"I couldn't find any {original_specialist_type}s  available in our website matching your criteria."

        dialogue = cm.update_conversation(patient_id, "assistant", final_response)

        # Count user messages from Redis-managed conversation
        _, current_symptoms = cm.get_conversation(patient_id)
        symptoms_count = len(current_symptoms)
        symptoms_provided = bool(json_data and json_data.get("symptoms"))

        if symptoms_provided and symptoms_count < 2:
            if json_data:
                json_data["questioning_complete"] = False
                logger.info(f"Delaying recommendations - only {symptoms_count} symptom interactions")
            specialists = []

        response_data = {
            "response": clean_reply,
            "recommendations": None,
            "timing": timing
        }

        if (json_data and specialists and (json_data.get("questioning_complete", False)) and
                (symptoms_provided or not symptoms_provided)):

            response_data["recommendations"] = {
                "specialist_type": json_data["specialist_type"],
                "specialists": specialists[:10],
                "telehealth_appropriate": json_data.get("telehealth_appropriate", False),
                "severity": json_data.get("severity", "medium")
            }

        return JsonResponse(response_data)

    except json.JSONDecodeError:
        return JsonResponse({"response": "Invalid JSON"}, status=400)

    except Exception as e:
        logger.error(f"Error in chatbot endpoint: {str(e)}", exc_info=True)
        return JsonResponse({"response": "I encountered an error processing your request. Please try again."},
                            status=500)
    finally:
        for var in [dialogue, bot_reply, json_data, clean_reply, cm]:
            if var is not None:
                del var

        import gc
        gc.collect()


def remove_json_from_reply(bot_reply):
    """Remove JSON sections from the bot reply to create a clean response"""
    if "```json" in bot_reply:
        clean_reply = bot_reply.split("```json")[0].strip()
    elif "```" in bot_reply:
        parts = bot_reply.split("```")
        # Remove the JSON code block
        clean_parts = [parts[0]]
        for i in range(2, len(parts), 2):
            if i < len(parts):
                clean_parts.append(parts[i])
        clean_reply = "".join(clean_parts).strip()
    else:
        clean_reply = bot_reply

    clean_reply = re.sub(r"(?i)placeholder\s+JSON", "", clean_reply)
    clean_reply = re.sub(r"(?i)example\s+structure", "", clean_reply)

    return clean_reply


def extract_json_from_response(response, dialogue_context, patient_id):
    """More robust JSON extraction that handles incomplete responses"""
    try:
        if not response:
            return None
        default_city = None
        default_country = None

        specialist_search_patterns = [
            "Here are the best", "recommended for you", "specialist"
        ]

        is_specialist_search = any(pattern in response for pattern in specialist_search_patterns)

        # Search all messages for location lock
        patient_location = get_patient_location(patient_id) or {}
        default_city = patient_location.get('city')
        default_country = patient_location.get('country')

        json_data = {}
        if default_city and default_country:
            json_data.setdefault('city', default_city)
            json_data.setdefault('country', default_country)

        try:
            parsed_json = json.loads(response)
            if isinstance(parsed_json, dict):
                return parsed_json
        except JSONDecodeError:
            pass

            # Try to find JSON in code blocks
        json_str = None
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            parts = response.split("```")
            for part in parts[1::2]:
                stripped = part.strip()
                if stripped.startswith('{'):
                    json_str = stripped
                    break

        if not json_str and is_specialist_search:
            specialist_type = None
            match = re.search(r"best (\w+)s? recommended", response, re.IGNORECASE)
            if match:
                specialist_type = match.group(1).lower()

            if specialist_type:
                return {
                    "specialist_type": specialist_type,
                    "city": default_city,
                    "country": default_country,
                    "telehealth_appropriate": False,
                    "urgent": False,
                    "questioning_complete": True
                }

        if json_str:
            try:
                parsed = json.loads(json_str)
                json_data.update(parsed)
                return json_data
            except JSONDecodeError:
                pas
        # Fallback: Scan entire response
        decoder = json.JSONDecoder()
        idx = 0
        while idx < len(response):
            try:
                obj, idx = decoder.raw_decode(response[idx:])
                json_data.update(obj)
                return json_data
            except JSONDecodeError:
                idx += 1
        return json_data or None

    except Exception as e:
        logger.warning(f"JSON extraction failed: {str(e)}")
        return None


PATIENT_LOCATION_CACHE_TTL = 3600


def get_patient_location(patient_id):
    """Retrieve patient's location from database with caching"""
    cache_key = f"patient_location:{patient_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        logger.info(f"Attempting to get location for patient ID: {patient_id}")
        if not patient_id.isdigit():
            logger.error(f"Invalid patient ID format: {patient_id}")
            return None

        patient = Patient.objects.get(id=int(patient_id))
        logger.info(f"Found patient {patient_id} in database")

        location = {
            'city': patient.city.name if patient.city else None,
            'country': patient.country.name if patient.country else None
        }

        cache.set(cache_key, location, PATIENT_LOCATION_CACHE_TTL)
        return location

    except Patient.DoesNotExist:
        logger.error(f"Patient {patient_id} not found in database")
        return None
    except Exception as e:
        logger.error(f"Critical error fetching patient location: {str(e)}", exc_info=True)
        return None


def build_elasticsearch_query(specialist_type, country=None, city=None,
                              language=None, telehealth_required=False,
                              patient_city=None, patient_country=None):
    """Build Elasticsearch query with improved specialty matching"""

    logger.info(f"Building query for {specialist_type} with fallback to patient location: "
                f"Patient City={patient_city or 'None'}, Patient Country={patient_country or 'None'}")

    final_city = (city if city is not None else patient_city)
    final_country = (country if country is not None else patient_country)

    # Convert to lowercase if values exist
    final_city = final_city.lower() if final_city else None
    final_country = final_country.lower() if final_country else None

    # Add debug logging
    logger.info(f"Final search location: {final_city}, {final_country}")
    bool_query = {
        "must": [],
        "should": [],
        "filter": []
    }

    # Specialty filter with improved handling for neurologists
    specialist_type_lower = specialist_type.lower()
    if specialist_type_lower in ["general practitioner", "family doctor", "gp"]:
        specialty_query = {
            "nested": {
                "path": "specialties",
                "query": {
                    "bool": {
                        "should": [
                            {"term": {"specialties.name.exact": "general practitioner"}},
                            {"term": {"specialties.name.exact": "general practitioner (gp)"}},
                            {"term": {"specialties.name.exact": "general internal medicine"}}
                        ],
                        "minimum_should_match": 1
                    }
                }
            }
        }
        bool_query["must"].append(specialty_query)

    else:
        # Clean and normalize input
        specialist_type_clean = specialist_type.lower()
        specialty_query = {
            "nested": {
                "path": "specialties",
                "query": {
                    "multi_match": {
                        "query": specialist_type_clean,
                        "fields": [
                            "specialties.name.exact^10",
                        ],
                        "fuzziness": 1,
                        "operator": "or",
                        "type": "best_fields"
                    }
                }
            }
        }
        bool_query["must"].append(specialty_query)


        # Country filter
    if final_country:
        bool_query["must"].append({
            "nested": {
                "path": "country",
                "query": {
                    "bool": {
                        "should": [
                            {"term": {"country.name.exact": final_country.lower()}},
                            {"match": {"country.name": final_country}}
                        ]
                    }
                }
            }
        })
    # City filter
    if final_city:
        bool_query["must"].append({
            "nested": {
                "path": "city",
                "query": {
                    "bool": {
                        "should": [
                            {"term": {"city.name.exact": final_city.lower()}},
                            {"match": {"city.name": final_city}}
                        ]
                    }
                }
            }
        })
    # Boost patient's location matches
    if patient_city and patient_city == final_city:
        bool_query["should"].append({
            "term": {"city.name.exact": patient_city.lower()},
            "boost": 2.0
        })

    if patient_country and patient_country == final_country:
        bool_query["should"].append({
            "term": {"country.name.exact": patient_country.lower()},
            "boost": 1.5
        })

    # Language filter
    if language:
        clean_lang = language.strip().lower()
        language_query = {
            "term": {"languages.exact": clean_lang}
        }
        bool_query["must"].append(language_query)
        logger.info(f"Added language filter: {clean_lang}")

    # Telehealth filter
    if telehealth_required is True:
        bool_query["must"].append({
            "term": {"is_online": True}
        })
    else:
        bool_query["should"].append({
            "term": {
                "is_online": {
                    "value": True,
                    "boost": 1.5
                }
            }
        })

    return bool_query


@circuit(failure_threshold=5, recovery_timeout=60)
def find_doctors_with_elasticsearch(specialist_type, country=None, city=None,
                                    language=None, telehealth_required=False,
                                    patient_city=None, patient_country=None):
    try:

        final_city = city or patient_city
        final_country = country or patient_country
        user_specified_location = city is not None or country is not None
        if user_specified_location:
            final_city = city
            final_country = country

        cache_key = f"doctors:{specialist_type}:{country}:{city}:{language}:" \
                    f"{telehealth_required}:{patient_city}:{patient_country}"

        # Try cache first
        if cached := cache.get(cache_key):
            logger.info(f"Cache hit for {cache_key}")
            return cached


        search = UserDocument.search()

        bool_query = build_elasticsearch_query(
            specialist_type=specialist_type,
            country=final_country,
            city=final_city,
            language=language,
            telehealth_required=telehealth_required,
            patient_city= patient_city,
            patient_country=patient_country
        )

        logger.debug(f"Elasticsearch query: {json.dumps(bool_query, indent=2)}")

        response = search.query({"bool": bool_query}) \
                       .sort('_score', {'average_rating': {'order': 'desc'}}) \
            [:8].execute()

        # Process results
        doctors = []
        for hit in response:
            try:
                doctor = hit.to_dict()
                doctor['encrypted_id'] = encrypt_laravel_style(str(doctor['id']))
                doctors.append(doctor)
            except Exception as e:
                logger.error(f"Error processing doctor {hit.meta.id}: {str(e)}")

        logger.info(f"Found {len(doctors)} doctors")
        cache.set(cache_key, doctors, 300)

        if len(doctors) == 0 and not user_specified_location:
            logger.warning(f"No doctors found. Raw Elasticsearch response: {response.to_dict()}")

            fallback_query = build_elasticsearch_query(
                specialist_type=specialist_type,
                country=None,
                city=None,
                language=language,
                telehealth_required=telehealth_required,
                patient_city=None,
                patient_country=None
            )

            logger.debug(f"Retrying with fallback query: {json.dumps(fallback_query, indent=2)}")

            response = search.query({"bool": fallback_query}) \
                           .sort('_score', {'average_rating': {'order': 'desc'}})[:8].execute()

            # Reprocess results
            doctors = []
            for hit in response:
                try:
                    doctor = hit.to_dict()
                    doctor['encrypted_id'] = encrypt_laravel_style(str(doctor['id']))
                    doctors.append(doctor)
                except Exception as e:
                    logger.error(f"Error processing fallback doctor {hit.meta.id}: {str(e)}")

            logger.info(f"Found {len(doctors)} doctors on fallback attempt")
            cache.set(cache_key, doctors, 300)

        return doctors
    except Exception as e:
        logger.error(f"Search failed: {str(e)}", exc_info=True)
        return []


def format_doctor_recommendations(doctors, is_urgent, telehealth_appropriate):
    """Format doctor recommendations into a user-friendly response"""

    if not doctors:
        return "I couldn't find any specialists matching your criteria. You might want to contact your primary care physician for a referral."


    urgent_message = ""
    if is_urgent:
        urgent_message = "⚠️ Based on your symptoms, this may require urgent attention. Please consider seeking immediate medical help if symptoms are severe. ⚠️\n\n"

    telehealth_message = ""
    if telehealth_appropriate:
        telehealth_message = "Your symptoms may be suitable for an initial online consultation. "

    result = f"{urgent_message}Here are some recommended doctors that might help with your symptoms:\n\n"

    for i, doctor in enumerate(doctors, 1):
        title = doctor.get('title', '').strip()
        first_name = doctor.get('first_name', '').strip()
        last_name = doctor.get('last_name', '').strip()

        if title:
            result += f"{i}. {title} {first_name} {last_name}\n"
        else:
            result += f"{i}. {first_name} {last_name}\n"

        if doctor.get('specialties'):
            if isinstance(doctor['specialties'], dict):
                # Handle nested specialty object
                result += f"\n   Specialty: {doctor['specialties'].get('name', '')}"
            else:
                result += f"\n   Specialty: {doctor['specialties']}"

        # Language display fix
        if doctor.get('languages'):
            if isinstance(doctor['languages'], list):
                result += f"\n   Languages: {', '.join(doctor['languages'])}"
            else:
                result += f"\n   Languages: {doctor['languages']}"

        location_parts = []
        if doctor.get('city'):
            if isinstance(doctor['city'], dict):
                location_parts.append(doctor['city'].get('name', ''))
            else:
                location_parts.append(doctor['city'])

        if doctor.get('country'):
            if isinstance(doctor['country'], dict):
                location_parts.append(doctor['country'].get('name', ''))
            else:
                location_parts.append(doctor['country'])

        if location_parts:
            result += f"   Location: {', '.join(filter(None, location_parts))}\n"

        # Rating
        if doctor.get('average_rating'):
            result += f"   Rating: {doctor['average_rating']}/5\n"
        elif doctor.get('rating'):
            result += f"   Rating: {doctor['rating']}/5\n"

        if doctor.get('service_type'):
            result += f"\n   Avg. Wait Time: {doctor['service_type']} days"

        if doctor.get('healthcare_professional_info'):
            result += f"\n   Info: {doctor['healthcare_professional_info']}"

        if doctor.get('is_online'):
            result += f"\n   ✓ Telehealth Available"

        if doctor.get('fees'):
            result += f"\n   Consultation Fees: {doctor['fees']}"

        if doctor.get('patient_status') == '1':
            doctor['tags'] = ['Accepting Patients']

        if doctor.get('web_url'):
            result += f"\n   Website: {doctor['web_url']}"




        result += "\n\n"
    if telehealth_appropriate:
        result += telehealth_message
        result += "Some of these doctors offer telehealth consultations, which may be suitable for your initial assessment."

    return result

# Add new function to create Elasticsearch index
@csrf_exempt
def initialize_elasticsearch(request):
    """Improved Elasticsearch initialization with resume capability"""
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    try:
        from elasticsearch_dsl.connections import connections
        es = connections.get_connection()

        # Check existing index
        existing_count = UserDocument.search().count()

        # Resume logic
        search_results = UserDocument.search().sort('-id')[:1].execute()
        if search_results:
            last_indexed = int(search_results[0].meta.id)
            users = User.objects.filter(id__gt=last_indexed)
            logger.info(f"Resuming indexing from ID {last_indexed}")
        else:
            users = User.objects.all()
        total_count = users.count()

        # Optimized batch processing
        batch_size = 200
        retry_count = 0
        max_retries = 3
        success = False

        while not success and retry_count < max_retries:
            try:
                with transaction.atomic():
                    for i in range(0, total_count, batch_size):
                        batch = users[i:i + batch_size].iterator(chunk_size=100)
                        bulk_actions = []

                        for user in batch:
                            try:
                                doc = UserDocument()
                                doc.meta.id = user.id
                                doc.prepare(user)
                                bulk_actions.append(doc.to_dict(include_meta=True))
                            except Exception as e:
                                logger.error(f"Skipping user {user.id}: {str(e)}")
                                continue

                        if bulk_actions:
                            # Use the bulk function from elasticsearch.helpers to perform bulk indexing
                            success, failed = bulk(es, bulk_actions)
                            if success:
                                logger.info(f"Successfully indexed {len(bulk_actions)} documents")
                            else:
                                logger.error(f"Failed to index some documents: {failed}")
                            time.sleep(0.1)

                        logger.info(f"Indexed {min(i+batch_size, total_count)}/{total_count} doctors")

                        # Keep connection alive
                        User.objects.first().pk

                success = True

            except (OperationalError, ConnectionError) as e:
                retry_count += 1
                logger.warning(f"Batch failed (attempt {retry_count}): {str(e)}")
                time.sleep(2 ** retry_count)

        return JsonResponse({
            "status": "success",
            "message": f"Indexed {total_count} doctors successfully."
        })

    except Exception as e:
        logger.error(f"Indexing error: {str(e)}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)

def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]