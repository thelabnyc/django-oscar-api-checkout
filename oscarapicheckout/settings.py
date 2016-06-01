from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def overridable(name, default=None, required=False, cast=None):
    if required:
        if not hasattr(settings, name) or not getattr(settings, name):
            raise ImproperlyConfigured("%s must be defined in Django settings" % name)
    value = getattr(settings, name, default)
    if cast:
        value = cast(value)
    return value


API_ENABLED_PAYMENT_METHODS = overridable('API_ENABLED_PAYMENT_METHODS', [
    {
        'method': 'oscarapicheckout.methods.Cash',
        'permission': 'oscarapicheckout.permissions.StaffOnly',
    }
])

ORDER_STATUS_PENDING = overridable('ORDER_STATUS_PENDING', 'Pending')
ORDER_STATUS_PAYMENT_DECLINED = overridable('ORDER_STATUS_PAYMENT_DECLINED', 'Payment Declined')
ORDER_STATUS_AUTHORIZED = overridable('ORDER_STATUS_AUTHORIZED', 'Authorized')
ORDER_STATUS_SHIPPED = overridable('ORDER_STATUS_SHIPPED', 'Shipped')
ORDER_STATUS_CANCELED = overridable('ORDER_STATUS_CANCELED', 'Canceled')

ORDER_PLACED_COMMUNICATION_TYPE_CODE = overridable('ORDER_PLACED_COMMUNICATION_TYPE_CODE', 'ORDER_PLACED')
