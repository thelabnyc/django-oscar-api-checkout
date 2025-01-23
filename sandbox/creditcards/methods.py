from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.core.signing import Signer
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from oscar.apps.payment.models import Transaction
from rest_framework.reverse import reverse

from oscarapicheckout.methods import PaymentMethod, PaymentMethodSerializer
from oscarapicheckout.states import (
    Complete,
    Declined,
    FormPostRequired,
    FormPostRequiredFormDataField,
)

if TYPE_CHECKING:
    from ..order.models import Order


class CreditCard(PaymentMethod):
    """
    This is an example of how to implement a payment method that required some off-site
    interaction, like Cybersource Secure Acceptance, for example. It returns a pending
    status initially that requires the client app to make a form post, which in-turn
    redirects back to us. This is a common pattern in PCI SAQ A-EP ecommerce sites.
    """

    name = _("Credit Card")
    code = "credit-card"
    serializer_class = PaymentMethodSerializer

    def _record_payment(
        self,
        request: HttpRequest,
        order: "Order",
        method_key: str,
        amount: Decimal,
        reference: str,
        **kwargs: Any,
    ) -> FormPostRequired:
        """Payment Step 1"""
        fields: list[FormPostRequiredFormDataField] = [
            {
                "key": "amount",
                "value": str(amount),
            },
            {
                "key": "reference_number",
                "value": order.number,
            },
            {
                "key": "transaction_id",
                "value": Signer().sign(method_key),
            },
        ]
        # Return a response showing we need to post some fields to the given
        # URL to finishing processing this payment method
        return FormPostRequired(
            amount=amount,
            name="get-token",
            url=reverse("creditcards-get-token"),
            fields=fields,
        )

    def require_authorization_post(
        self, order: "Order", method_key: str, amount: Decimal
    ) -> FormPostRequired:
        """Payment Step 2"""
        fields: list[FormPostRequiredFormDataField] = [
            {
                "key": "amount",
                "value": str(amount),
            },
            {
                "key": "reference_number",
                "value": order.number,
            },
            {
                "key": "transaction_id",
                "value": Signer().sign(method_key),
            },
        ]
        return FormPostRequired(
            amount=amount,
            name="authorize",
            url=reverse("creditcards-authorize"),
            fields=fields,
        )

    def record_successful_authorization(
        self,
        order: "Order",
        amount: Decimal,
        reference: str,
    ) -> Complete:
        """Payment Step 3 Succeeded"""
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
        """Payment Step 3 Failed"""
        source = self.get_source(order, reference)
        source._create_transaction(
            Transaction.AUTHORISE, amount, reference=reference, status="DECLINED"
        )
        return Declined(amount, source_id=source.pk)
