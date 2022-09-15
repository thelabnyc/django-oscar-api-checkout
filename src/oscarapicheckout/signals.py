from django.dispatch import Signal

pre_calculate_total = Signal()

order_placed = Signal()

order_payment_authorized = Signal()

order_payment_declined = Signal()
