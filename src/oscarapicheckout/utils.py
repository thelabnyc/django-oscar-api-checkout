from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional, TypedDict
import base64
import pickle

from django.contrib.auth.models import AnonymousUser, User
from django.db.models import F
from django.db.models.functions import Greatest
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from oscar.core.loading import get_class, get_model
from oscarapi.basket import operations

from .settings import ORDER_STATUS_AUTHORIZED, ORDER_STATUS_PAYMENT_DECLINED
from .signals import order_payment_authorized, order_payment_declined
from .states import Complete, Consumed, Declined, PaymentMethodStatus, PaymentStatus

if TYPE_CHECKING:
    from oscar.apps.basket.models import Basket
    from oscar.apps.order.models import BillingAddress, Order, ShippingAddress
    from oscar.apps.order.utils import OrderCreator
    from oscar.apps.shipping.methods import Base as ShippingMethod
else:
    Order = get_model("order", "Order")
    OrderCreator = get_class("order.utils", "OrderCreator")

CHECKOUT_ORDER_ID = "api_checkout_pending_order_id"
CHECKOUT_PAYMENT_STEPS = "api_checkout_payment_steps"


def _session_pickle(obj: Any) -> str:
    pickled = pickle.dumps(obj)
    base64ed = base64.standard_b64encode(pickled)
    utfed = base64ed.decode("utf8")
    return utfed


def _session_unpickle(utfed: str) -> Any:
    base64ed = utfed.encode("utf8")
    pickled = base64.standard_b64decode(base64ed)
    obj = pickle.loads(pickled)
    return obj


def _update_payment_method_state(
    request: HttpRequest,
    method_key: str,
    state: PaymentStatus,
) -> None:
    states = request.session.get(CHECKOUT_PAYMENT_STEPS, {})
    states[method_key] = _session_pickle(state)
    request.session[CHECKOUT_PAYMENT_STEPS] = states
    request.session.modified = True


def _set_order_authorized(order: "Order", request: HttpRequest) -> None:
    # Set the order status
    order.set_status(ORDER_STATUS_AUTHORIZED)

    if order.basket is not None:
        # Mark the basket as submitted
        order.basket.submit()

        # Update the owner of the basket to match the order
        if order.user != order.basket.owner:
            order.basket.owner = order.user
            order.basket.save()

    # Send a signal
    order_payment_authorized.send(sender=order, order=order, request=request)


def _set_order_payment_declined(order: "Order", request: HttpRequest) -> None:
    # Set the order status
    order.set_status(ORDER_STATUS_PAYMENT_DECLINED)

    voucher_applications = order.voucherapplication_set.all()

    for voucher_application in voucher_applications:
        voucher = voucher_application.voucher

        parent = getattr(voucher, "parent", None)
        if parent:
            parent.num_orders = Greatest(F("num_orders") - 1, 0)
            parent.save(update_children=False)

        voucher.num_orders = Greatest(F("num_orders") - 1, 0)
        voucher.save()

    # Delete some related objects
    order.discounts.all().delete()
    order.line_prices.all().delete()
    voucher_applications.delete()

    if order.basket is not None:
        # Thaw the basket and put it back into the request.session so that it can be retried
        order.basket.thaw()
        operations.store_basket_in_session(order.basket, request.session)

    # Send a signal
    order_payment_declined.send(sender=order, order=order, request=request)


def _update_order_status(order: "Order", request: HttpRequest) -> None:
    states = list_payment_method_states(request)

    declined = [
        s for k, s in states.items() if s.status == PaymentMethodStatus.DECLINED
    ]
    if len(declined) > 0:
        _set_order_payment_declined(order, request)

    not_complete = [
        s for k, s in states.items() if s.status != PaymentMethodStatus.COMPLETE
    ]
    if len(not_complete) <= 0:
        # Authorized the order and consume all the payments
        _set_order_authorized(order, request)
        for key, state in states.items():
            mark_payment_method_consumed(
                order,
                request,
                key,
                state.amount,
                source_id=getattr(state, "source_id", None),
            )


def list_payment_method_states(request: HttpRequest) -> dict[str, PaymentStatus]:
    states = request.session.get(CHECKOUT_PAYMENT_STEPS, {})
    return {
        method_key: _session_unpickle(state) for method_key, state in states.items()
    }


def clear_payment_method_states(request: HttpRequest) -> None:
    request.session[CHECKOUT_PAYMENT_STEPS] = {}
    request.session.modified = True


def clear_consumed_payment_method_states(request: HttpRequest) -> None:
    curr_states = list_payment_method_states(request)
    new_states = {}
    for key, state in curr_states.items():
        if state.status != PaymentMethodStatus.CONSUMED:
            new_states[key] = state
    clear_payment_method_states(request)
    for key, state in new_states.items():
        _update_payment_method_state(request, key, state)


