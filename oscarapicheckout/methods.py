from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers
from oscar.core.loading import get_model
from . import states

PaymentEventType = get_model('order', 'PaymentEventType')
PaymentEvent = get_model('order', 'PaymentEvent')
PaymentEventQuantity = get_model('order', 'PaymentEventQuantity')
SourceType = get_model('payment', 'SourceType')
Source = get_model('payment', 'Source')
Transaction = get_model('payment', 'Transaction')


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

    def _make_payment_event(self, type_name, order, amount, reference=''):
        etype, created = PaymentEventType.objects.get_or_create(name=type_name)
        event = PaymentEvent()
        event.order = order
        event.amount = amount
        event.reference = reference
        event.event_type = etype
        event.save()
        return event

    def make_authorize_event(self, *args, **kwargs):
        return self._make_payment_event(Transaction.AUTHORISE, *args, **kwargs)

    def make_debit_event(self, *args, **kwargs):
        return self._make_payment_event(Transaction.DEBIT, *args, **kwargs)

    def make_refund_event(self, *args, **kwargs):
        return self._make_payment_event(Transaction.REFUND, *args, **kwargs)

    def make_event_quantity(self, event, line, quantity):
        return PaymentEventQuantity.objects.create(event=event, line=line, quantity=quantity)

    def get_source(self, order, reference=''):
        stype, created = SourceType.objects.get_or_create(name=self.name)
        source, created = Source.objects.get_or_create(order=order, source_type=stype)
        source.currency = order.currency
        source.reference = reference
        source.save()
        return source

    @transaction.atomic()
    def record_payment(self, request, order, amount=None, reference='', **kwargs):
        if not amount and amount != Decimal('0.00'):
            raise RuntimeError('Amount must be specified')
        return self._record_payment(request, order, amount, reference, **kwargs)

    def _record_payment(self, request, order, amount, reference, **kwargs):
        raise NotImplementedError('Subclass must implement _record_payment(request, order, amount, reference, **kwargs) method.')


class Cash(PaymentMethod):
    """
    Cash payments are an example of how to implement a payment method plug-in. It
    doesn't do anything more than record a transaction and payment source.
    """
    name = _('Cash')
    code = 'cash'

    def _record_payment(self, request, order, amount, reference, **kwargs):
        source = self.get_source(order, reference)

        amount_to_allocate = amount - source.amount_allocated
        source.allocate(amount_to_allocate, reference)

        amount_to_debit = amount - source.amount_debited
        source.debit(amount_to_debit, reference)

        event = self.make_debit_event(order, amount_to_debit, reference)
        for line in order.lines.all():
            self.make_event_quantity(event, line, line.quantity)

        return states.Complete(source.amount_debited)
