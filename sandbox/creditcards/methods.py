from rest_framework.reverse import reverse
from oscarapicheckout.methods import PaymentMethod, PaymentMethodSerializer
from oscarapicheckout.states import FormPostRequired, Complete


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


    # Payment Step 1
    def _record_payment(self, order, amount, reference, **kwargs):
        source = self.get_source(order, reference)
        amount_to_allocate = amount - source.amount_allocated

        fields = [
            {
                'key': 'amount',
                'value': amount_to_allocate
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


    # Payment Step 2
    def require_authorization_post(self, order, amount):
        fields = [
            {
                'key': 'amount',
                'value': amount,
            },
            {
                'key': 'reference_number',
                'value': order.number,
            }
        ]
        return FormPostRequired(
            amount=amount,
            name='authorize',
            url=reverse('creditcards-authorize'),
            fields=fields)


    # Payment Step 3
    def record_successful_authorization(self, order, amount, reference):
        source = self.get_source(order, reference)

        source.allocate(amount, reference)
        event = self.make_authorize_event(order, amount, reference)
        for line in order.lines.all():
            self.make_event_quantity(event, line, line.quantity)

        return Complete(source.amount_allocated)
