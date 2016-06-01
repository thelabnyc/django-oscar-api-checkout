from decimal import Decimal
from oscar.test.factories import create_order
from rest_framework import status
from rest_framework.reverse import reverse
from .base import BaseTest

from ..methods import PaymentMethodSerializer, PaymentMethod, Cash


class PaymentMethodSerializerTest(BaseTest):
    def test_disabled_is_valid(self):
        s = PaymentMethodSerializer(data={
            'enabled': False,
        })
        self.assertTrue(s.is_valid())
        self.assertEquals(s.validated_data, {
            'enabled': False,
            'pay_balance': True,
            'reference': '',
        })


    def test_pay_balance_without_amount_is_valid(self):
        s = PaymentMethodSerializer(data={
            'enabled': True,
            'pay_balance': True,
            'amount': '10.00'
        })
        self.assertTrue(s.is_valid())
        self.assertEquals(s.validated_data, {
            'enabled': True,
            'pay_balance': True,
            'reference': '',
        })


    def test_amount_specified_is_valid(self):
        # amount specified without amount is valid
        s = PaymentMethodSerializer(data={
            'enabled': True,
            'pay_balance': False,
            'amount': '10.00'
        })
        self.assertTrue(s.is_valid())
        self.assertEquals(s.validated_data, {
            'enabled': True,
            'pay_balance': False,
            'amount': Decimal('10.00'),
            'reference': '',
        })


    def test_missing_amount_is_not_valid(self):
        s = PaymentMethodSerializer(data={
            'enabled': True,
            'pay_balance': False,
        })
        self.assertFalse(s.is_valid())


class PaymentMethodTest(BaseTest):
    def test_get_source(self):
        order = create_order()

        method = PaymentMethod()
        source = method.get_source(order, reference='12345')

        self.assertEqual(source.source_type.name, 'Abstract Payment Method')
        self.assertEqual(source.order, order)
        self.assertEqual(source.currency, order.currency)
        self.assertEqual(source.reference, '12345')

        self.assertEqual(order.sources.all().count(), 1)
        self.assertEqual(order.sources.first().id, source.id)


class CashTest(BaseTest):
    def test_record_payment(self):
        order = create_order()
        state = Cash().record_payment(order, amount=Decimal('1.00'))

        self.assertEqual(state.status, 'Complete')
        self.assertEqual(state.amount, Decimal('1.00'))

        self.assertEqual(order.sources.count(), 1)

        source = order.sources.first()
        self.assertEqual(source.currency, order.currency)
        self.assertEqual(source.amount_allocated, Decimal('1.00'))
        self.assertEqual(source.amount_debited, Decimal('1.00'))
        self.assertEqual(source.amount_refunded, Decimal('0.00'))
        self.assertEqual(source.transactions.count(), 2)

        transaction = source.transactions.get(txn_type='Authorise')
        self.assertEqual(transaction.amount, Decimal('1.00'))

        transaction = source.transactions.get(txn_type='Debit')
        self.assertEqual(transaction.amount, Decimal('1.00'))
