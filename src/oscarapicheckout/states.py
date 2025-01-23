from collections.abc import Sequence
from decimal import Decimal
from enum import UNIQUE, StrEnum, verify
from typing import Literal, Optional, TypedDict


@verify(UNIQUE)
class PaymentMethodStatus(StrEnum):
    PENDING = "Pending"
    DECLINED = "Declined"
    COMPLETE = "Complete"
    DEFERRED = "Deferred"
    CONSUMED = "Consumed"


# For backwards compat
PENDING = PaymentMethodStatus.PENDING
DECLINED = PaymentMethodStatus.DECLINED
COMPLETE = PaymentMethodStatus.COMPLETE
DEFERRED = PaymentMethodStatus.DEFERRED
CONSUMED = PaymentMethodStatus.CONSUMED


class FormPostRequiredFormDataField(TypedDict):
    key: str
    value: str


class FormPostRequiredFormData(TypedDict):
    type: Literal["form"]
    name: str
    url: str
    method: str
    fields: Sequence[FormPostRequiredFormDataField]


type RequiredAction = FormPostRequiredFormData | None


class PaymentStatus:
    status: PaymentMethodStatus
    amount: Decimal

    def __init__(self, amount: Decimal) -> None:
        self.amount = amount

    def get_required_action(self) -> RequiredAction:
        raise NotImplementedError("Subclass does not implement get_required_action()")


class SourceBoundPaymentStatus(PaymentStatus):
    def __init__(
        self,
        amount: Decimal,
        source_id: Optional[int] = None,
    ) -> None:
        super().__init__(amount)
        self.source_id = source_id


class Complete(SourceBoundPaymentStatus):
    status = PaymentMethodStatus.COMPLETE


class Deferred(SourceBoundPaymentStatus):
    status = PaymentMethodStatus.DEFERRED


class Declined(SourceBoundPaymentStatus):
    status = PaymentMethodStatus.DECLINED


class Consumed(SourceBoundPaymentStatus):
    status = PaymentMethodStatus.CONSUMED


class FormPostRequired(PaymentStatus):
    status = PaymentMethodStatus.PENDING
    form_data: FormPostRequiredFormData

    def __init__(
        self,
        amount: Decimal,
        name: str,
        url: str,
        method: str = "POST",
        fields: Sequence[FormPostRequiredFormDataField] = [],
    ) -> None:
        super().__init__(amount)
        self.form_data = FormPostRequiredFormData(
            type="form",
            name=name,
            url=url,
            method=method,
            fields=fields,
        )

    def get_required_action(self) -> RequiredAction:
        return self.form_data
