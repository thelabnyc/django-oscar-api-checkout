from django.dispatch import Signal

order_placed = Signal(providing_args=["order", "user", "request"])
order_payment_authorized = Signal(providing_args=["order"])
order_payment_declined = Signal(providing_args=["order"])
