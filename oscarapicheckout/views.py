from typing import Any, cast
import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from oscar.core.loading import get_model
from rest_framework import generics, status
from rest_framework.metadata import SimpleMetadata
from rest_framework.request import Request
from rest_framework.response import Response

from . import utils
from .methods import PaymentMethod, PaymentMethodData
from .serializers import (
    CheckoutSerializer,
    CompleteDeferredPaymentSerializer,
    OrderSerializer,
    PaymentMethodsSerializer,
    PaymentStateSerializer,
)
from .settings import ORDER_STATUS_AUTHORIZED
from .signals import order_placed
from .states import CONSUMED, DECLINED, PaymentStatus

Order = get_model("order", "Order")

CHECKOUT_ORDER_ID = "checkout_order_id"

logger = logging.getLogger(__name__)


class PaymentMethodsView(generics.GenericAPIView[Any]):
    serializer_class = PaymentMethodsSerializer  # type:ignore[assignment]

    def get(self, request: Request) -> Response:
        root_serializer: PaymentMethodsSerializer = (
            self.get_serializer()  # type:ignore[assignment]
        )
        meta = cast(SimpleMetadata, self.metadata_class())  # type:ignore[operator, misc]
        data = {}
        for (
            method_code,
            method_serializer,
        ) in root_serializer.child.type_mapping.items():
            method = root_serializer.methods[method_code]
            data[method_code] = {
                "type": "nested object",
                "required": False,
                "read_only": False,
                "label": method.name,
                "children": meta.get_serializer_info(method_serializer),
            }
        return Response(data)


