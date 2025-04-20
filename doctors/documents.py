#document.py
from django_elasticsearch_dsl import Document
from django_elasticsearch_dsl import fields as dsl_fields
from django_elasticsearch_dsl.registries import registry
from django.core.exceptions import ObjectDoesNotExist
from .models import *
import logging
logger = logging.getLogger(__name__)

@registry.register_document
class UserDocument(Document):

    specialties = dsl_fields.NestedField(properties={
        'name': dsl_fields.TextField(
            analyzer='specialty_analyzer',
            fields={
                'exact': dsl_fields.KeywordField(normalizer='lowercase_normalizer'),
                'edge_ngram': dsl_fields.TextField(analyzer='edge_ngram_analyzer')
            }
        ),
    })

    def prepare_languages(self, instance):
        """Convert to list of lowercase language names"""
        try:
            return [lang.name.lower() for lang in instance.languages.all()]
        except (AttributeError, ObjectDoesNotExist):
            return []

    def prepare_is_online(self, instance):
        """Convert char field to boolean"""
        return instance.is_online == '1'



    languages = dsl_fields.KeywordField(
        fields={
            'exact': dsl_fields.KeywordField(normalizer='lowercase_normalizer'),
            'edge_ngram': dsl_fields.TextField(analyzer='edge_ngram_analyzer')
        }
    )

    language_ids = dsl_fields.KeywordField(attr='language_ids')

    country = dsl_fields.NestedField(properties={
        'name': dsl_fields.TextField(
            fields={
                'exact': dsl_fields.KeywordField(normalizer='lowercase_normalizer'),
                'edge_ngram': dsl_fields.TextField(analyzer='edge_ngram_analyzer')
            }
        ),
    })

    city = dsl_fields.NestedField(
        properties={
            'name': dsl_fields.TextField(
            fields={
                'exact': dsl_fields.KeywordField(normalizer='lowercase_normalizer'),
                'edge_ngram': dsl_fields.TextField(analyzer='edge_ngram_analyzer')
            }),
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



    def prepare(self, instance):
        """Safe document preparation with error handling"""
        try:
            data = super().prepare(instance)

            # Handle location separately
            try:
                data['location'] = self.prepare_location(instance)
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid location for user {instance.id}: {e}")
                data['location'] = None

            return data
        except Exception as e:
            logger.error(f"Failed to index user {instance.id}: {str(e)}")
            return None

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

    class Index:
        name = 'doctors'
        settings = {
            'number_of_shards': 1,
            'number_of_replicas': 0,
            'analysis': {
                'analyzer': {
                    'specialty_analyzer': {
                        'type': 'custom',
                        'tokenizer': 'standard',
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
                        'min_gram': 4,
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

    def save(self, **kwargs):
        """
        Override the save method to index in bulk
        """
        from elasticsearch_dsl.connections import connections
        from elasticsearch.helpers import bulk

        # Index documents in smaller chunks
        client = connections.get_connection()
        actions = [self.to_dict() for self in Doctor.objects.all()]
        bulk(client, actions, chunk_size=500)
