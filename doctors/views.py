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
from .models import User
from .serializers import UserSerializer
from .documents import UserDocument
from django_ratelimit.decorators import ratelimit
from django.db import OperationalError, transaction
from elasticsearch.helpers import bulk
from circuitbreaker import circuit
import logging
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Check for required environment variables
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY or not OPENROUTER_API_KEY.startswith('sk-or-v1-'):
    logger.error("Invalid OpenRouter API key format")
    raise EnvironmentError("Invalid OpenRouter API key format")

ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200")

# Initialize OpenAI client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)


# System prompt for the medical assistant
SYSTEM_PROMPT = """You are a medical assistant for Doctomed.ch. Be realistic and natural. Follow these rules strictly:
- DONOT provide medical diagnosis.
- Guide the patient effectively and concisely if asked for some specific symtoms, or any health related issue.
- DONOT give doctor recommendations from other websites
- Include the JSON block and the recommendation message ONLY when 'questioning_complete' is true.

1. Direct Requests (when users ask something to find/recommend/search doctors):
- Extract: 
```json
{
  "specialist_type": "string",
  "city": "string or null",
  "country": "string or null",
  "language": "string or null",
  "telehealth_appropriate": true/false,
  "urgent": true/false,
  "questioning_complete": true/false
}
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
  "questioning_complete": true
}
```
NOTE:
- MUST mention country if only city is given in both cases of JSON either Direct Requests or Symptom Analysis
- IMPORTANT: Always include the JSON block at the end when recommending a specialist. Example response:
  Here are the best psychiatrists recommended for you:
  ```json
  {"specialist_type": "psychiatrist", ...}
- Add "Here are the best {specialist_type}s recommended for you:\n\n" before returning JSON
- This JSON must be machine-parsable and should be at the END of your helpful response.
"""



def optimize_llm_call():
    return client.chat.completions.create(
        model="deepseek/deepseek-chat:free",
        messages=messages,
        temperature=0.2,
        max_tokens=150,
        top_p=0.9,
        frequency_penalty=0.5,
        presence_penalty=0.5
    )
import urllib3

# Elasticsearch
es_pool = urllib3.HTTPSConnectionPool(
    host='es-cluster',
    maxsize=100,
    block=True,
    timeout=60
)

REDIS_HOST = os.environ.get('REDISHOST')
REDIS_PASSWORD = os.environ.get('REDISPASSWORD')
REDIS_PORT = os.environ.get('REDISPORT')

redis_pool = redis.ConnectionPool(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    db=0,
    max_connections=1000,
    socket_timeout=5
)


class ConversationManager:
    def __init__(self):
        self.redis = redis.Redis(connection_pool=redis_pool)
        self.expiration = 86400  # 24 hours

    def save_conversation(self, user_id, dialogue, symptoms):
        """Store conversation data in Redis with proper structure"""
        data = {
            'dialogue': dialogue,
            'symptoms': symptoms,
            'updated_at': time.time()
        }
        self.redis.setex(f"conversation:{user_id}", self.expiration, json.dumps(data))

    def get_conversation(self, user_id):
        """Retrieve complete conversation history"""
        data = self.redis.get(f"conversation:{user_id}")
        if data:
            decoded = json.loads(data)
            return decoded.get('dialogue', []), decoded.get('symptoms', [])
        return [], []

    def update_conversation(self, user_id, role, content, symptoms=None):
        """Append to existing conversation"""
        dialogue, existing_symptoms = self.get_conversation(user_id)
        dialogue.append({"role": role, "content": content})

        if symptoms is not None:
            existing_symptoms.extend(symptoms)

        self.save_conversation(user_id, dialogue, existing_symptoms)
        return dialogue

async def handle_message(user_message):
    # Process message async
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(
            pool,
            lambda: requests.post(API_ENDPOINT, json=user_message)
        )