class CheckoutView(generics.GenericAPIView[Any]):
    """
    Checkout and begin collecting payment.

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

    def post(self, request: Request, format: str | None = None) -> Response:
        # Wipe out any previous state data
        utils.clear_consumed_payment_method_states(request)

        # Validate the input
        c_ser: CheckoutSerializer = self.get_serializer(  # type:ignore[assignment]
            data=request.data
        )
        if not c_ser.is_valid():
            return Response(c_ser.errors, status.HTTP_406_NOT_ACCEPTABLE)

        # Freeze basket
        basket = c_ser.validated_data.get("basket")
        basket.freeze()

        # Save Order
        order = c_ser.save()
        request.session[CHECKOUT_ORDER_ID] = order.id
        utils.drop_foreign_payment_method_states(order, request)

        # Send order_placed signal
        order_placed.send(
            sender=self,
            order=order,
            user=request.user,
            request=request,
            recaptcha_score=c_ser.get_recaptcha_score(),
        )

        # Save payment steps into session for processing
        self._record_payments_and_set_states(
            request,
            order,
            c_ser.fields["payment"].methods,  # type:ignore[attr-defined]
            c_ser.validated_data["payment"],
        )

        # Return order data
        o_ser = OrderSerializer(order, context={"request": request})
        return Response(o_ser.data)

    def _record_payments_and_set_states(
        self,
        request: Request,
        order: Order,
        methods: dict[str, PaymentMethod[PaymentMethodData]],
        data: dict[str, PaymentMethodData],
    ) -> None:
        """
        Collect payment for a placed order, unwinding the order if that fails.

        Storing the states is inside the backstop as well as recording them:
        that write runs the authorization guard, the configured authorized-amount
        calculator and the authorize/decline signals, any of which can raise
        after payment has already been taken.
        """
        previous_states = utils.list_payment_method_states(request)
        try:
            new_states = self._record_payments(
                previous_states=previous_states,
                request=request,
                order=order,
                methods=methods,
                data=data,
            )
            utils.set_payment_method_states(order, request, new_states)
        except Exception:
            self._recover_from_payment_error(request, order)
            raise

    def _recover_from_payment_error(self, request: Request, order: Order) -> None:
        """
        Undo the freeze-then-collect-payment setup after payment collection blew up.

        The basket is frozen and the order created before any payment method
        runs, and only a decline thaws them again. Without this, an unhandled
        error strands the customer with an unreachable basket and an order stuck
        in its initial status.

        Recovery is best-effort and must never replace the exception that
        triggered it. It is skipped once the order is authorized, because the
        decline teardown deletes discounts and line prices that nothing would
        rebuild. Session payment states are left alone so a retry behaves as
        though the failed request had never happened; methods that succeeded
        before the failure are therefore re-recorded on the retry, which for a
        method keyed by a per-attempt reference means a second authorization,
        and for a method that captures synchronously a second charge to refund.
        """
        if order.status == ORDER_STATUS_AUTHORIZED:
            return
        try:
            # Atomic because the teardown is six independent writes and this
            # runs when the request has already failed once: a partial decline
            # leaves an order no retry can rebuild.
            with transaction.atomic():
                utils.decline_order_payment(order, request, internal_error=True)
        except Exception:
            logger.exception(
                "Failed to recover Order[%s] after an error while recording payment.",
                order.number,
            )

    def _record_payments(
        self,
        previous_states: dict[str, PaymentStatus],
        request: Request,
        order: Order,
        methods: dict[str, PaymentMethod[PaymentMethodData]],
        data: dict[str, PaymentMethodData],
    ) -> dict[str, PaymentStatus]:
        order_balance = [order.total_incl_tax]
        new_states: dict[str, PaymentStatus] = {}

        def record(method_key: str, method_data: PaymentMethodData) -> PaymentStatus:
            # If a previous payment method at least partially succeeded, hasn't been consumed by an
            # order, and is for the same amount, recycle it. This requires that the amount hasn't changed.

            # Get the processor class for this method
            code = method_data["method_type"]
            method = methods[code]

            state: PaymentStatus | None = None
            if method_key in previous_states:
                prev = previous_states[method_key]
                if not utils.payment_state_belongs_to_order(prev, order):
                    # Unreachable from the views above, which drop foreign states
                    # before this runs. Kept for callers that reach _record_payments
                    # by another route: another order's money is never recycled,
                    # and never voided against this order either.
                    utils.warn_foreign_payment_state(order, method_key, prev)
                elif prev.status not in (DECLINED, CONSUMED):
                    if prev.amount == method_data["amount"]:
                        state = prev
                    else:
                        # Previous payment exists but we can't recycle it; void whatever already exists.
                        method.void_existing_payment(request, order, method_key, prev)

            # Previous payment method doesn't exist or can't be reused. Create it now.
            final_state = state if state else method.record_payment(request, order, method_key, **method_data)
            # Subtract amount from pending order balance.
            order_balance[0] = order_balance[0] - final_state.amount
            return final_state

        # Loop through each method with a specified amount to charge
        data_amount_specified = {k: v for k, v in data.items() if not v["pay_balance"]}
        for key, method_data in data_amount_specified.items():
            new_states[key] = record(key, method_data)

        # Change the remainder, not covered by the above methods, to the method marked with `pay_balance`
        data_pay_balance = {k: v for k, v in data.items() if v["pay_balance"]}
        for key, method_data in data_pay_balance.items():
            method_data["amount"] = order_balance[0]
            new_states[key] = record(key, method_data)

        return new_states


class CompleteDeferredPaymentView(CheckoutView):
    """
    Authorize payment for an order previously placed using the “Pay Later”
    deferred payment method.
    """

    serializer_class = CompleteDeferredPaymentSerializer  # type:ignore[assignment]

    def post(self, request: Request, format: str | None = None) -> Response:
        # Wipe out any previous state data
        utils.clear_consumed_payment_method_states(request)

        # Validate the input
        c_ser: CompleteDeferredPaymentSerializer = self.get_serializer(  # type:ignore[assignment]
            data=request.data
        )
        if not c_ser.is_valid():
            return Response(c_ser.errors, status.HTTP_406_NOT_ACCEPTABLE)

        # Update the session to note that we're working on this order
        order = c_ser.validated_data["order"]
        request.session[CHECKOUT_ORDER_ID] = order.id
        utils.drop_foreign_payment_method_states(order, request)

        # Save payment steps into session for processing
        self._record_payments_and_set_states(
            request,
            order,
            c_ser.fields["payment"].methods,  # type:ignore[attr-defined]
            c_ser.validated_data["payment"],
        )

        # Return order data
        o_ser = OrderSerializer(order, context={"request": request})
        return Response(o_ser.data)


class PaymentStatesView(generics.GenericAPIView[Any]):
    def get(self, request: Request, pk: int | None = None) -> Response:
        # We don't really use the provided pk. It's just there to be compatible with oscarapi
        if pk and int(pk) != request.session.get(CHECKOUT_ORDER_ID):
            return Response(status=status.HTTP_404_NOT_FOUND)

        # Fetch the order object from the session, but only if it's pending
        pk = request.session.get(CHECKOUT_ORDER_ID)
        order = get_object_or_404(Order, pk=pk)

        # Return order status and payment states
        states = utils.list_payment_method_states(request)
        state_data = {}
        for key, state in states.items():
            ser = PaymentStateSerializer(instance=state)
            state_data[key] = ser.data

        return Response(
            {
                "order_status": order.status,
                "payment_method_states": state_data if any(state_data) else None,
            }
        )
