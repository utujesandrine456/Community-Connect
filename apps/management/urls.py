from django.urls import path
from . import views

app_name = 'management'

urlpatterns = [
    path('login/', views.admin_login, name='login'),
    path('logout/', views.admin_logout, name='logout'),
    path('', views.dashboard, name='dashboard'),
    path('application/<int:pk>/', views.application_detail, name='application_detail'),
    path('document/<int:doc_id>/download/', views.document_download, name='document_download'),
    path('documents/organize/', views.organize_documents_view, name='organize_documents'),
]
