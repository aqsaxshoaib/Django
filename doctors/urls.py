# In your app's urls.py
from django.urls import path
from . import views  # Import your views module

urlpatterns = [
    path('chatbot/', views.chatbot, name='chatbot'),
    path('initialize_elasticsearch/', views.initialize_elasticsearch, name='initialize_elasticsearch'),
]