@ratelimit(key='user', rate='100/m', block=True)
@csrf_exempt
def chatbot(request):
    if request.method != "POST":
        return JsonResponse({"response": "Invalid request method."}, status=405)

    try:
        data = json.loads(request.body)
        user_id = data.get("user_id", "default")
        user_message = data.get("message", "")
        user_country = data.get("country")
        user_city = data.get("city")
        # user_lat = data.get("latitude")
        # user_lng = data.get("longitude")
        preferred_language = data.get("language")
        telehealth_preference = data.get("telehealth_appropriate", False)
        patient_age = data.get("age")
        patient_gender = data.get("gender")

        cm = ConversationManager()

        # Get or initialize conversation from Redis
        dialogue, symptoms = cm.get_conversation(user_id)

        # Initialize if empty
        if not dialogue:
            dialogue = [{"role": "system", "content": SYSTEM_PROMPT}]
            symptoms = []
            cm.save_conversation(user_id, dialogue, symptoms)

        # Add user message to conversation
        dialogue = cm.update_conversation(user_id, "user", user_message)

        logger.info(f"User message: {user_message}")

        # Retry mechanism for API calls
        max_retries = 3
        retry_count = 0
        while retry_count < max_retries:
            try:
                # Get response from LLM
                completion = client.chat.completions.create(
                    model="deepseek/deepseek-chat:free",
                    messages=dialogue
                )

                # Get the bot's reply
                bot_reply = completion.choices[0].message.content
                logger.info(f"Raw bot reply: {bot_reply}")
                break
            except Exception as e:
                retry_count += 1
                logger.warning(f"API call failed (attempt {retry_count}/{max_retries}): {str(e)}")
                if retry_count >= max_retries:
                    return JsonResponse(
                        {"response": "Sorry, I'm having trouble connecting to the service. Please try again later."},
                        status=503)
                time.sleep(1)  # Wait before retrying

        # Extract JSON data from the response
        json_data = extract_json_from_response(bot_reply)
        logger.info(f"Extracted JSON data: {json_data}")

        # Create a response without JSON
        clean_reply = remove_json_from_reply(bot_reply)

        # Initialize the final response
        final_response = clean_reply
        specialists = []
        specialist_type = "General Practitioner"  # Default value
        symptoms_provided = False

        if json_data:
            # Only include recommendations if symptoms are provided
            symptoms = json_data.get("symptoms", [])

            specialist_type = json_data.get("specialist_type", "General Practitioner").strip().lower()

            original_specialist_type = specialist_type

            symptoms_provided = bool(symptoms)

            if symptoms:
                # Update conversation with new symptoms using Redis manager
                dialogue = cm.update_conversation(
                    user_id=user_id,
                    role="system",
                    content="",
                    symptoms=symptoms
                )
                logger.info(f"Updated symptoms for user {user_id}: {symptoms}")


            if specialist_type:
                telehealth_required = json_data.get("telehealth_appropriate", False)
                if telehealth_preference:
                    telehealth_required = True

                logger.info(f"Searching for specialist type: {specialist_type}")

                country = json_data.get('country') or user_country
                city = json_data.get('city') or user_city

                # Find doctors
                specialists = find_doctors_with_elasticsearch(
                    specialist_type=json_data.get('specialist_type'),
                    country=country,
                    city=city,
                    language=json_data.get('language'),
                    telehealth_required=json_data.get('telehealth_appropriate', False)
                )

                logger.info(f"Found specialists: {len(specialists) if specialists else 0}")

                if not specialists:
                    specialists = find_doctors_with_elasticsearch(
                        specialist_type=json_data.get('specialist_type'),
                        country=None,
                        city=None,
                        language=json_data.get('language'),
                        telehealth_required=json_data.get('telehealth_appropriate', False)
                    )

                # If no specialists found and GP is appropriate, try finding GPs
                gp_fallback_used = False
                if not specialists and json_data.get("gp_appropriate", True):
                    logger.info("No specialists found, searching for GPs")
                    gp_fallback_used = True

                    gp_country = json_data.get('country') or user_country
                    gp_city = json_data.get('city') or user_city

                    gp_specialists = find_doctors_with_elasticsearch(
                        "General Practitioner",
                        country=gp_country,
                        city=gp_city,
                        language=json_data.get('language'),
                        telehealth_required=json_data.get('telehealth_appropriate', False)
                    )

                    if not gp_specialists:
                        gp_specialists = find_doctors_with_elasticsearch(
                            "General Practitioner",
                            country=None,
                            city=None,
                            language=json_data.get('language'),
                            telehealth_required=json_data.get('telehealth_appropriate', False)
                        )

                    specialists = gp_specialists

                # Modify response message if we used GP fallback
                if gp_fallback_used:
                    if specialists:
                        clean_reply = f"We couldn't find any {original_specialist_type}s matching your criteria. Recommending best general practitioner for initial assessment:"
                    else:
                        clean_reply = f"We couldn't find any {original_specialist_type}s or General Practitioners matching your criteria. Please try a different search."


        # Add the bot's reply to the conversation history using Redis
        dialogue = cm.update_conversation(user_id, "assistant", final_response)

        # Count user messages from Redis-managed conversation
        _, current_symptoms = cm.get_conversation(user_id)
        symptoms_count = len(current_symptoms)
        symptoms_provided = bool(json_data and json_data.get("symptoms"))

        # Enforce minimum of 2 symptom interactions
        if symptoms_provided and symptoms_count < 2:
            if json_data:
                json_data["questioning_complete"] = False
                logger.info(f"Delaying recommendations - only {symptoms_count} symptom interactions")
            specialists = []  # Clear any specialists to prevent early recommendations

        # Later, when preparing the response:
        response_data = {
            "response": clean_reply,
            "recommendations": None
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
        return JsonResponse({"response": "Invalid JSON in request body."}, status=400)
    except Exception as e:
        logger.error(f"Error in chatbot endpoint: {str(e)}", exc_info=True)
        return JsonResponse({"response": "I encountered an error processing your request. Please try again."},
                            status=500)

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

    return clean_reply


def extract_json_from_response(response):
    """More robust JSON extraction that handles incomplete responses"""
    try:
        if not response:
            return None

        # Look for specific patterns that indicate specialist search
        specialist_search_patterns = [
            "Here are the best", "recommended for you", "specialist"
        ]

        is_specialist_search = any(pattern in response for pattern in specialist_search_patterns)

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

        # If no JSON found but this appears to be a specialist search, create default JSON
        if not json_str and is_specialist_search:
            # Extract specialist type from the response text
            specialist_type = None
            if "best" in response:
                text_after_best = response.split("best")[1].strip()
                # Take first word after "best" as specialist type
                if text_after_best:
                    specialist_type = text_after_best.split()[0].rstrip('s:,.')

            if specialist_type:
                return {
                    "specialist_type": specialist_type,
                    "city": None,
                    "country": None,
                    "telehealth_appropriate": False,
                    "urgent": False,
                    "questioning_complete": True
                }

        # If still no JSON found, scan the entire response for valid JSON
        if not json_str:
            decoder = json.JSONDecoder()
            idx = 0
            while idx < len(response):
                try:
                    obj, idx = decoder.raw_decode(response[idx:])
                    return obj
                except json.JSONDecodeError:
                    idx += 1
            return None

        return json.loads(json_str)
    except Exception as e:
        logger.warning(f"JSON extraction failed: {str(e)}")
        return None

def create_default_json_response():
    """Create a default JSON response when extraction fails"""
    return {
        "specialist_type": "General Practitioner",
        "severity": "medium",
        "urgent": False,
        "gp_appropriate": True,
        "telehealth_appropriate": True
    }

def optimize_es_query():
    return {
        "query": {
            "bool": {
                "must": [
                    {"term": {"speciality.raw": specialties}},
                    {"term": {"city.raw": city}},
                    {"range": {"average_rating": {"gte": 4}}}
                ],
                "should": [
                    {"term": {"patient_status": patient_status}},
                    {"term": {"languages": language}}
                ]
            }
        },
        "rescore": {
            "window_size": 50,
            "query": {
                "rescore_query": {
                    "score_mode": "multiply",
                    "query_weight": 0.7,
                    "rescore_query_weight": 1.2,
                    "script_score": {
                        "script": {
                            "source": "doc['availability'].value ? 1.1 : 0.9"
                        }
                    }
                }
            }
        }
    }


def build_elasticsearch_query(specialist_type, country=None, city=None,
                              language=None, telehealth_required=False):
    """Build Elasticsearch query with improved specialty matching"""
    bool_query = {
        "must": [],
        "should": [],  # Add this line to initialize 'should'
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
                            "specialties.name^5",
                            "specialties.name.edge_ngram^3"
                        ],
                        "fuzziness": "AUTO",
                        "operator": "or",
                        "type": "best_fields"
                    }
                }
            }
        }
        bool_query["must"].append(specialty_query)

    # Location filter
    if country:
        clean_country = country.strip().lower()
        country_query = {
            "nested": {
                "path": "country",
                "query": {
                    "bool": {
                        "should": [
                            {"term": {"country.name.exact": {"value": clean_country, "boost": 3}}},
                            {"match": {"country.name": {"query": clean_country, "fuzziness": 2, "boost": 1}}}
                        ]
                    }
                }
            }
        }
        bool_query["must"].append(country_query)
        logger.info(f"Added country filter: {clean_country}")

    if city:
        clean_city = city.strip().lower()
        city_query = {
            "nested": {
                "path": "city",
                "query": {
                    "bool": {
                        "should": [
                            {"term": {"city.name.exact": {"value": clean_city, "boost": 3}}},
                            {"match": {"city.name": {"query": clean_city, "fuzziness": "AUTO", "boost": 1}}}
                        ]
                    }
                }
            }
        }
        bool_query["must"].append(city_query)
        logger.info(f"Added city filter: {clean_city}")

        # Language filter
    if language:
        clean_lang = language.strip().lower()
        # Use the 'exact' subfield for language
        language_query = {
            "term": {"languages.exact": clean_lang}
        }
        bool_query["must"].append(language_query)
        logger.info(f"Added language filter: {clean_lang}")

    # Telehealth filter
    if telehealth_required is True:
        # Hard filter: only show doctors offering telehealth
        bool_query["must"].append({
            "term": {"is_online": True}
        })
    else:
        # Soft boost: prefer but don't require
        bool_query["should"].append({
            "term": {
                "is_online": {
                    "value": True,
                    "boost": 1.5
                }
            }
        })

    # Patient status: always boost, but not filter
    bool_query["should"].append({
        "term": {
            "patient_status": {
                "value": "1",
                "boost": 2.0
            }
        }
    })

    return bool_query


