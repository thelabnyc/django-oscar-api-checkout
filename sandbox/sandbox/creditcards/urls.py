from django.urls import path
from .views import GetCardTokenView, AuthorizeCardView


urlpatterns = [
    path("get-token/", GetCardTokenView.as_view(), name="creditcards-get-token"),
    path("authorize/", AuthorizeCardView.as_view(), name="creditcards-authorize"),
]
