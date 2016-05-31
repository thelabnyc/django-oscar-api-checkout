from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.reverse import reverse
from oscar.core.loading import get_model
from oscarapicheckout import utils
from oscarapicheckout.states import FormPostRequired
from .methods import CreditCard

Order = get_model('order', 'Order')


class GetCardTokenView(generics.GenericAPIView):
    def post(self, request):
        amount = request.data['amount']
        order_number = request.data['reference_number']
        order = get_object_or_404(Order, number=order_number)

        # REquire the client to do another form post
        fields = [
            {
                'key': 'amount',
                'value': amount,
            },
            {
                'key': 'reference_number',
                'value': order_number,
            }
        ]
        new_state = FormPostRequired(
            amount=amount,
            name='authorize',
            url=reverse('creditcards-authorize'),
            fields=fields)
        utils.update_payment_method_state(order, request.session, CreditCard.code, new_state)

        return Response({
            'status': 'Success',
        })


class AuthorizeCardView(generics.GenericAPIView):
    def post(self, request):
        # Mark the payment method as complete
        order = get_object_or_404(Order, number=request.data['reference_number'])
        utils.mark_payment_method_completed(order, request.session, CreditCard.code, request.data['amount'])

        return Response({
            'status': 'Success',
        })