@circuit(failure_threshold=5, recovery_timeout=60)
def find_doctors_with_elasticsearch(specialist_type, country=None, city=None,
                                    language=None, telehealth_required=False):
    try:
        logger.info(
            f"Searching for doctors with: {specialist_type}, country={country}, city={city}, {language}, {telehealth_required}")
        search = UserDocument.search()


        # Initialize a bool query
        bool_query = build_elasticsearch_query(
            specialist_type,
            country=country,
            city=city,
            language=language,
            telehealth_required=telehealth_required
        )

        # Log the actual query being sent to Elasticsearch
        logger.info(f"Elasticsearch query: {json.dumps(bool_query)}")

        # Execute the search with appropriate sorting
        response = search.query({"bool": bool_query}) \
                       .sort('_score', {'average_rating': {'order': 'desc'}}) \
            [:8].execute()

        doctors = [hit.to_dict() for hit in response]


        logger.info(f"Found {len(doctors)} doctors via Elasticsearch")
        if len(doctors) == 0:
            # If no doctors found, log the raw response for debugging
            logger.warning(f"No doctors found. Raw Elasticsearch response: {response.to_dict()}")

        # Fallback logic remains the same...

        return doctors

    except Exception as e:

        logger.error(f"Search error: {str(e)}", exc_info=True)

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
        title = doctor.get('title', '').strip()  # Get title and remove extra spaces
        first_name = doctor.get('first_name', '').strip()
        last_name = doctor.get('last_name', '').strip()

        if title:
            result += f"{i}. {title} {first_name} {last_name}\n"  # Show title if it exists
        else:
            result += f"{i}. {first_name} {last_name}\n"  # Show only name if no title

        if doctor.get('specialties'):
            if isinstance(doctor['specialties'], dict):
                # Handle nested specialty object
                result += f"\n   Specialty: {doctor['specialties'].get('name', '')}"
            else:
                result += f"\n   Specialty: {doctor['specialties']}"

        # Language display fix
        if doctor.get('languages'):  # Note plural field name
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


