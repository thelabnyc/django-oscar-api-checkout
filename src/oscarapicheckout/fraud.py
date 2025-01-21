from datetime import timedelta
from typing import Any, Generator, Literal, Optional, Protocol
import logging

from django.http import HttpRequest
from django.utils import timezone
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _
from oscar.core.loading import get_model
from rest_framework import serializers

from . import settings

Order = get_model("order", "Order")

logger = logging.getLogger(__name__)

type CheckoutData = dict[str, Any]


class FraudRule(Protocol):
    def validate(
        self,
        data: CheckoutData,
        recaptcha_score: Optional[float],
        request: Optional[HttpRequest],
    ) -> None: ...


def get_enabled_fraud_checks() -> Generator[FraudRule, None, None]:
    for config in settings.API_CHECKOUT_FRAUD_CHECKS:
        RuleClass: type[FraudRule] = import_string(config["rule"])
        rule = RuleClass(**config.get("kwargs", {}))
        yield rule


def run_enabled_fraud_checks(
    data: CheckoutData,
    recaptcha_score: Optional[float] = None,
    request: Optional[HttpRequest] = None,
) -> None:
    for rule in get_enabled_fraud_checks():
        rule.validate(data, recaptcha_score, request)
    return None


class AddressVelocity:
    """
    Built-in example of an order fraud check. Rejects new orders if there's been
    too many orders in a rolling time window with the same billing or shipping
    address.
    """

    period: timedelta
    threshold: int

    def __init__(
        self,
        period: timedelta | None = None,
        threshold: int = 10,
    ) -> None:
        self.period = period or timedelta(hours=24)
        self.threshold = threshold

    def validate(self, data: CheckoutData, *args: Any, **kwargs: Any) -> None:
        self._validate_addr("shipping_address", data)
        self._validate_addr("billing_address", data)

    def _validate_addr(
        self,
        addr_type: Literal["shipping_address", "billing_address"],
        data: CheckoutData,
    ) -> None:
        timeframe_start = timezone.now() - self.period
        filter_args = {
            "date_placed__gte": timeframe_start,
        }
        addr_data = data[addr_type]
        for addr_field in ["line1", "line2", "line3", "line4", "postcode"]:
            if addr_field in addr_data:
                filter_key = f"{addr_type}__{addr_field}__iexact"
                filter_args[filter_key] = addr_data[addr_field]

        if "country" in addr_data:
            filter_args[f"{addr_type}__country"] = addr_data["country"]

        address_use_count = Order.objects.filter(**filter_args).count()
        if address_use_count >= self.threshold:
            logger.info("Rejected order due to address velocity rules")
            raise serializers.ValidationError(_("Order rejected."))
