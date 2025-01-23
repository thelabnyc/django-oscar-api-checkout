from typing import Any, Optional, TypedDict

from django.conf import settings


def overridable(name: str, default: Optional[Any] = None) -> Any:
    return getattr(settings, name, default)


class PaymentMethodConfig(TypedDict):
    method: str
    permission: str
    method_kwargs: dict[str, Any]
    permission_kwargs: dict[str, Any]


class FraudRuleConfig(TypedDict):
    rule: str
    kwargs: dict[str, Any]


API_ENABLED_PAYMENT_METHODS: list[PaymentMethodConfig] = overridable(
    "API_ENABLED_PAYMENT_METHODS",
    [
        {
            "method": "oscarapicheckout.methods.Cash",
            "permission": "oscarapicheckout.permissions.StaffOnly",
            "method_kwargs": {},
            "permission_kwargs": {},
        }
    ],
)
API_MAX_PAYMENT_METHODS: int = overridable("API_MAX_PAYMENT_METHODS", 0)
API_CHECKOUT_CAPTCHA: str | bool = overridable(
    "API_CHECKOUT_CAPTCHA",
    "oscarapicheckout.utils.get_checkout_captcha_settings",
)
API_CHECKOUT_FRAUD_CHECKS: list[FraudRuleConfig] = overridable(
    "API_CHECKOUT_FRAUD_CHECKS",
    [],
)

ORDER_STATUS_PENDING: str = overridable("ORDER_STATUS_PENDING", "Pending")
ORDER_STATUS_PAYMENT_DECLINED: str = overridable(
    "ORDER_STATUS_PAYMENT_DECLINED", "Payment Declined"
)
ORDER_STATUS_AUTHORIZED: str = overridable("ORDER_STATUS_AUTHORIZED", "Authorized")
ORDER_STATUS_SHIPPED: str = overridable("ORDER_STATUS_SHIPPED", "Shipped")
ORDER_STATUS_CANCELED: str = overridable("ORDER_STATUS_CANCELED", "Canceled")

ORDER_OWNERSHIP_CALCULATOR: str = overridable(
    "ORDER_OWNERSHIP_CALCULATOR",
    "oscarapicheckout.utils.get_order_ownership",
)

CHECKOUT_CACHE_SERIALIZERS: dict[str, str] = overridable(
    "CHECKOUT_CACHE_SERIALIZERS",
    {},
)
