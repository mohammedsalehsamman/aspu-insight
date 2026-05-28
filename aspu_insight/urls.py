from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from accounts.urls import auth_urlpatterns, admin_urlpatterns

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/ai/', include('ai_service.urls', namespace='ai_service')),
    path('api/auth/', include((auth_urlpatterns, 'auth'))),
    path('api/admin/', include((admin_urlpatterns, 'admin-api'))),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)