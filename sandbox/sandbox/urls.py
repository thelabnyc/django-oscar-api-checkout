from django.conf import settings
from django.conf.urls import include, url, i18n
from django.contrib import admin
from django.views.static import serve
from oscar.app import application as oscar_application
from oscarapi.app import application as oscar_api
from oscarapicheckout.app import application as oscar_api_checkout
from sandbox.creditcards import urls as cc_urls


urlpatterns = [
    url(r'^i18n/', include(i18n)),
    url(r'^admin/', admin.site.urls),
    url(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT, 'show_indexes': True}),

    # Include plugins
    url(r'^api/', oscar_api_checkout.urls),
    url(r'^api/', oscar_api.urls),

    url(r'^creditcards/', include(cc_urls)),

    # Include stock Oscar
    url(r'', oscar_application.urls),
]
