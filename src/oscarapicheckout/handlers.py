from django.dispatch import receiver
from oscar.core.loading import get_class
from .email import OrderMessageSender
from .settings import ORDER_STATUS_PAYMENT_DECLINED
from .signals import order_payment_authorized
import logging

logger = logging.getLogger(__name__)

order_status_changed = get_class('order.signals', 'order_status_changed')


@receiver(order_payment_authorized)
def send_order_confirmation_message(sender, order, request, **kwargs):
    OrderMessageSender(request).send_order_placed_email(order)


@receiver(order_status_changed)
def update_basket_status_upon_order_status_change(sender, order, old_status, new_status, **kwargs):
    """
    When an order transitions from "Payment Declined" to any other status, make sure
    it's associated basket is not still editable.
    """
    basket = order.basket
    if not basket:
        return

    if new_status == ORDER_STATUS_PAYMENT_DECLINED:
        return

    if not basket.can_be_edited:
        return

    logger.info("Changing status of Basket[%s] from %s to Submitted due to order status change from %s to %s.",
        basket.pk, basket.status, old_status, new_status)
    basket.submit()
