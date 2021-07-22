from django.apps import apps
from django.conf import settings
from django.conf.urls import include, i18n
from django.urls import re_path
from django.contrib import admin
from django.views.static import serve


urlpatterns = [
    re_path(r"^i18n/", include(i18n)),
    re_path(r"^admin/", admin.site.urls),
    re_path(
        r"^media/(?P<path>.*)$",
        serve,
        {"document_root": settings.MEDIA_ROOT, "show_indexes": True},
    ),
    # Include plugins
    re_path(r"^api/", include(apps.get_app_config("oscarapicheckout").urls[0])),
    re_path(r"^api/", include("oscarapi.urls")),
    re_path(r"^creditcards/", include("sandbox.creditcards.urls")),
    # Include stock Oscar
    re_path(r"^", include(apps.get_app_config("oscar").urls[0])),
]
