from django.dispatch import receiver
from .email import OrderMessageSender
from .settings import ORDER_PLACED_COMMUNICATION_TYPE_CODE
from .signals import order_payment_authorized


@receiver(order_payment_authorized)
def send_order_confirmation_message(sender, order, request, **kwargs):
    OrderMessageSender(request).send_confirmation_message(order, ORDER_PLACED_COMMUNICATION_TYPE_CODE)
