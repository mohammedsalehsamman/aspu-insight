import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aspu_insight.settings')

# يجب استدعاء get_asgi_application() (يُشغِّل django.setup() داخلياً) قبل استيراد أي شيء
# يحمّل نماذج Django — لذا notifications.routing يُستورَد بعده لا قبله.
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

import notifications.routing  # noqa: E402

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': URLRouter(notifications.routing.websocket_urlpatterns),
})
