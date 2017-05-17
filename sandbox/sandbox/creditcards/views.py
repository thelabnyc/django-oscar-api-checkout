from decimal import Decimal
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.response import Response
from oscar.core.loading import get_model
from oscarapicheckout import utils
from .methods import CreditCard
import uuid

Order = get_model('order', 'Order')


class GetCardTokenView(generics.GenericAPIView):
    def post(self, request):
        amount = Decimal(request.data['amount'])
        order_number = request.data['reference_number']
        order = get_object_or_404(Order, number=order_number)

        # Decline the payment
        if request.data.get('deny'):
            utils.mark_payment_method_declined(order, request, CreditCard.code, request.data['amount'])
            return Response({
                'status': 'Declined',
            })

        # Require the client to do another form post
        new_state = CreditCard().require_authorization_post(order, amount)
        utils.update_payment_method_state(order, request, CreditCard.code, new_state)
        return Response({
            'status': 'Success',
        })


class AuthorizeCardView(generics.GenericAPIView):
    def post(self, request):
        # Mark the payment method as complete or denied
        amount = Decimal(request.data['amount'])
        order_number = request.data['reference_number']
        order = get_object_or_404(Order, number=order_number)

        # Decline the payment
        if request.data.get('deny'):
            utils.mark_payment_method_declined(order, request, CreditCard.code, request.data['amount'])
            return Response({
                'status': 'Declined',
            })

        # Record the funds allocation
        new_state = CreditCard().record_successful_authorization(order, amount, uuid.uuid1())
        utils.update_payment_method_state(order, request, CreditCard.code, new_state)
        return Response({
            'status': 'Success',
        })
