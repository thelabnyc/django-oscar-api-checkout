from django.dispatch import Signal

pre_calculate_total = Signal(providing_args=["basket"])
order_placed = Signal(providing_args=["order", "user", "request"])
order_payment_authorized = Signal(providing_args=["order", "request"])
order_payment_declined = Signal(providing_args=["order", "request"])
