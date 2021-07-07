from django.conf.urls import url
from .views import GetCardTokenView, AuthorizeCardView


urlpatterns = [
    url(r"^get-token/", GetCardTokenView.as_view(), name="creditcards-get-token"),
    url(r"^authorize/", AuthorizeCardView.as_view(), name="creditcards-authorize"),
]
