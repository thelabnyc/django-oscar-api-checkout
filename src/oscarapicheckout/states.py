PENDING = 'Pending'
DECLINED = 'Declined'
COMPLETE = 'Complete'
CONSUMED = 'Consumed'


class PaymentStatus(object):
    def __init__(self, amount):
        self.amount = amount

    @property
    def status(self):
        raise NotImplementedError('Subclass must implement status property')

    def get_required_action(self):
        raise NotImplementedError('Subclass does not implement get_required_action()')


class SourceBoundPaymentStatus(PaymentStatus):
    def __init__(self, amount, source_id=None):
        super().__init__(amount)
        self.source_id = source_id


class Complete(SourceBoundPaymentStatus):
    status = COMPLETE


class Declined(SourceBoundPaymentStatus):
    status = DECLINED


class Consumed(SourceBoundPaymentStatus):
    status = CONSUMED


class FormPostRequired(PaymentStatus):
    status = PENDING

    def __init__(self, amount, name, url, method='POST', fields=[]):
        super().__init__(amount)
        self.form_data = {
            'type': 'form',
            'name': name,
            'url': url,
            'method': method,
            'fields': fields,
        }

    def get_required_action(self):
        return self.form_data
