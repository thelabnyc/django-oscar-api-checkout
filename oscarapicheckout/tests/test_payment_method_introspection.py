from rest_framework import status
from rest_framework.reverse import reverse
from .base import BaseTest


class PaymentMethodsViewTest(BaseTest):
    def test_introspection_authenticated(self):
        self.login(is_staff=True)
        url = reverse('api-checkout-payment-methods')
        resp = self.client.get(url)
        self.assertEquals(resp.status_code, status.HTTP_200_OK)
        self.assertEquals(resp.data, {
            'credit-card': {
                'type': 'nested object',
                'required': False,
                'read_only': False,
                'label': 'Credit-card',
                'children': {
                    'enabled': {
                        'type': 'boolean',
                        'required': False,
                        'read_only': False,
                        'label': 'Enabled',
                    },
                    'pay_balance': {
                        'type': 'boolean',
                        'required': False,
                        'read_only': False,
                        'label': 'Pay balance',
                    },
                    'amount': {
                        'type': 'decimal',
                        'required': False,
                        'read_only': False,
                        'label': 'Amount',
                    },
                    'reference': {
                        'type': 'string',
                        'required': False,
                        'read_only': False,
                        'label': 'Reference',
                        'max_length': 128,
                    },
                },
            },
            'cash': {
                'type': 'nested object',
                'required': False,
                'read_only': False,
                'label': 'Cash',
                'children': {
                    'enabled': {
                        'type': 'boolean',
                        'required': False,
                        'read_only': False,
                        'label': 'Enabled',
                    },
                    'pay_balance': {
                        'type': 'boolean',
                        'required': False,
                        'read_only': False,
                        'label': 'Pay balance',
                    },
                    'amount': {
                        'type': 'decimal',
                        'required': False,
                        'read_only': False,
                        'label': 'Amount',
                    },
                    'reference': {
                        'type': 'string',
                        'required': False,
                        'read_only': False,
                        'label': 'Reference',
                        'max_length': 128,
                    },
                },
            },
        })


    def test_introspection_anonymous(self):
        url = reverse('api-checkout-payment-methods')
        resp = self.client.get(url)
        self.assertEquals(resp.status_code, status.HTTP_200_OK)
        self.assertEquals(resp.data, {
            'credit-card': {
                'type': 'nested object',
                'required': False,
                'read_only': False,
                'label': 'Credit-card',
                'children': {
                    'enabled': {
                        'type': 'boolean',
                        'required': False,
                        'read_only': False,
                        'label': 'Enabled',
                    },
                    'pay_balance': {
                        'type': 'boolean',
                        'required': False,
                        'read_only': False,
                        'label': 'Pay balance',
                    },
                    'amount': {
                        'type': 'decimal',
                        'required': False,
                        'read_only': False,
                        'label': 'Amount',
                    },
                    'reference': {
                        'type': 'string',
                        'required': False,
                        'read_only': False,
                        'label': 'Reference',
                        'max_length': 128,
                    },
                },
            },
        })
