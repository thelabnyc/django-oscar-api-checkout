from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.core.signing import Signer
from rest_framework import generics
from rest_framework.response import Response
from oscar.core.loading import get_model
from oscarapicheckout import utils
from .methods import CreditCard

Order = get_model('order', 'Order')


class GetCardTokenView(generics.GenericAPIView):
    def post(self, request):
        amount = Decimal(request.data['amount'])
        order_number = request.data['reference_number']
        order = get_object_or_404(Order, number=order_number)

        # Get the method key
        method_key = Signer().unsign(request.data['transaction_id'])

        # Decline the payment
        if request.data.get('deny'):
            utils.mark_payment_method_declined(order, request, method_key, request.data['amount'])
            return Response({
                'status': 'Declined',
            })

        # Require the client to do another form post
        new_state = CreditCard().require_authorization_post(order, method_key, amount)
        utils.update_payment_method_state(order, request, method_key, new_state)
        return Response({
            'status': 'Success',
        })


class AuthorizeCardView(generics.GenericAPIView):
    def post(self, request):
        # Mark the payment method as complete or denied
        amount = Decimal(request.data['amount'])
        order_number = request.data['reference_number']
        order = get_object_or_404(Order, number=order_number)

        # Get the method key
        method_key = Signer().unsign(request.data['transaction_id'])

        # Get transaction UUID
        reference = request.data['uuid']

        # Decline the payment
        if request.data.get('deny'):
            new_state = CreditCard().record_declined_authorization(order, amount, reference)
            utils.update_payment_method_state(order, request, method_key, new_state)
            return Response({
                'status': 'Declined',
            })

        # Record the funds allocation
        new_state = CreditCard().record_successful_authorization(order, amount, reference)
        utils.update_payment_method_state(order, request, method_key, new_state)
        return Response({
            'status': 'Success',
        })
