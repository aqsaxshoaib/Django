# In your app's urls.py
from django.urls import path
from . import views  # Import your views module

urlpatterns = [
    path('chatbot/', views.chatbot, name='chatbot'),
    path('symptom_analysis/', views.symptom_analysis, name='symptom_analysis'),
    path('initialize_elasticsearch/', views.initialize_elasticsearch, name='initialize_elasticsearch'),
    path('debug_db_schema/', views.debug_db_schema, name='debug_db_schema'),
    path('view-indexed-data/', views.view_indexed_data, name='view_indexed_data'),
    path('api/update-vectors/', views.update_vector_embeddings, name='update_vector_embeddings'),
]
