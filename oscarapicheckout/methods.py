from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers
from oscar.core.loading import get_model
from . import states

SourceType = get_model('payment', 'SourceType')
Source = get_model('payment', 'Source')


class PaymentMethodSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(default=False)
    pay_balance = serializers.BooleanField(default=True)
    amount = serializers.DecimalField(
        decimal_places=2,
        max_digits=12,
        required=False)
    reference = serializers.CharField(
        max_length=128,
        default='')

    def validate(self, data):
        if not data['enabled']:
            return data

        if data['pay_balance']:
            data.pop('amount', None)
        elif 'amount' not in data or not data['amount'] or data['amount'] <= Decimal('0.00'):
            raise serializers.ValidationError(_("Amount must be greater then 0.00 or pay_balance must be enabled."))

        return data


class PaymentMethod(object):
    name = _('Abstract Payment Method')
    code = 'abstract-payment-method'
    serializer_class = PaymentMethodSerializer

    def get_source(self, order, reference=''):
        stype, created = SourceType.objects.get_or_create(name=self.name)
        source, created = Source.objects.get_or_create(order=order, source_type=stype)
        source.currency = order.currency
        source.reference = reference
        source.save()
        return source

    @transaction.atomic()
    def record_payment(self, order, amount=None, reference='', **kwargs):
        if not amount or amount <= Decimal('0.00'):
            raise RuntimeError('Amount must be specified')
        return self._record_payment(order, amount, reference, **kwargs)

    def _record_payment(self, order, amount, reference, **kwargs):
        raise NotImplementedError('Subclass must implement _record_payment(order, amount, reference, **kwargs) method.')


class Cash(PaymentMethod):
    """
    Cash payments are an example of how to implement a payment method plug-in. It
    doesn't do anything more than record a transaction and payment source.
    """
    name = _('Cash')
    code = 'cash'

    def _record_payment(self, order, amount, reference, **kwargs):
        source = self.get_source(order, reference)
        source.debit(amount, reference)
        return states.Complete(amount)
