from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.core.signing import Signer
from django.shortcuts import get_object_or_404
from oscar.core.loading import get_model
from rest_framework import generics
from rest_framework.exceptions import ParseError
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
        data = request.data
        if not isinstance(data, dict):
            raise ParseError("Expected a JSON object.")

        amount = Decimal(data["amount"])
        order_number = data["reference_number"]
        order = get_object_or_404(Order, number=order_number)

        method_key = Signer().unsign(data["transaction_id"])

        new_state: PaymentStatus
        if data.get("deny"):
            new_state = ClientSideCard().record_declined_authorization(order, amount, reference="")
            utils.update_payment_method_state(order, request, method_key, new_state)
            return Response({"status": "Declined"})

        reference = data.get("result_token", "")
        new_state = ClientSideCard().record_successful_authorization(order, amount, reference)
        utils.update_payment_method_state(order, request, method_key, new_state)
        return Response({"status": "Success"})
