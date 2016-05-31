from rest_framework.reverse import reverse
from oscarapicheckout.methods import PaymentMethod, PaymentMethodSerializer
from oscarapicheckout.states import FormPostRequired


class CreditCard(PaymentMethod):
    """
    This is an example of how to implement a payment method that required some off-site
    interaction, like Cybersource Secure Acceptance, for example. It returns a pending
    status initially that requires the client app to make a form post, which in-turn
    redirects back to us. This is a common pattern in PCI SAQ A-EP ecommerce sites.
    """
    name = 'Credit Card'
    code = 'credit-card'
    serializer_class = PaymentMethodSerializer

    def _record_payment(self, order, amount, reference, **kwargs):
        fields = [
            {
                'key': 'amount',
                'value': amount
            },
            {
                'key': 'reference_number',
                'value': order.number
            }
        ]
        # Return a response showing we need to post some fields to the given
        # URL to finishing processing this payment method
        return FormPostRequired(
            amount=amount,
            name='get-token',
            url=reverse('creditcards-get-token'),
            fields=fields)
