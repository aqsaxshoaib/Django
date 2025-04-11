#document.py
from django_elasticsearch_dsl import Document
from django_elasticsearch_dsl import fields as dsl_fields
from .custom_fields import DenseVectorField
from django_elasticsearch_dsl.registries import registry
from .utils import *
from .models import *
import logging
logger = logging.getLogger(__name__)

@registry.register_document
class UserDocument(Document):
    specialty_vector = DenseVectorField(dims=384)
    about_me_vector = DenseVectorField(dims=384)

    # Keep other fields using dsl_fields
    specialties = dsl_fields.NestedField(properties={
        'name': dsl_fields.TextField(
            analyzer='specialty_analyzer',
            fields={
                'exact': dsl_fields.KeywordField(normalizer='lowercase_normalizer'),
                'edge_ngram': dsl_fields.TextField(analyzer='edge_ngram_analyzer')
            }
        ),
    })

    def prepare_specialty_vector(self, instance):
        try:
            specialty_text = f"{instance.specialties.name if instance.specialties else ''}".strip()

            # Skip individual processing during bulk operations
            if hasattr(instance, '_bulk_preparation'):
                return None

            logger.debug(f"Preparing specialty vector for {instance.id}")
            vector = generate_embedding(specialty_text)
            return vector
        except Exception as e:
            logger.error(f"Error preparing specialty vector: {str(e)}")
            return [0.0] * 384  # Match model dimensions

    def prepare_about_me_vector(self, instance):
        try:
            about_text = f"{instance.about_me or ''} {instance.healthcare_professional_info or ''}".strip()

            # Skip individual processing during bulk operations
            if hasattr(instance, '_bulk_preparation'):
                return None

            logger.debug(f"Preparing about_me vector for {instance.id}")
            vector = generate_embedding(about_text)
            return vector
        except Exception as e:
            logger.error(f"Error preparing about_me vector: {str(e)}")
            return [0.0] * 384  # Match model dimensions

    # Add bulk processing optimization
    def bulk_prepare(self, instances):
        """Batch process embeddings for better performance"""
        try:
            # Collect texts for batch processing
            specialty_texts = []
            about_me_texts = []

            for inst in instances:
                # Specialty text
                specialty_text = f"{inst.specialties.name if inst.specialties else ''}".strip()
                specialty_texts.append(self.prepare_specialty_vector(inst))

                # About me text
                about_text = f"{inst.about_me or ''} {inst.healthcare_professional_info or ''}".strip()
                about_me_texts.append(self.prepare_about_me_vector(inst))

            # Batch embed
            specialty_vectors = batch_embed_medical_text(specialty_texts)
            about_me_vectors = batch_embed_medical_text(about_me_texts)

            # Store prepared data
            for inst, s_vec, a_vec in zip(instances, specialty_vectors, about_me_vectors):
                inst._prepared_data = {
                    'specialty_vector': s_vec.tolist(),
                    'about_me_vector': a_vec.tolist()
                }

        except Exception as e:
            logger.error(f"Bulk preparation failed: {str(e)}")
            raise


    def prepare_languages(self, instance):
        """Alternative preparation method"""
        return [lang.name for lang in instance.languages]

    def get_language_names(self):
        """Helper method to get language names"""
        return ", ".join(lang.name for lang in self.languages)



    languages = dsl_fields.TextField(  # Fixed this line
        attr='get_language_names',
        analyzer='standard',
        fields={
            'raw': dsl_fields.KeywordField(),
            'suggest': dsl_fields.CompletionField()
        }
    )

    language_ids = dsl_fields.KeywordField(attr='language_ids')

    country = dsl_fields.NestedField(properties={
        'name': dsl_fields.TextField(
            fields={
                'exact': dsl_fields.KeywordField()
            }
        ),
    })

    city = dsl_fields.NestedField(
        properties={
            'name': dsl_fields.TextField(),
            'canton': dsl_fields.ObjectField(properties={
                'name': dsl_fields.TextField(),
            })
        }
    )

    experties = dsl_fields.ObjectField(
        properties={
            'name': dsl_fields.TextField(
                analyzer='standard',
                fields={'exact': dsl_fields.KeywordField()}
            ),
        },
        dynamic=False
    )

    average_rating = dsl_fields.FloatField()

    reviews = dsl_fields.NestedField(
        properties={
            'rating': dsl_fields.IntegerField(),
            'comments': dsl_fields.TextField(),
            'status': dsl_fields.KeywordField()
        }
    )

    Speaking_Languages = dsl_fields.KeywordField(multi=True)

    location = dsl_fields.ObjectField(
        properties={
            'lat': dsl_fields.FloatField(),
            'lon': dsl_fields.FloatField()
        }
    )

    healthcare_professional_info = dsl_fields.TextField()

    def prepare_reviews(self, instance):
        """Collect all user reviews"""
        return [{
            "rating": review.rating,
            "comments": review.comments,
            "status": review.status
        } for review in instance.review_set.all()]  # Use correct reverse relation

    def prepare_average_rating(self, instance):
        """Calculate average rating from all reviews"""
        ratings = [r.rating for r in instance.review_set.all() if r.rating is not None]
        return round(sum(ratings) / len(ratings), 2) if ratings else 0.0

    def prepare_location(self, instance):
        """Handle invalid geo coordinates"""
        try:
            return {
                "lat": float(instance.latitude or 0),
                "lon": float(instance.longitude or 0)
            }
        except (TypeError, ValueError):
            return None

    def prepare_Speaking_Languages(self, instance):
        """
        Convert Speaking_Languages to a list of strings
        Handle comma-separated values properly
        """
        if not instance.Speaking_Languages:
            return []

        # Strip whitespace and filter out empty strings
        return [lang.strip() for lang in instance.Speaking_Languages.split(',') if lang.strip()]

    def prepare_specialties(self, instance):
        """Return specialties as list of nested objects"""
        try:
            if instance.specialties_id:
                return [{'name': instance.specialties.name}]
        except ObjectDoesNotExist:
            pass
        return []

    def prepare_city(self, instance):
        """Safe city preparation"""
        try:
            if instance.city_id and City.objects.filter(id=instance.city_id).exists():
                city_data = {'name': instance.city.name}
                if instance.city.canton_id:
                    city_data['canton'] = {'name': instance.city.canton.name}
                return city_data
        except ObjectDoesNotExist:
            pass
        return None

    def prepare_experties(self, instance):
        """Safe expertise preparation"""
        try:
            if instance.experties_id and Expertise.objects.filter(id=instance.experties_id).exists():
                return {'name': instance.experties.name}
        except ObjectDoesNotExist:
            pass
        return None

    # def prepare_reviews(self, instance):
    #     """Safe review preparation"""
    #     try:
    #         if instance.reviews_id and Review.objects.filter(id=instance.reviews_id).exists():
    #             return {
    #                 "rating": instance.reviews.rating,
    #                 "comments": instance.reviews.comments,
    #                 "status": instance.reviews.status
    #             }
    #     except ObjectDoesNotExist:
    #         pass
    #     return None

    class Index:
        name = 'doctors'
        settings = {
            'number_of_shards': 1,
            'number_of_replicas': 0,
            'analysis': {
                'analyzer': {
                    'specialty_analyzer': {
                        'type': 'custom',
                        'tokenizer': 'keyword',
                        'filter': [
                            'lowercase',
                            'asciifolding',
                            'english_possessive_stemmer',
                            'snowball_english'
                        ]
                    },
                    'edge_ngram_analyzer': {
                        'type': 'custom',
                        'tokenizer': 'edge_ngram_tokenizer',
                        'filter': ['lowercase', 'asciifolding']
                    },
                },
                'tokenizer': {
                    'edge_ngram_tokenizer': {
                        'type': 'edge_ngram',
                        'min_gram': 3,
                        'max_gram': 15,
                        'token_chars': ['letter']
                    }
                },
                'filter': {
                    'english_possessive_stemmer': {
                        'type': 'stemmer',
                        'name': 'english'
                    },
                    'snowball_english': {
                        'type': 'snowball',
                        'language': 'English'
                    }
                },
                'normalizer': {
                    'lowercase_normalizer': {
                        'type': 'custom',
                        'filter': ['lowercase', 'asciifolding']
                    }
                }
            }
        }


        using = 'default'

    class Django:
        model = User
        fields = [
            'id',
            'first_name',
            'last_name',
            'title',
            'email',
            'gender',
            'age',
            'profile_pic',
            'postal_code',
            'web_url',
            'role',
            'speciality',
            'service_type',
            'fees',
            'is_online',
            'is_active',
            'status',
            'payment_method',
            'patient_status',
            'institute_id',
            'zefix_ide',
            'about_me',
        ]
        auto_prepare = False

    def prepare(self, instance):
        data = super().prepare(instance)
        # Manually add vector fields
        data.update({
            'specialty_vector': self.prepare_specialty_vector(instance),
            'about_me_vector': self.prepare_about_me_vector(instance)
        })
        return data