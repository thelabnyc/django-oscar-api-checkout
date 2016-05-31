from django.conf.urls import url
from oscar.core.application import Application
from .views import PaymentMethodsView, CheckoutView, PaymentStatesView


class APICheckoutApplication(Application):
    def get_urls(self):
        urlpatterns = [
            url(r'^checkout/payment-methods/$', PaymentMethodsView.as_view(), name='api-checkout-payment-methods'),
            url(r'^checkout/payment-states/$', PaymentStatesView.as_view(), name='api-payment'),
            url(r'^checkout/payment-states/(?P<pk>\d+)/$', PaymentStatesView.as_view(), name='api-payment'),
            url(r'^checkout/$', CheckoutView.as_view(), name='api-checkout'),
        ]
        return self.post_process_urls(urlpatterns)


application = APICheckoutApplication()
