"""
Community Connect — URL Configuration
Two Custom Business Apps:
- applications (public citizen-facing portal)
- management (private administrator portal)
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Public citizen assistance portal (root)
    path('', include('apps.applications.urls')),
    
    # Administrator management dashboard & portal
    path('manage/', include('apps.management.urls')),
    
    # Convenience auth redirects
    path('login/', RedirectView.as_view(url='/manage/login/', permanent=False)),
    path('logout/', RedirectView.as_view(url='/manage/logout/', permanent=False)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
