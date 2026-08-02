from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.core.signing import Signer
from django.shortcuts import get_object_or_404
from oscar.core.loading import get_model
from rest_framework import generics
from rest_framework.request import Request
from rest_framework.response import Response

from oscarapicheckout import utils
from oscarapicheckout.states import PaymentStatus

from .methods import ClientSideCard

if TYPE_CHECKING:
    from ..order.models import Order
else:
    Order = get_model("order", "Order")


class CompleteClientSidePaymentView(generics.GenericAPIView[Any]):
    def post(self, request: Request) -> Response:
        amount = Decimal(request.data["amount"])
        order_number = request.data["reference_number"]
        order = get_object_or_404(Order, number=order_number)

        method_key = Signer().unsign(request.data["transaction_id"])

        new_state: PaymentStatus
        if request.data.get("deny"):
            new_state = ClientSideCard().record_declined_authorization(order, amount, reference="")
            utils.update_payment_method_state(order, request, method_key, new_state)
            return Response({"status": "Declined"})

        reference = request.data.get("result_token", "")
        new_state = ClientSideCard().record_successful_authorization(order, amount, reference)
        utils.update_payment_method_state(order, request, method_key, new_state)
        return Response({"status": "Success"})
