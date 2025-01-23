from decimal import Decimal

from oscar.test.factories import create_order

from ..methods import Cash, PaymentMethod, PaymentMethodSerializer
from .base import BaseTest


class PaymentMethodSerializerTest(BaseTest):
    def test_disabled_is_valid(self):
        s = PaymentMethodSerializer(
            method_type_choices=[("cash", "Cash")],
            data={
                "method_type": "cash",
                "enabled": False,
            },
        )
        self.assertTrue(s.is_valid())
        self.assertDictEqual(
            s.validated_data,
            {
                "method_type": "cash",
                "enabled": False,
                "pay_balance": True,
                "reference": "",
            },
        )

    def test_pay_balance_without_amount_is_valid(self):
        s = PaymentMethodSerializer(
            method_type_choices=[("cash", "Cash")],
            data={
                "method_type": "cash",
                "enabled": True,
                "pay_balance": True,
                "amount": "10.00",
            },
        )
        self.assertTrue(s.is_valid())
        self.assertDictEqual(
            s.validated_data,
            {
                "method_type": "cash",
                "enabled": True,
                "pay_balance": True,
                "reference": "",
            },
        )

    def test_amount_specified_is_valid(self):
        # amount specified without amount is valid
        s = PaymentMethodSerializer(
            method_type_choices=[("cash", "Cash")],
            data={
                "method_type": "cash",
                "enabled": True,
                "pay_balance": False,
                "amount": "10.00",
            },
        )
        self.assertTrue(s.is_valid())
        self.assertDictEqual(
            s.validated_data,
            {
                "method_type": "cash",
                "enabled": True,
                "pay_balance": False,
                "amount": Decimal("10.00"),
                "reference": "",
            },
        )

    def test_missing_amount_is_not_valid(self):
        s = PaymentMethodSerializer(
            method_type_choices=[("cash", "Cash")],
            data={
                "method_type": "cash",
                "enabled": True,
                "pay_balance": False,
            },
        )
        self.assertFalse(s.is_valid())

    def test_missing_method_type_is_not_valid(self):
        s = PaymentMethodSerializer(
            method_type_choices=[("cash", "Cash")],
            data={
                "enabled": True,
                "pay_balance": False,
            },
        )
        self.assertFalse(s.is_valid())

    def test_invalid_method_type_is_not_valid(self):
        s = PaymentMethodSerializer(
            method_type_choices=[("cash", "Cash")],
            data={
                "method_type": "credit-card",
                "enabled": True,
                "pay_balance": False,
            },
        )
        self.assertFalse(s.is_valid())

        s = PaymentMethodSerializer(
            method_type_choices=[],
            data={
                "method_type": "cash",
                "enabled": True,
                "pay_balance": False,
            },
        )
        self.assertFalse(s.is_valid())

        s = PaymentMethodSerializer(
            method_type_choices=["credit-card", "Credit Card"],
            data={
                "method_type": "cash",
                "enabled": True,
                "pay_balance": False,
            },
        )
        self.assertFalse(s.is_valid())


class PaymentMethodTest(BaseTest):
    def test_get_source(self):
        order = create_order()

        method = PaymentMethod()
        source = method.get_source(order, reference="12345")

        self.assertEqual(source.source_type.name, "Abstract Payment Method")
        self.assertEqual(source.order, order)
        self.assertEqual(source.currency, order.currency)
        self.assertEqual(source.reference, "12345")

        self.assertEqual(order.sources.all().count(), 1)
        self.assertEqual(order.sources.first().id, source.id)


class CashTest(BaseTest):
    def test_record_payment(self):
        order = create_order()
        state = Cash().record_payment(None, order, "cash", amount=Decimal("1.00"))

        self.assertEqual(state.status, "Complete")
        self.assertEqual(state.amount, Decimal("1.00"))

        self.assertEqual(order.sources.count(), 1)

        source = order.sources.first()
        self.assertEqual(source.currency, order.currency)
        self.assertEqual(source.amount_allocated, Decimal("1.00"))
        self.assertEqual(source.amount_debited, Decimal("1.00"))
        self.assertEqual(source.amount_refunded, Decimal("0.00"))
        self.assertEqual(source.transactions.count(), 2)

        transaction = source.transactions.get(txn_type="Authorise")
        self.assertEqual(transaction.amount, Decimal("1.00"))

        transaction = source.transactions.get(txn_type="Debit")
        self.assertEqual(transaction.amount, Decimal("1.00"))
