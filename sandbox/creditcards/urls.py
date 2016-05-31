from django.conf.urls import patterns, url
from .views import GetCardTokenView, AuthorizeCardView


urlpatterns = patterns('',
    url(r'^get-token/', GetCardTokenView.as_view(), name='creditcards-get-token'),
    url(r'^authorize/', AuthorizeCardView.as_view(), name='creditcards-authorize'),
)