def update_payment_method_state(
    order: "Order",
    request: HttpRequest,
    method_key: str,
    state: PaymentStatus,
) -> None:
    _update_payment_method_state(request, method_key, state)
    _update_order_status(order, request)


def set_payment_method_states(
    order: "Order",
    request: HttpRequest,
    states: dict[str, PaymentStatus],
) -> None:
    clear_payment_method_states(request)
    for method_key, state in states.items():
        _update_payment_method_state(request, method_key, state)
    _update_order_status(order, request)


def mark_payment_method_completed(
    order: "Order",
    request: HttpRequest,
    method_key: str,
    amount: Decimal,
    source_id: Optional[int] = None,
) -> None:
    update_payment_method_state(
        order,
        request,
        method_key,
        Complete(amount, source_id=source_id),
    )


def mark_payment_method_declined(
    order: "Order",
    request: HttpRequest,
    method_key: str,
    amount: Decimal,
    source_id: Optional[int] = None,
) -> None:
    update_payment_method_state(
        order,
        request,
        method_key,
        Declined(amount, source_id=source_id),
    )


def mark_payment_method_consumed(
    order: "Order",
    request: HttpRequest,
    method_key: str,
    amount: Decimal,
    source_id: Optional[int] = None,
) -> None:
    update_payment_method_state(
        order,
        request,
        method_key,
        Consumed(amount, source_id=source_id),
    )


def get_order_ownership(
    request: HttpRequest,
    given_user: User | None,
    guest_email: str | None,
) -> tuple[User | None, str | None]:
    current_user = request.user
    if current_user and current_user.is_authenticated:
        return current_user, None
    return None, guest_email


class CheckoutCaptchaSettings(TypedDict):
    action: str
    required_score: float


def get_checkout_captcha_settings(
    request: HttpRequest,
) -> None | CheckoutCaptchaSettings:
    return None


class OrderUpdater(object):
    def update_order(
        self,
        order: "Order",
        basket: "Basket",
        order_total: Decimal,
        shipping_method: "ShippingMethod",
        shipping_charge: Decimal,
        user: Optional[User | AnonymousUser] = None,
        shipping_address: Optional["ShippingAddress"] = None,
        billing_address: Optional["BillingAddress"] = None,
        order_number: Optional[str] = None,
        status: Optional[str] = None,
        request: Optional[HttpRequest] = None,
        **kwargs: Any,
    ) -> "Order":
        """
        Similar to OrderCreator.place_order, except this updates an existing "Payment Declined" order instead
        of creating a new order.
        """
        if basket.is_empty:
            # Translators: Error message in checkout
            raise ValueError(_("Empty baskets cannot be submitted"))

        if order.status != ORDER_STATUS_PAYMENT_DECLINED:
            # Translators: Error message in checkout
            raise ValueError(
                _("Can not update an order that isn't in payment declined state.")
            )

        # Make sure there isn't another order with this number already, besides of course the
        # order we're trying to update.
        try:
            Order._default_manager.exclude(id=order.id).get(number=order_number)
        except Order.DoesNotExist:
            pass
        else:
            # Translators: Error message in checkout
            msg = _("There is already an order with number %(order_number)s") % dict(
                order_number=order_number
            )
            raise ValueError(msg)

        # Remove all the order lines and cancel and stock they allocated. We'll make new lines from the
        # basket after this.
        for order_line in order.lines.all():
            if (
                order_line.product
                and order_line.product.get_product_class().track_stock
                and order_line.stockrecord
            ):
                order_line.stockrecord.cancel_allocation(order_line.quantity)
            order_line.delete()

        # Use the built in OrderCreator, but specify a pk so that Django actually does an update instead
        # Create the actual order.Order and order.Line models
        creator = OrderCreator()
        order = creator.create_order_model(
            user,
            basket,
            shipping_address,
            shipping_method,
            shipping_charge,
            billing_address,
            order_total,
            order_number,
            status,
            id=order.id,
            request=request,
            **kwargs,
        )

        # Make new order lines to replace the ones we deleted.
        for basket_line in basket.all_lines():
            creator.create_line_models(order, basket_line)
            creator.update_stock_records(basket_line)

        # Make sure all the vouchers are still available to the user placing the order (not necessarily the
        # same as the order owner)
        voucher_user = request.user if request and request.user else user
        for voucher in basket.vouchers.select_for_update():
            available_to_user, msg = voucher.is_available_to_user(user=voucher_user)
            if not voucher.is_active() or not available_to_user:
                raise ValueError(msg)

        # Record any discounts associated with this order
        for application in basket.offer_applications:
            # Trigger any deferred benefits from offers and capture the
            # resulting message
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
            creator.create_discount_model(order, application)
            creator.record_discount(application)

        # Record voucher usage for this order
        for voucher in basket.vouchers.all():
            creator.record_voucher_usage(order, voucher, user)

        # Done! Return the order.Order model
        return order
