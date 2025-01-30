from decimal import Decimal
from typing import TYPE_CHECKING, Any, NotRequired, Optional, TypedDict
import logging

from django.db import transaction
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from django_stubs_ext import StrOrPromise
from oscar.core.loading import get_model
from rest_framework import serializers

from . import states

if TYPE_CHECKING:
    from oscar.apps.order.models import Line as OrderLine
    from oscar.apps.order.models import (
        Order,
        PaymentEvent,
        PaymentEventQuantity,
        PaymentEventType,
    )
    from oscar.apps.payment.models import Source, SourceType, Transaction
else:
    PaymentEventType = get_model("order", "PaymentEventType")
    PaymentEvent = get_model("order", "PaymentEvent")
    PaymentEventQuantity = get_model("order", "PaymentEventQuantity")
    SourceType = get_model("payment", "SourceType")
    Source = get_model("payment", "Source")
    Transaction = get_model("payment", "Transaction")

logger = logging.getLogger(__name__)


class PaymentMethodData(TypedDict):
    method_type: str
    enabled: NotRequired[bool]
    pay_balance: NotRequired[bool]
    amount: NotRequired[Decimal]
    reference: NotRequired[str]


class PaymentMethodSerializer[T: PaymentMethodData](serializers.Serializer[Any]):
    method_type = serializers.ChoiceField(choices=tuple())
    enabled = serializers.BooleanField(default=False)
    pay_balance = serializers.BooleanField(default=True)
    amount = serializers.DecimalField(decimal_places=2, max_digits=12, required=False)
    reference = serializers.CharField(max_length=128, default="")

    def __init__(
        self,
        *args: Any,
        method_type_choices: list[tuple[str, str]] = list(),
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.fields["method_type"] = serializers.ChoiceField(
            choices=method_type_choices
        )

    def validate(self, data: T) -> T:
        if not data["enabled"]:
            return data
        if data["pay_balance"]:
            data.pop("amount", None)  # type:ignore[arg-type]
        elif (
            "amount" not in data
            or not data["amount"]
            or data["amount"] <= Decimal("0.00")
        ):
            # Translators: User facing error message in checkout
            raise serializers.ValidationError(
                _("Amount must be greater then 0.00 or pay_balance must be enabled.")
            )
        return data


class PaymentMethod[T: PaymentMethodData]:
    # Translators: Description of payment method in checkout
    name: StrOrPromise = gettext_noop("Abstract Payment Method")
    code: str = "abstract-payment-method"
    serializer_class: type[PaymentMethodSerializer[T]] = PaymentMethodSerializer

    def _make_payment_event(
        self,
        type_name: str,
        order: "Order",
        amount: Decimal,
        reference: str = "",
    ) -> PaymentEvent:
        etype, created = PaymentEventType.objects.get_or_create(name=type_name)
        event = PaymentEvent()
        event.order = order
        event.amount = amount
        event.reference = reference if reference else ""
        event.event_type = etype
        event.save()
        return event

    def make_authorize_event(
        self,
        order: "Order",
        amount: Decimal,
        reference: str = "",
    ) -> PaymentEvent:
        return self._make_payment_event(
            type_name=Transaction.AUTHORISE,
            order=order,
            amount=amount,
            reference=reference,
        )

    def make_debit_event(
        self,
        order: "Order",
        amount: Decimal,
        reference: str = "",
    ) -> PaymentEvent:
        return self._make_payment_event(
            type_name=Transaction.DEBIT,
            order=order,
            amount=amount,
            reference=reference,
        )

    def make_refund_event(
        self,
        order: "Order",
        amount: Decimal,
        reference: str = "",
    ) -> PaymentEvent:
        return self._make_payment_event(
            type_name=Transaction.REFUND,
            order=order,
            amount=amount,
            reference=reference,
        )

    def make_event_quantity(
        self,
        event: PaymentEvent,
        line: "OrderLine",
        quantity: int,
    ) -> PaymentEventQuantity:
        return PaymentEventQuantity.objects.create(
            event=event, line=line, quantity=quantity
        )

    def get_source(
        self,
        order: "Order",
        reference: str = "",
    ) -> Source:
        stype, created = SourceType.objects.get_or_create(name=self.name)
        source, created = Source.objects.get_or_create(
            order=order, source_type=stype, reference=reference
        )
        source.currency = order.currency
        source.save()
        return source

    @transaction.atomic()
    def void_existing_payment(
        self,
        request: HttpRequest,
        order: "Order",
        method_key: str,
        state_to_void: states.PaymentStatus,
    ) -> None:
        source_id: int | None = getattr(state_to_void, "source_id", None)
        source = (
            Source.objects.filter(pk=source_id).first()
            if source_id is not None
            else None
        )
        if not source:
            logger.warning(
                "Attempted to void PaymentSource for Order[%s], MethodKey[%s], but no source was found.",
                order.number,
                method_key,
            )
            return
        source.amount_allocated = max(
            Decimal("0.00"),
            (source.amount_allocated - state_to_void.amount),
        )
        source.save()
        logger.info(
            "Voided Amount[%s] from PaymentSource[%s] for Order[%s], MethodKey[%s].",
            state_to_void.amount,
            source,
            order.number,
            method_key,
        )

    @transaction.atomic()
    def record_payment(
        self,
        request: HttpRequest,
        order: "Order",
        method_key: str,
        amount: Optional[Decimal] = None,
        reference: str = "",
        **kwargs: Any,
    ) -> states.PaymentStatus:
        if not amount and amount != Decimal("0.00"):
            raise RuntimeError("Amount must be specified")
        return self._record_payment(
            request,
            order,
            method_key,
            amount=amount,
            reference=reference,
            **kwargs,
        )

    def _record_payment(
        self,
        request: HttpRequest,
        order: "Order",
        method_key: str,
        amount: Decimal,
        reference: str,
        **kwargs: Any,
    ) -> states.PaymentStatus:
        raise NotImplementedError(
            "Subclass must implement _record_payment(request, order, method_key, amount, reference, **kwargs) method."
        )


class Cash(PaymentMethod[PaymentMethodData]):
    """
    Cash payments are an example of how to implement a payment method plug-in. It
    doesn't do anything more than record a transaction and payment source.
    """

    # Translators: Description of payment method in checkout
    name = gettext_noop("Cash")
    code = "cash"

    def _record_payment(
        self,
        request: HttpRequest,
        order: "Order",
        method_key: str,
        amount: Decimal,
        reference: str,
        **kwargs: Any,
    ) -> states.PaymentStatus:
        source = self.get_source(order, reference)

        amount_to_allocate = amount - source.amount_allocated
        source.allocate(amount_to_allocate, reference)

        amount_to_debit = amount - source.amount_debited
        source.debit(amount_to_debit, reference)

        event = self.make_debit_event(order, amount_to_debit, reference)
        for line in order.lines.all():
            self.make_event_quantity(event, line, line.quantity)

        return states.Complete(source.amount_debited, source_id=source.pk)


class PayLater(PaymentMethod[PaymentMethodData]):
    """
    The PayLater method method is similar to the Cash payment method—it doesn't
    actually authorize any payment. This method exists to differentiate two
    different types of not-really-authorized orders:

    - `Cash` is intended for use by employees when they are going to collect
        payment directly by some means other than Oscar.
    - `PayLater` is used by customers as an failover system when the normal
        payment processor is experiencing downtime. It allows a customer to
        place an order, then come back and complete the payment authorization
        later.
    """

    # Translators: Description of payment method in checkout
    name = gettext_noop("Pay Later")
    code = "pay-later"

    def _record_payment(
        self,
        request: HttpRequest,
        order: "Order",
        method_key: str,
        amount: Decimal,
        reference: str,
        **kwargs: Any,
    ) -> states.PaymentStatus:
        source = self.get_source(order, reference)
        return states.Deferred(Decimal("0.00"), source_id=source.pk)
