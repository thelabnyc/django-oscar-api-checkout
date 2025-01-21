from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from oscar.core.loading import get_class, get_model
from rest_framework import serializers

from .. import fraud
from .base import BaseTest

Order = get_model("order", "Order")
ShippingAddress = get_model("order", "ShippingAddress")
Basket = get_model("basket", "Basket")
Default = get_class("partner.strategy", "Default")
OrderCreator = get_class("order.utils", "OrderCreator")
Country = get_model("address", "Country")


class AddressVelocityTest(BaseTest):
    def test_validate_address_velocity(self):
        # Create shipping address data
        address_data = {
            "title": "Mr",
            "first_name": "John",
            "last_name": "Doe",
            "line1": "123 Test St",
            "line2": "Test Building",
            "line3": "Test Floor",
            "line4": "Test City",
            "state": "Test State",
            "postcode": "TEST123",
            "country": Country.objects.get(pk="US"),
            "phone_number": "1234567890",
        }
        checkout_data = {
            "shipping_address": address_data,
            "billing_address": address_data,
        }

        # Address should pass check at first
        fraud.run_enabled_fraud_checks(checkout_data)

        # Create fake test orders with the same shipping address data
        for i in range(10):  # Create 10 orders
            # Create a fake test order with the specified shipping address
            Order.objects.create(
                number=str(1 + i),
                currency="USD",
                total_incl_tax=Decimal("100.00"),
                total_excl_tax=Decimal("90.00"),
                shipping_address=ShippingAddress.objects.create(**address_data),
                date_placed=timezone.now() - timedelta(hours=23),
            )

        # Address should now fail the fraud check
        with self.assertRaises(serializers.ValidationError):
            fraud.run_enabled_fraud_checks(checkout_data)
