from django.urls import re_path
from .views import GetCardTokenView, AuthorizeCardView


urlpatterns = [
    re_path(r"^get-token/", GetCardTokenView.as_view(), name="creditcards-get-token"),
    re_path(r"^authorize/", AuthorizeCardView.as_view(), name="creditcards-authorize"),
]
