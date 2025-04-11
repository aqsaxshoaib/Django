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
from circuitbreaker import circuit
import logging
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Check for required environment variables
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    logger.error("OPENROUTER_API_KEY environment variable is not set")
    raise EnvironmentError("OPENROUTER_API_KEY is required")

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
- ALWAYS return JSON for any specialist type mentioned, even if the user just types a specialist name
- Extract: 
```json
{
  "specialist_type": "most appropriate specialist type",
  "telehealth_appropriate": true/false,
  "urgent": true/false,
  "questioning_complete": true
}

- Maintain conversation context

2. Symptom Analysis:
- Only ask about symptoms if user describes health issues
- Ask only ONE targeted question per response
- After 2-3 questions, provide:

```json
{
  "symptoms": ["list", "of", "identified", "symptoms"],
  "severity": "low/medium/high",
  "specialist_type": "most appropriate specialist type",
  "gp_appropriate": true/false,
  "telehealth_appropriate": true/false,
  "questioning_complete": true
}
```
NOTE:
ALWAYS include the JSON block at the end when  recommending specialist_type
Add "Here are the best {specialist_type}s recommended for you:\n\n" before returning JSON
This JSON must be machine-parsable and should be at the END of your helpful response.
"""



def optimize_llm_call():
    return client.chat.completions.create(
        model="deepseek-chat:free",
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


redis_pool = redis.ConnectionPool(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=6379,
    db=0,
    max_connections=1000  # Proper parameter name and value
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

def sanitize_input(text):
    # Remove any special characters except allowed medical terms
    return re.sub(r"[^a-zA-Z0-9\sà-üÀ-Ü\-'.,]", '', text)[:500]


from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine


def anonymize_text(text):
    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()

    results = analyzer.analyze(text=text, language='en')
    return anonymizer.anonymize(text, results).text

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
                    role="system",  # Or appropriate role for symptom tracking
                    content="",  # No message content needed for symptom updates
                    symptoms=symptoms
                )
                logger.info(f"Updated symptoms for user {user_id}: {symptoms}")


            if specialist_type:
                telehealth_required = json_data.get("telehealth_appropriate", False)
                if telehealth_preference:
                    telehealth_required = True

                logger.info(f"Searching for specialist type: {specialist_type}")

                # Find doctors
                specialists = find_doctors_with_elasticsearch(
                    specialist_type,
                    country=user_country,
                    city=user_city,
                    language=preferred_language,
                    telehealth_required=telehealth_preference,
                    use_vector_search=True  # Enable vector search
                )


                logger.info(f"Found specialists: {len(specialists) if specialists else 0}")

                # If no specialists found and GP is appropriate, try finding GPs
                gp_fallback_used = False
                if not specialists and json_data.get("gp_appropriate", True):
                    logger.info("No specialists found, searching for GPs")
                    gp_fallback_used = True
                    specialists = find_doctors_with_elasticsearch(
                        "General Practitioner",
                        country=user_country,
                        city=user_city,
                        language=preferred_language,
                        telehealth_required=telehealth_required
                    )

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
        clean_parts = [parts[0]]  # Start with the first part
        for i in range(2, len(parts), 2):  # Add the parts that are not code blocks
            if i < len(parts):
                clean_parts.append(parts[i])
        clean_reply = "".join(clean_parts).strip()
    else:
        clean_reply = bot_reply

    return clean_reply


def extract_json_from_response(response):
    """Robust JSON extraction with multiple fallbacks"""
    try:
        if not response:
            return None

        json_str = None
        # Try to find JSON in code blocks first
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            # Check all code blocks for JSON
            parts = response.split("```")
            for part in parts[1::2]:  # Check every code block
                if part.strip().startswith('{'):
                    json_str = part.strip()
                    break

        # If no code blocks, look for JSON-like structures
        if not json_str:
            start = response.find('{')
            end = response.rfind('}')
            if start != -1 and end != -1 and start < end:
                json_str = response[start:end+1].strip()

        if json_str:
            return json.loads(json_str)
        return None

    except Exception as e:
        logger.warning(f"JSON extraction failed: {str(e)}")
        return None


