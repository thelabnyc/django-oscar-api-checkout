from django.urls import path
from django.urls.resolvers import URLPattern, URLResolver
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache
from oscar.core.application import OscarConfig


class Config(OscarConfig):
    name = "oscarapicheckout"
    label = "oscarapicheckout"
    verbose_name = _("Oscar API-Checkout")
    namespace = "oscarapicheckout"
    default = True

    def ready(self) -> None:
        # Register signal handlers
        from . import handlers  # NOQA

    def get_urls(self) -> list[URLPattern | URLResolver]:
        from .views import (
            CheckoutView,
            CompleteDeferredPaymentView,
            PaymentMethodsView,
            PaymentStatesView,
        )

        view_methods = never_cache(PaymentMethodsView.as_view())
        view_states = never_cache(PaymentStatesView.as_view())
        view_checkout = never_cache(CheckoutView.as_view())
        view_complete_deferred_payment = never_cache(
            CompleteDeferredPaymentView.as_view()
        )
        urlpatterns = [
            path(
                "checkout/payment-methods/",
                view_methods,
                name="api-checkout-payment-methods",
            ),
            path("checkout/payment-states/", view_states, name="api-payment"),
            path(
                "checkout/payment-states/<int:pk>/",
                view_states,
                name="api-payment",
            ),
            path(
                "checkout/complete-deferred-payment/",
                view_complete_deferred_payment,
                name="api-complete-deferred-payment",
            ),
            path("checkout/", view_checkout, name="api-checkout"),
        ]
        return self.post_process_urls(urlpatterns)  # type:ignore[no-any-return]
