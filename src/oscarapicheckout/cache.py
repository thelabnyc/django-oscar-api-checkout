from collections.abc import Mapping
from decimal import Decimal
from typing import TYPE_CHECKING, Any, TypedDict

from django.core.cache import cache
from django.utils.module_loading import import_string
from oscar.core.loading import get_model
from rest_framework import serializers

from . import settings as pkgsettings

if TYPE_CHECKING:
    from oscar.apps.address.models import Country
else:
    Country = get_model("address", "Country")


class EmailAddressSerializer(serializers.Serializer[Any]):
    email = serializers.EmailField()


class EmailAddressCacheValue(TypedDict):
    email: str


class ShippingMethodSerializer(serializers.Serializer[Any]):
    code = serializers.CharField(max_length=128)
    name = serializers.CharField(max_length=128)
    price = serializers.DecimalField(decimal_places=2, max_digits=12)


class ShippingMethodCacheValue(TypedDict):
    code: str
    name: str
    price: Decimal


class BaseAddressCacheValue(TypedDict):
    title: str
    first_name: str
    last_name: str
    line1: str
    line2: str
    line3: str
    line4: str
    state: str
    postcode: str
    country: Country | None


class ShippingAddressCacheValue(BaseAddressCacheValue):
    phone_number: str
    notes: str


class BillingAddressCacheValue(BaseAddressCacheValue):
    pass


class AbstractCheckoutCache[
    ExternalData: Mapping[str, Any],
    StoredData: Mapping[str, Any],
]:
    serializer_class_path: str | None = None
    cache_timeout: int = 60 * 60 * 24  # 24 hours

    def __init__(self, basket_id: int, enable_validation: bool = False) -> None:
        self.basket_id = basket_id
        self.enable_validation = enable_validation

    @property
    def cache_key(self) -> str:
        return "oscarapicheckout.cache.{}.{}".format(
            self.__class__.__name__, self.basket_id
        )

    def set(self, edata: ExternalData) -> None:
        sdata = self._transform_incoming_data(edata)
        cache.set(self.cache_key, sdata, self.cache_timeout)

    def get(self) -> ExternalData:
        data = cache.get(self.cache_key)
        return self._transform_outgoing_data(data)

    def invalidate(self) -> None:
        cache.delete(self.cache_key)

    def _transform_incoming_data(self, edata: ExternalData) -> StoredData:
        sdata: StoredData = edata  # type:ignore[assignment]
        if self.enable_validation:
            serializer = self._get_serializer(edata)
            if serializer:
                serializer.is_valid(raise_exception=True)
                sdata = serializer.validated_data
        return sdata

    def _transform_outgoing_data(self, sdata: StoredData) -> ExternalData:
        return sdata  # type:ignore[return-value]

    def _get_serializer(
        self, edata: ExternalData
    ) -> serializers.Serializer[Any] | None:
        serializer_class = self._get_serializer_class()
        if serializer_class:
            return serializer_class(data=edata)
        return None

    def _get_serializer_class(self) -> type[serializers.Serializer[Any]] | None:
        if self.serializer_class_path:
            return import_string(  # type:ignore[no-any-return]
                self.serializer_class_path
            )
        return None


class AbstractCheckoutAddressCache[ExternalData: BaseAddressCacheValue](
    AbstractCheckoutCache[ExternalData, dict[str, Any]]
):
    def _transform_incoming_data(self, edata: ExternalData) -> dict[str, Any]:
        sdata: dict[str, Any] = super()._transform_incoming_data(edata)
        if sdata and "country" in sdata and hasattr(sdata["country"], "pk"):
            sdata["country"] = sdata["country"].pk
        return sdata

    def _transform_outgoing_data(self, sdata: dict[str, Any]) -> ExternalData:
        edata: ExternalData = super()._transform_outgoing_data(sdata)
        if sdata and "country" in sdata and not hasattr(sdata["country"], "pk"):
            try:
                edata["country"] = Country.objects.get(pk=sdata["country"])
            except Country.DoesNotExist:
                edata["country"] = None
        return edata


class EmailAddressCache(
    AbstractCheckoutCache[
        EmailAddressCacheValue,
        dict[str, Any],
    ],
):
    serializer_class_path = pkgsettings.CHECKOUT_CACHE_SERIALIZERS.get(
        "email_address", "oscarapicheckout.cache.EmailAddressSerializer"
    )


class ShippingAddressCache(AbstractCheckoutAddressCache[ShippingAddressCacheValue]):
    serializer_class_path = pkgsettings.CHECKOUT_CACHE_SERIALIZERS.get(
        "shipping_address", "oscarapi.serializers.checkout.ShippingAddressSerializer"
    )


class BillingAddressCache(AbstractCheckoutAddressCache[BillingAddressCacheValue]):
    serializer_class_path = pkgsettings.CHECKOUT_CACHE_SERIALIZERS.get(
        "billing_address", "oscarapi.serializers.checkout.BillingAddressSerializer"
    )


class ShippingMethodCache(
    AbstractCheckoutCache[
        ShippingMethodCacheValue,
        dict[str, Any],
    ],
):
    serializer_class_path = pkgsettings.CHECKOUT_CACHE_SERIALIZERS.get(
        "shipping_method", "oscarapicheckout.cache.ShippingMethodSerializer"
    )
