from django.urls import re_path
from django.views.decorators.cache import never_cache
from django.utils.translation import gettext_lazy as _
from oscar.core.application import OscarConfig


class Config(OscarConfig):
    name = "oscarapicheckout"
    label = "oscarapicheckout"
    verbose_name = _("Oscar API-Checkout")
    namespace = "oscarapicheckout"

    def ready(self):
        # Register signal handlers
        from . import handlers  # NOQA

    def get_urls(self):
        from .views import (
            PaymentMethodsView,
            CheckoutView,
            CompleteDeferredPaymentView,
            PaymentStatesView,
        )

        view_methods = never_cache(PaymentMethodsView.as_view())
        view_states = never_cache(PaymentStatesView.as_view())
        view_checkout = never_cache(CheckoutView.as_view())
        view_complete_deferred_payment = never_cache(
            CompleteDeferredPaymentView.as_view()
        )
        urlpatterns = [
            re_path(
                r"^checkout/payment-methods/$",
                view_methods,
                name="api-checkout-payment-methods",
            ),
            re_path(r"^checkout/payment-states/$", view_states, name="api-payment"),
            re_path(
                r"^checkout/payment-states/(?P<pk>\d+)/$",
                view_states,
                name="api-payment",
            ),
            re_path(
                r"^checkout/complete-deferred-payment/$",
                view_complete_deferred_payment,
                name="api-complete-deferred-payment",
            ),
            re_path(r"^checkout/$", view_checkout, name="api-checkout"),
        ]
        return self.post_process_urls(urlpatterns)
