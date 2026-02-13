from django.urls import path

from .views import CompleteClientSidePaymentView

urlpatterns = [
    path(
        "complete/",
        CompleteClientSidePaymentView.as_view(),
        name="clientside-complete",
    ),
]
