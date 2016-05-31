from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from oscar.core.loading import get_model
from oscarapi.views.checkout import CheckoutView as OscarCheckoutView
from .settings import (
    API_ENABLED_PAYMENT_METHODS,
    ORDER_STATUS_PAYMENT_DECLINED,
    ORDER_STATUS_AUTHORIZED,
)
from .serializers import (
    CheckoutSerializer,
    OrderSerializer,
    PaymentMethodsSerializer,
    PaymentStateSerializer
)
from .signals import order_placed
from .states import COMPLETE, DECLINED
from . import utils

Order = get_model('order', 'Order')

CHECKOUT_ORDER_ID = 'checkout_order_id'


class PaymentMethodsView(generics.GenericAPIView):
    serializer_class = PaymentMethodsSerializer

    def get(self, request):
        serializer = self.get_serializer()
        data = self.metadata_class().get_serializer_info(serializer)
        return Response(data)


class CheckoutView(generics.GenericAPIView):
    """
    Checkout and use a WFRS account as payment.

    POST(basket, shipping_address, wfrs_source_account,
         [total, shipping_method_code, shipping_charge, billing_address]):
    {
        "basket": "/api/baskets/1/",
        "guest_email": "foo@example.com",
        "total": "100.0",
        "shipping_charge": {
            "currency": "EUR",
            "excl_tax": "10.0",
            "tax": "0.6"
        },
        "shipping_method_code": "no-shipping-required",
        "shipping_address": {
            "country": "/api/countries/NL/",
            "first_name": "Henk",
            "last_name": "Van den Heuvel",
            "line1": "Roemerlaan 44",
            "line2": "",
            "line3": "",
            "line4": "Kroekingen",
            "notes": "Niet STUK MAKEN OK!!!!",
            "phone_number": "+31 26 370 4887",
            "postcode": "7777KK",
            "state": "Gerendrecht",
            "title": "Mr"
        },
        "payment": {
            "cash": {
                "amount": "100.00"
            }
        }
    }

    Returns the order object.
    """
    serializer_class = CheckoutSerializer

    def post(self, request, format=None):
        c_ser = self.get_serializer(data=request.data)
        if not c_ser.is_valid():
            return Response(c_ser.errors, status.HTTP_406_NOT_ACCEPTABLE)

        # Freeze basket
        basket = c_ser.validated_data.get('basket')
        basket.freeze()

        # Save Order
        order = c_ser.save()
        request.session[CHECKOUT_ORDER_ID] = order.id

        # Save payment steps into session for processing
        states = self._record_payments(order,
            methods=c_ser.fields['payment'].methods,
            data=c_ser.validated_data['payment'])
        utils.set_payment_method_states(order, request.session, states)

        # Return order data
        order_placed.send(sender=self, order=order, user=request.user, request=request)
        o_ser = OrderSerializer(order, context={ 'request': request })
        return Response(o_ser.data)


    def _record_payments(self, order, methods, data):
        order_balance = order.total_incl_tax
        states = {}

        data_amount_specified = { k: v for k, v in data.items() if not v['pay_balance'] }
        data_pay_balance = { k: v for k, v in data.items() if v['pay_balance'] }

        for code, method_data in data_amount_specified.items():
            method = methods[code]
            state = method.record_payment(order, **method_data)
            states[method.code] = state
            order_balance -= state.amount

        for code, method_data in data_pay_balance.items():
            method = methods[code]
            state = method.record_payment(order, amount=order_balance, **method_data)
            states[method.code] = state

        return states


class PaymentStatesView(generics.GenericAPIView):
    def get(self, request, pk=None):
        if pk and int(pk) != request.session.get(CHECKOUT_ORDER_ID):
            return Response(status=status.HTTP_404_NOT_FOUND)

        pk = request.session.get(CHECKOUT_ORDER_ID)
        order = get_object_or_404(Order, pk=pk)

        states = utils.list_payment_method_states(order, request.session)
        if not any(states):
            return Response(status=status.HTTP_201_NO_CONTENT)

        state_data = {}
        for code, state in states.items():
            ser = PaymentStateSerializer(instance=state)
            state_data[code] = ser.data

        return Response({
            'order_status': order.status,
            'payment_method_states': state_data
        })
