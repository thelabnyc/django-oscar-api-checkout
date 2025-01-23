from oscar.core.loading import get_model

from ..cache import (
    BillingAddressCache,
    EmailAddressCache,
    ShippingAddressCache,
    ShippingMethodCache,
)
from .base import BaseTest

Country = get_model("address", "Country")


class EmailAddressCacheTest(BaseTest):
    def test_cache(self):
        EmailAddressCache(1).set({"email": "foo1@example.com"})
        EmailAddressCache(2).set({"email": "foo2@example.com"})
        self.assertEqual(EmailAddressCache(1).get(), {"email": "foo1@example.com"})
        self.assertEqual(EmailAddressCache(2).get(), {"email": "foo2@example.com"})


class ShippingAddressCacheTest(BaseTest):
    def test_cache(self):
        ShippingAddressCache(1).set(
            {
                "first_name": "Bart",
                "last_name": "Simpson",
                "line1": "123 Evergreen Terrace",
                "line4": "Springfield",
                "state": "NY",
                "postcode": "10001",
                "country": Country.objects.get(iso_3166_1_a3="USA"),
            }
        )
        self.assertEqual(
            ShippingAddressCache(1).get(),
            {
                "first_name": "Bart",
                "last_name": "Simpson",
                "line1": "123 Evergreen Terrace",
                "line4": "Springfield",
                "state": "NY",
                "postcode": "10001",
                "country": Country.objects.get(iso_3166_1_a3="USA"),
            },
        )


class BillingAddressCacheTest(BaseTest):
    def test_cache(self):
        BillingAddressCache(1).set(
            {
                "first_name": "Lisa",
                "last_name": "Simpson",
                "line1": "123 Evergreen Terrace",
                "line4": "Springfield",
                "state": "NY",
                "postcode": "10001",
                "country": Country.objects.get(iso_3166_1_a3="USA"),
            }
        )
        self.assertEqual(
            BillingAddressCache(1).get(),
            {
                "first_name": "Lisa",
                "last_name": "Simpson",
                "line1": "123 Evergreen Terrace",
                "line4": "Springfield",
                "state": "NY",
                "postcode": "10001",
                "country": Country.objects.get(iso_3166_1_a3="USA"),
            },
        )


class ShippingMethodCacheTest(BaseTest):
    def test_cache(self):
        ShippingMethodCache(1).set(
            {
                "code": "ups-next-day-air",
                "name": "UPS Next Day Air",
                "price": "47.00",
            }
        )
        self.assertEqual(
            ShippingMethodCache(1).get(),
            {
                "code": "ups-next-day-air",
                "name": "UPS Next Day Air",
                "price": "47.00",
            },
        )