@csrf_exempt
def symptom_analysis(request):
    """Endpoint to analyze symptoms without conversation context"""
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method."}, status=405)

    try:
        data = json.loads(request.body)
        symptoms = data.get("symptoms", [])
        country = data.get("country")
        city = data.get("city")
        patient_age = data.get("age")
        language = data.get("language"),
        patient_gender = data.get("gender")
        medical_history = data.get("medical_history")

        if not symptoms:
            return JsonResponse({"error": "Please provide symptoms for analysis."}, status=400)

        # Use LLM to analyze symptoms and suggest specialist
        specialist_response = analyze_symptoms_with_llm(
            symptoms,
            patient_age,
            patient_gender,
            medical_history
        )

        # Find matching doctors with Elasticsearch
        specialists = find_doctors_with_elasticsearch(
            specialist_response["specialist_type"],
            country=country,
            city=city,
            language=language,
            telehealth_required=False
        )

        return JsonResponse({
            "analysis": specialist_response,
            "specialists": specialists[:3]  # Limit to 3 specialists
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON in request body."}, status=400)
    except Exception as e:
        logger.error(f"Error in symptom analysis: {str(e)}", exc_info=True)
        return JsonResponse({"error": "An error occurred during symptom analysis."}, status=500)


def analyze_symptoms_with_llm(symptoms, patient_age=None, patient_gender=None, medical_history=None):
    """
    Use LLM to analyze symptoms and recommend specialist type with improved error handling
    """
    # Convert symptoms list to text if it's a list
    if isinstance(symptoms, list):
        symptoms_text = ", ".join(symptoms)
    else:
        symptoms_text = symptoms

    # Build context with available patient information
    context = f"Symptoms: {symptoms_text}\n"
    if patient_age:
        context += f"Patient age: {patient_age}\n"
    if patient_gender:
        context += f"Patient gender: {patient_gender}\n"
    if medical_history:
        context += f"Medical history: {medical_history}\n"

    prompt = f"""You are a medical specialist advisor for a Swiss healthcare website. 
    Analyze the following patient information and determine the most appropriate medical specialist type:

    {context}

    Based on the available information, determine:
    1. The most appropriate medical specialist type
    2. The urgency level of the situation
    3. Whether this could be handled by a general practitioner
    4. If telehealth would be appropriate for an initial consultation

    Provide a JSON response with the following format:
    {{
      "specialist_type": "the most appropriate specialist type",
      "severity": "low/medium/high",
      "urgent": true/false,
      "gp_appropriate": true/false,
      "telehealth_appropriate": true/false,
      "explanation": "brief explanation of your recommendation",
      "differential_specialties": ["other possible specialist types"]
    }}

    Only return the JSON object, nothing else.
    """

    # Retry mechanism
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model="deepseek/deepseek-chat:free",
                temperature=0.2,
                messages=[
                    {"role": "system",
                     "content": "You are a medical specialist advisor for a Swiss healthcare website."},
                    {"role": "user", "content": prompt}
                ]
            )

            response = completion.choices[0].message.content
            logger.info(f"Symptom analysis raw response: {response}")

            # Handle case when LLM wraps JSON in code block
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()

            # Try to parse the JSON response
            try:
                result = json.loads(response)
                return result
            except json.JSONDecodeError:
                # Fallback: if JSON parsing fails, return a default
                logger.warning("Failed to parse JSON from symptom analysis, using default")
                return create_default_specialist_response()

            break
        except Exception as e:
            retry_count += 1
            logger.warning(f"LLM API call failed (attempt {retry_count}/{max_retries}): {str(e)}")
            if retry_count >= max_retries:
                return create_default_specialist_response()
            time.sleep(1)  # Wait before retrying

    return create_default_specialist_response()


def create_default_specialist_response():
    """Create a default specialist response when API or parsing fails"""
    return {
        "specialist_type": None,
        "severity": "medium",
        "urgent": False,
        "gp_appropriate": True,
        "telehealth_appropriate": True,
        "explanation": "Unable to determine specific specialist. Recommending general practitioner for initial assessment.",
        "differential_specialties": ["Internal Medicine"]
    }


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
        batch_size = 200  # Reduced from 500
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
                        User.objects.first().pk  # Simple query to maintain connection

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