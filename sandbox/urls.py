from django.apps import apps
from django.conf import settings
from django.conf.urls import i18n, include
from django.contrib import admin
from django.urls import path
from django.views.static import serve

urlpatterns = [
    path("i18n/", include(i18n)),
    path("admin/", admin.site.urls),
    path(
        "media/<path:path>",
        serve,
        {"document_root": settings.MEDIA_ROOT, "show_indexes": True},
    ),
    # Include plugins
    path(
        "api/",
        include(
            apps.get_app_config("oscarapicheckout").urls[0]  # type:ignore[attr-defined]
        ),
    ),
    path("api/", include("oscarapi.urls")),
    path("creditcards/", include("sandbox.creditcards.urls")),
    # Include stock Oscar
    path(
        "",
        include(apps.get_app_config("oscar").urls[0]),  # type:ignore[attr-defined]
    ),
]
