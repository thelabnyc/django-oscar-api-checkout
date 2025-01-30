from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional, cast

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from oscar.core.loading import get_class, get_model

if TYPE_CHECKING:
    from oscar.apps.basket.models import Basket
    from oscar.apps.order.models import BillingAddress, Order, ShippingAddress
    from oscar.apps.order.signals import order_placed
    from oscar.apps.order.utils import OrderCreator
    from oscar.apps.shipping.methods import Base as ShippingMethod
else:
    Order = get_model("order", "Order")
    order_placed = get_class("order.signals", "order_placed")
    OrderCreator = object


class OrderCreatorMixin(OrderCreator):
    """
    Class mixin for oscar.apps.order.utils.OrderCreator. Handles bug that occurs when
    order ownership isn't the same as the user placing the order, but the basket contains
    a voucher which is only available to the user placing the order.
    """

    def place_order(  # type:ignore[override]
        self,
        basket: "Basket",
        total: Decimal,
        shipping_method: "ShippingMethod",
        shipping_charge: Decimal,
        user: Optional[User] = None,
        shipping_address: Optional["ShippingAddress"] = None,
        billing_address: Optional["BillingAddress"] = None,
        order_number: Optional[str] = None,
        status: Optional[str] = None,
        request: Optional[HttpRequest] = None,
        **kwargs: Any
    ) -> Order:
        """
        Placing an order involves creating all the relevant models based on the
        basket and session data.
        """
        # Make sure basket isn't empty
        if basket.is_empty:
            # Translators: User facing error message in checkout
            raise ValueError(_("Empty baskets cannot be submitted"))

        # Allocate an order number
        if not order_number:
            OrderNumberGenerator = get_class("order.utils", "OrderNumberGenerator")
            generator = OrderNumberGenerator()
            order_number = generator.order_number(basket)

        # Figure out what status the new order should be
        if not status and hasattr(settings, "OSCAR_INITIAL_ORDER_STATUS"):
            status = getattr(settings, "OSCAR_INITIAL_ORDER_STATUS")

        # Make sure there isn't already an order with this order number
        if Order._default_manager.filter(number=order_number).exists():
            # Translators: User facing error message in checkout
            raise ValueError(
                _("There is already an order with number %(order_number)s")
                % dict(order_number=order_number)
            )

        # Open a transaction so that order creation is atomic.
        with transaction.atomic():
            # Create the actual order.Order and order.Line models
            order = cast(
                Order,
                self.create_order_model(
                    user,
                    basket,
                    shipping_address,
                    shipping_method,
                    shipping_charge,
                    billing_address,
                    total,
                    order_number,
                    status,
                    request=request,
                    **kwargs
                ),
            )
            for line in basket.all_lines():
                self.create_line_models(order, line)
                self.update_stock_records(line)

            # Make sure all the vouchers in the order are active and can actually be used by the order placing user.
            voucher_user = request.user if request and request.user else user
            for voucher in basket.vouchers.select_for_update():
                available_to_user, msg = voucher.is_available_to_user(user=voucher_user)
                if not voucher.is_active() or not available_to_user:
                    raise ValueError(msg)

            # Record any discounts associated with this order
            for application in basket.offer_applications:
                # Trigger any deferred benefits from offers and capture the resulting message
                application["message"] = application["offer"].apply_deferred_benefit(
                    basket, order, application
                )
                # Record offer application results
                if application["result"].affects_shipping:
                    # Skip zero shipping discounts
                    shipping_discount = shipping_method.discount(basket)
                    if shipping_discount <= Decimal("0.00"):
                        continue
                    # If a shipping offer, we need to grab the actual discount off
                    # the shipping method instance, which should be wrapped in an
                    # OfferDiscount instance.
                    application["discount"] = shipping_discount
                self.create_discount_model(order, application)
                self.record_discount(application)

            # Record voucher usage for this order
            for voucher in basket.vouchers.all():
                self.record_voucher_usage(order, voucher, user)

        # Send signal for analytics to pick up
        order_placed.send(sender=self, order=order, user=user)

        # Done! Return the order.Order model
        return order
