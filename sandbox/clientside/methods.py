from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.core.signing import Signer
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from oscar.apps.payment.models import Transaction
from oscarapicheckout.methods import (
    PaymentMethod,
    PaymentMethodData,
    PaymentMethodSerializer,
)
from oscarapicheckout.states import (
    ClientSidePaymentRequired,
    Complete,
    Declined,
)

if TYPE_CHECKING:
    from ..order.models import Order


class ClientSideCard(PaymentMethod[PaymentMethodData]):
    """
    Example of a payment method that uses a client-side SDK (e.g. CyberSource
    Unified Checkout, Stripe Elements, Braintree Drop-in, Adyen Web Components).

    Instead of returning a form-post URL, it returns an opaque token that the
    client uses to initialize a provider-hosted JS widget.
    """

    name = _("Client-Side Card")
    code = "client-side-card"
    serializer_class = PaymentMethodSerializer[PaymentMethodData]

    def _record_payment(
        self,
        request: HttpRequest,
        order: "Order",
        method_key: str,
        amount: Decimal,
        reference: str,
        **kwargs: Any,
    ) -> ClientSidePaymentRequired:
        return ClientSidePaymentRequired(
            amount=amount,
            payment_processor="sandbox-processor",
            data={
                "amount": str(amount),
                "token": "sandbox-client-token-xyz",
                "sdk_url": "https://sandbox.example.com/sdk.js",
                "reference_number": order.number,
                "transaction_id": Signer().sign(method_key),
            },
        )

    def record_successful_authorization(
        self,
        order: "Order",
        amount: Decimal,
        reference: str,
    ) -> Complete:
        source = self.get_source(order, reference)

        source.allocate(amount, reference=reference, status="ACCEPTED")
        event = self.make_authorize_event(order, amount, reference)
        for line in order.lines.all():
            self.make_event_quantity(event, line, line.quantity)

        return Complete(amount, source_id=source.pk)

    def record_declined_authorization(
        self,
        order: "Order",
        amount: Decimal,
        reference: str,
    ) -> Declined:
        source = self.get_source(order, reference)
        source._create_transaction(Transaction.AUTHORISE, amount, reference=reference, status="DECLINED")
        return Declined(amount, source_id=source.pk)
