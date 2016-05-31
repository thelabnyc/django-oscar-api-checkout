from django.dispatch import Signal

order_placed = Signal(providing_args=["order", "user", "request"])