@csrf_exempt
def update_vector_embeddings(request):
    """Update vector embeddings for all doctors"""
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    try:
        from .utils import generate_embedding

        # Get all users to update
        users = User.objects.all()
        total_count = users.count()
        processed_count = 0
        error_count = 0

        # Process in batches
        batch_size = 50
        for i in range(0, total_count, batch_size):
            batch = users[i:i + batch_size]
            bulk_actions = []

            for user in batch:
                try:
                    # Generate specialty vector
                    specialty_text = ""
                    if user.specialties_id:
                        specialty_text = user.specialties.name

                    specialty_vector = generate_embedding(specialty_text)

                    # Generate about_me vector
                    about_text = user.about_me if user.about_me else ""
                    if user.healthcare_professional_info:
                        about_text += " " + user.healthcare_professional_info

                    about_me_vector = generate_embedding(about_text)

                    # Update document in Elasticsearch
                    doc = UserDocument.get(id=user.id)
                    doc.update(
                        specialty_vector=specialty_vector,
                        about_me_vector=about_me_vector
                    )

                    processed_count += 1
                except Exception as e:
                    logger.error(f"Error updating vector for user {user.id}: {str(e)}")
                    error_count += 1

            logger.info(f"Processed {processed_count}/{total_count} doctors")

        return JsonResponse({
            "status": "success",
            "message": f"Updated vectors for {processed_count} doctors with {error_count} errors."
        })

    except Exception as e:
        logger.error(f"Vector update error: {str(e)}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)

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
                    {"term": {"speciality.raw": specialty}},
                    {"term": {"city.raw": location}},
                    {"range": {"average_rating": {"gte": 4}}}
                ],
                "should": [
                    {"term": {"insurance_providers": insurance}},
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
    bool_query = {"must": []}

    # Specialty filter with improved handling for neurologists
    specialist_type_lower = specialist_type.lower()
    if specialist_type_lower in ["general practitioner", "family doctor", "gp"]:
        specialty_query = {
            "nested": {
                "path": "specialties",
                "query": {
                    "bool": {
                        "should": [  # Match ANY of these
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
                            "specialties.name.exact^10",  # Match nested field
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
    # Insurance provider
    # if insurance_provider:
    #     insurance_query = {
    #         "multi_match": {
    #             "query": insurance_provider,
    #             "fields": [
    #                 "accepted_insurance_providers.exact^10",  # Boost exact matches
    #                 "accepted_insurance_providers^5",  # Normal match
    #                 "accepted_insurance_providers.edge_ngram^3"  # Partial matches
    #             ],
    #             "fuzziness": "AUTO",
    #             "operator": "or",
    #             "type": "best_fields",
    #             "minimum_should_match": "30%"
    #         }
    #     }
    #     bool_query["must"].append(insurance_query)

    # Location filter
    if country:
        bool_query["must"].append({
            "bool": {  # Wrap in a bool query
                "should": [
                    {"term": {"country.name.exact": {"value": country.lower(), "boost": 3}}},
                    {"match": {"country.name": {"query": country, "fuzziness": 2, "boost": 1}}}
                ],
                "minimum_should_match": 1  # Ensure at least one condition matches
            }
        })

        # City filter (fuzzy match)
    if city:
        bool_query["must"].append({
            "match": {
                "city.name": {
                    "query": city,
                    "fuzziness": "AUTO"
                }
            }
        })

    # Language filter
    if language:
        language_query = {
            "match": {
                "languages": {
                    "query": language.lower(),
                    "boost": 2.0,  # Increase relevance
                    "fuzziness": "AUTO",  # Allow small typos
                    "operator": "or",  # Match any word
                    "minimum_should_match": "30%"  # At least 30% of words should match
                }
            }
        }

        bool_query["must"].append(language_query)

    # Telehealth filter
    # if telehealth_required:
    #     bool_query["must"].append({"term": {"is_online": "1"}})

    # Accepting new patients
    # bool_query["must"].append({"term": {"patient_status": "1"}})

    return bool_query


@circuit(failure_threshold=5, recovery_timeout=60)
def find_doctors_with_elasticsearch(specialist_type, country=None, city=None,
                                    language=None, telehealth_required=False,
                                    use_vector_search=True):
    """Search doctors using Elasticsearch DSL with vector search capability"""
    try:
        logger.info(
            f"Searching for doctors with: {specialist_type}, country={country}, city={city}, {language}, {telehealth_required}")
        search = UserDocument.search()

        # Generate vector embedding for the search query
        from .utils import generate_embedding
        query_vector = generate_embedding(specialist_type)

        # Initialize a bool query
        bool_query = build_elasticsearch_query(
            specialist_type,
            country=country,
            city=city,
            language=language,
            telehealth_required=telehealth_required
        )

        # Create combined query with both keyword and vector search
        combined_query = {
            "bool": {
                "must": [{"bool": bool_query}],
                "should": []
            }
        }

        # Add vector search if enabled
        if use_vector_search and query_vector:
            vector_queries = [
                {
                    "script_score": {
                        "query": {"bool": bool_query},
                        "script": {
                            "source": "(cosineSimilarity(params.query_vector, 'specialty_vector') + 1.0) * 3.0",
                            "params": {"query_vector": query_vector}
                        }
                    }
                }
            ]
            combined_query["bool"]["should"].extend(vector_queries)

        # Log the actual query being sent to Elasticsearch
        logger.info(f"Elasticsearch query: {json.dumps(combined_query)}")

        # Execute the search with appropriate sorting
        if use_vector_search and query_vector:
            # When using vector search, rely on script_score for ranking
            response = search.query(combined_query)[:6].execute()
        else:
            # Traditional search with explicit sorting
            response = search.query({"bool": bool_query}) \
                           .sort({'average_rating': {'order': 'desc'}})[:6].execute()

        doctors = [hit.to_dict() for hit in response]
        logger.info(f"Found {len(doctors)} doctors via Elasticsearch")

        # Fallback logic remains the same...

        return doctors

    except ConnectionError as e:
        logger.warning(f"Elasticsearch connection error: {e}, falling back to DB")
        return find_doctors(specialist_type, country, city,
                            languages, telehealth_required)
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
    """Initialize Elasticsearch index with current data"""
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    try:
        # Create the index
        from elasticsearch_dsl.connections import connections
        es = connections.get_connection()

        # Recreate the index
        UserDocument._index.delete(ignore=404)
        UserDocument.init()

        # Index the data in batches for better performance
        users = User.objects.all()
        batch_size = 100
        total_count = users.count()
        processed_count = 0

        for i in range(0, total_count, batch_size):
            batch = users[i:i + batch_size]
            bulk_actions = []

            for user in batch:
                doc = UserDocument()
                doc.prepare(user)
                bulk_actions.append(doc.to_dict(include_meta=True))

            if bulk_actions:
                UserDocument._index.bulk(bulk_actions)

            processed_count += len(batch)
            logger.info(f"Indexed {processed_count}/{total_count} doctors")

        return JsonResponse({
            "status": "success",
            "message": f"Indexed {processed_count} doctors successfully."
        })

    except Exception as e:
        logger.error(f"Elasticsearch indexing error: {str(e)}", exc_info=True)
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def debug_db_schema(request):
    """Endpoint to check database schema with improved security"""
    try:
        # Get database credentials from environment variables
        db_host = os.getenv("DB_HOST", "localhost")
        db_user = os.getenv("DB_USER", "root")
        db_password = os.getenv("DB_PASSWORD", "")  # Empty default for security
        db_name = os.getenv("DB_NAME", "doctor_directory")

        # Check if required credentials are set
        if not db_password:
            return JsonResponse({"error": "Database credentials not properly configured"}, status=500)

        conn = mysql.connector.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            database=db_name
        )
        cursor = conn.cursor(dictionary=True)

        # Get table structure
        cursor.execute("DESCRIBE users")
        columns = cursor.fetchall()

        column_names = [col['Field'] for col in columns]

        cursor.close()
        conn.close()

        return JsonResponse({
            "column_names": column_names
        })

    except Exception as e:
        logger.error(f"Database schema error: {str(e)}", exc_info=True)
        return JsonResponse({"error": "Database connection error"}, status=500)


@csrf_exempt
def view_indexed_data(request):
    """Endpoint to view indexed doctors data with better error handling"""
    try:
        from elasticsearch_dsl.connections import connections
        es = connections.get_connection()

        # Get the first 10 doctors from the index
        response = es.search(
            index=UserDocument._index._name,
            body={
                "query": {"match_all": {}},
                "size": 10
            }
        )

        # Extract hits
        hits = response.get('hits', {}).get('hits', [])
        doctors = [hit['_source'] for hit in hits]

        # Get total count
        total = response.get('hits', {}).get('total', {}).get('value', 0)

        return JsonResponse({
            "total_indexed": total,
            "sample_data": doctors
        })

    except ConnectionError:
        return JsonResponse({"error": "Could not connect to Elasticsearch"}, status=503)
    except Exception as e:
        logger.error(f"Error viewing indexed data: {str(e)}", exc_info=True)
        return JsonResponse({"error": "An error occurred while retrieving indexed data"}, status=500)