from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView
)

from accounts.urls import (
    auth_urlpatterns,
    admin_urlpatterns
)

urlpatterns = [

    path(
        'admin/2004/R/',
        admin.site.urls
    ),

    path(
        'api/auth/ASPU-2004/',
        include((auth_urlpatterns, 'auth'))
    ),

    path(
        'api/admin/2004-R/',
        include((admin_urlpatterns, 'admin-api'))
    ),

    path(
        'api/admin/2004-R/dashboard/',
        include('dashboard.urls')
    ),

    path(
        'api/admin/2004-R/configuration/',
        include('configuration.urls')
    ),

    path(
        'api/admin/2004-R/research-history/',
        include('researchHistory.urls')
    ),

    path(
        'api/ai/ai2004-R/',
        include(
            'ai_service.urls',
            namespace='ai_service'
        )
    ),

    path(
        'api/research/researchAspu2004/',
        include('research.urls')
    ),

    path(
        'api/research/',
        include('assistantReview.urls')
    ),

    path(
        'api/research/',
        include('editorReview.urls')
    ),

    path(
        'api/v1/committees-app/', include('committees.urls')
        ),

    path(
        'api/notifications/notificationsAspu2004/',
        include('notifications.urls')
    ),

]

if settings.DEBUG:

    urlpatterns += [

        path(
            'api/schema/schemaAspu2004/',
            SpectacularAPIView.as_view(),
            name='schema'
        ),

        path(
            'api/docs/',
            SpectacularSwaggerView.as_view(
                url_name='schema'
            ),
            name='swagger-ui'
        ),

        path(
            'api/redoc/redocAspu2004/',
            SpectacularRedocView.as_view(
                url_name='schema'
            ),
            name='redoc'
        ),

    ]

    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )

    urlpatterns += static(
        settings.STATIC_URL,
        document_root=settings.STATIC_ROOT
    )