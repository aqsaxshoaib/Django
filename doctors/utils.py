#utils.py
import os
import numpy as np
from sentence_transformers import SentenceTransformer
import logging
logger = logging.getLogger(__name__)

# Choose appropriate model for embedding generation
model = None


def get_embedding_model():
    global model
    if model is None:
        try:
            # Best overall medical model
            model = SentenceTransformer(
                'abhinand/MedEmbed-small-v0.1',
                device='cpu'  # or 'cuda'
            )

        except Exception as e:
            logger.error(f"Error loading embedding model: {e}")
            raise  # Critical error - should fail fast
    return model


# utils.py
def generate_embedding(text):
    """Optimized for clinical text retrieval"""
    try:
        text = text.strip()
        if not text:
            return [0.0] * 384  # Match model dimensions

        model = get_embedding_model()

        # Medical text preprocessing
        processed_text = text.lower().replace('\n', ' ').replace('\r', '')

        # Clinical-specific encoding parameters
        embedding = model.encode(
            processed_text,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=32
        )

        logger.info(f"Generated embedding of shape: {embedding.shape} for text: {processed_text[:30]}...")

        return embedding.tolist()

    except Exception as e:
        logger.error(f"Medical embedding failed: {str(e)}")
        return [0.0] * 384
def generate_openai_embedding(text):
    """Alternative: Use OpenAI API for embeddings"""
    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )

        response = client.embeddings.create(
            model="openai/text-embedding-ada-002",
            input=text
        )

        return response.data[0].embedding
    except Exception as e:
        logging.error(f"Error generating OpenAI embedding: {e}")
        return [0.0] * 384