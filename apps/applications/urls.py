from django.urls import path
from . import views

app_name = 'applications'

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('apply/', views.application_apply, name='apply'),
    path('apply/confirmation/<str:reference>/', views.application_confirmation, name='confirmation'),
    path('status/', views.application_status, name='status'),
    path('document/<int:doc_id>/preview/', views.document_preview, name='document_preview'),
]
