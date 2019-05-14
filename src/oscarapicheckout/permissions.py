class PaymentMethodPermission(object):
    def is_permitted(self, request=None, user=None):
        raise NotImplementedError('Class must implement is_method_permitted(request=None, user=None)')


class Public(PaymentMethodPermission):
    def is_permitted(self, request=None, user=None):
        return True


class StaffOnly(PaymentMethodPermission):
    def is_permitted(self, request=None, user=None):
        return (user and user.is_authenticated and user.is_staff)


class CustomerOnly(PaymentMethodPermission):
    def is_permitted(self, request=None, user=None):
        return (user is None or not user.is_authenticated or (user.is_authenticated and not user.is_staff))
