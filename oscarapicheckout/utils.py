from collections.abc import Callable
from decimal import Decimal
from functools import cache
from typing import Any, TypedDict
import base64
import logging
import pickle

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser, User
from django.db import transaction
from django.db.models import F, Sum
from django.db.models.functions import Greatest
from django.http import HttpRequest
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _
from oscar.core.loading import get_class, get_model
from oscar.core.prices import Price
from oscarapi.basket import operations

from . import settings
from .settings import ORDER_STATUS_AUTHORIZED, ORDER_STATUS_PAYMENT_DECLINED
from .signals import order_payment_authorized, order_payment_declined
from .states import Complete, Consumed, Declined, PaymentMethodStatus, PaymentStatus

Basket = get_model("basket", "Basket")
Order = get_model("order", "Order")
ShippingAddress = get_model("order", "ShippingAddress")
BillingAddress = get_model("order", "BillingAddress")
Source = get_model("payment", "Source")

OrderCreator = get_class("order.utils", "OrderCreator")
ShippingMethod = get_class("shipping.methods", "Base")

CHECKOUT_PAYMENT_STEPS = "api_checkout_payment_steps"

logger = logging.getLogger(__name__)


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
    order_id: int | None = None,
) -> None:
    # Stamping happens here, at the only place a state enters the session, so
    # that no caller can leave one unowned. An unowned state is treated as a
    # legacy pickle, which is the lenient branch -- so a forgotten stamp would
    # silently re-open cross-order reuse rather than fail.
    if order_id is not None:
        state.order_id = order_id
    states = request.session.get(CHECKOUT_PAYMENT_STEPS, {})
    states[method_key] = _session_pickle(state)
    request.session[CHECKOUT_PAYMENT_STEPS] = states
    request.session.modified = True


def payment_state_belongs_to_order(state: PaymentStatus, order: Order) -> bool:
    """
    Is this payment state safe to reuse while placing the given order?

    States live in the session and outlive the checkout that created them, so a
    state can describe money taken against an entirely different order. Applying
    one to this order credits it with a payment it never received.

    States pickled before ``order_id`` existed carry no stamp; for those the
    Source they allocated is the only available evidence of ownership. An
    un-stamped state with no Source is only accepted when it has money behind
    it to protect: a PENDING state has taken none yet, and the payload it
    carries names the order it was minted for, so replaying it onto this order
    would route the customer's payment elsewhere. Re-recording it costs a
    round trip; recycling it costs the payment.
    """
    if state.order_id is not None:
        return bool(state.order_id == order.id)
    if state.source_id is None:
        return state.status != PaymentMethodStatus.PENDING
    return Source.objects.filter(pk=state.source_id, order_id=order.id).exists()


def warn_foreign_payment_state(
    order: Order,
    method_key: str,
    state: PaymentStatus,
) -> None:
    source = Source.objects.filter(pk=state.source_id).select_related("order").first() if state.source_id is not None else None
    foreign_order_number: str | None
    if source is not None:
        foreign_order_number = source.order.number
    else:
        foreign_order = Order._default_manager.filter(pk=state.order_id).first() if state.order_id else None
        foreign_order_number = foreign_order.number if foreign_order else None
    # method_key is client-supplied, so %r rather than %s: a key carrying CR/LF
    # would otherwise forge log lines. Source.reference is deliberately not
    # logged -- plugins put gateway tokens in it, and this warning is expected
    # to fire for ordinary stale sessions after an upgrade.
    logger.warning(
        "Disregarded payment state for MethodKey[%r], Amount[%s], SourceID[%s] belonging to Order[%s] while working on Order[%s].",
        method_key,
        state.amount,
        state.source_id,
        foreign_order_number,
        order.number,
    )


def drop_foreign_payment_method_states(order: Order, request: HttpRequest) -> None:
    curr_states = list_payment_method_states(request)
    kept_states = {}
    for key, state in curr_states.items():
        if payment_state_belongs_to_order(state, order):
            kept_states[key] = state
        else:
            warn_foreign_payment_state(order, key, state)
    if len(kept_states) == len(curr_states):
        return
    clear_payment_method_states(request)
    for key, state in kept_states.items():
        _update_payment_method_state(request, key, state)


def _set_order_authorized(order: Order, request: HttpRequest) -> None:
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


def decline_order_payment(
    order: Order,
    request: HttpRequest,
    internal_error: bool = False,
) -> None:
    """
    Public entry point for declining an order's payment.

    Exposed because the ``internal_error`` flag is part of the
    ``order_payment_declined`` contract that downstream projects must handle,
    and because subclasses of the checkout views need a supported way to run
    the same teardown.
    """
    _set_order_payment_declined(order, request, internal_error=internal_error)


def _set_order_payment_declined(
    order: Order,
    request: HttpRequest,
    internal_error: bool = False,
) -> None:
    """
    Decline the order's payment and thaw its basket so it can be retried.

    ``internal_error`` marks exactly one thing: the request raised while
    payment was being recorded, so the decline is a recovery step rather than a
    verdict. Receivers use it to suppress customer-facing decline messaging,
    since no processor rejected anything. It is deliberately narrow -- a
    shortfall found by the authorization guard is a genuine decline the
    customer must act on, and sends ``False``.
    """
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
    order_payment_declined.send(
        sender=order,
        order=order,
        request=request,
        internal_error=internal_error,
    )


def get_order_authorized_amount(order: Order) -> Decimal:
    """
    How much money is actually recorded against this order?

    Used as the floor for authorizing an order: the session's payment states
    describe what checkout believed it collected, which is not evidence that
    anything was collected against *this* order.

    This is a floor, not a reconciliation. Retries record additional sources, so
    the sum may legitimately exceed the order total; only the short side matters.

    Counts ``Source.amount_allocated`` only. A payment method that debits without
    allocating records nothing here and must supply its own calculator via
    ``ORDER_AUTHORIZED_AMOUNT_CALCULATOR``; amount_debited is not added by
    default because voiding a payment only decrements amount_allocated.

    A replacement must also count authorizations that are pending manual review,
    otherwise orders deliberately held for review are declined.

    The sum is currency-blind: every Source on the order is counted at face
    value against ``order.total_incl_tax``. ``PaymentMethod.get_source()``
    stamps the order's own currency, so in-tree methods are consistent by
    construction, but a store recording Sources in more than one currency must
    supply its own calculator.
    """
    total = order.sources.all().aggregate(total=Sum("amount_allocated"))["total"]
    return Decimal(total or "0.00")


@cache
def _import_authorized_amount_calc(dotted_path: str) -> Callable[[Order], Decimal]:
    return import_string(dotted_path)  # type:ignore[no-any-return]


def _get_authorized_amount_calc() -> Callable[[Order], Decimal]:
    calculator = settings.ORDER_AUTHORIZED_AMOUNT_CALCULATOR
    if callable(calculator):
        return calculator
    return _import_authorized_amount_calc(calculator)


def _update_order_status(order: Order, request: HttpRequest) -> None:
    # Filter here rather than trusting callers. This is the choke point every
    # path reaches -- including out-of-band processor callbacks, which resolve
    # the order from their own payload and never pass through the checkout
    # views -- so it is the only place the ownership rule holds for everyone.
    all_states = list_payment_method_states(request)
    states = {}
    for key, state in all_states.items():
        if payment_state_belongs_to_order(state, order):
            states[key] = state
        else:
            warn_foreign_payment_state(order, key, state)

    declined = [s for k, s in states.items() if s.status == PaymentMethodStatus.DECLINED]
    not_complete = [s for k, s in states.items() if s.status != PaymentMethodStatus.COMPLETE]
    if len(declined) > 0:
        _set_order_payment_declined(order, request)
    elif len(not_complete) <= 0:
        authorized_amount = _get_authorized_amount_calc()(order)
        if authorized_amount < order.total_incl_tax:
            # Backed means "allocated", not "has a Source row": get_source()
            # creates the row before any money moves, and the floor above sums
            # allocations, so existence alone would credit a method that
            # recorded nothing.
            backed_source_ids = set(order.sources.filter(amount_allocated__gt=0).values_list("id", flat=True))
            unbacked = {key: state for key, state in states.items() if state.source_id not in backed_source_ids}
            logger.error(
                "Refusing to authorize Order[%s]: payments recorded against it total %s, but the order totals %s. Methods with nothing allocated: %r.",
                order.number,
                authorized_amount,
                order.total_incl_tax,
                sorted(unbacked.keys()),
            )
            # Decline the states with nothing recorded behind them, so the
            # client shows a decline and a retry re-records only those methods.
            # Declining a state that did allocate would make the retry take a
            # second hold for the same money. If every state is backed, the
            # shortfall can't be attributed, so decline them all rather than
            # leave the order stuck in a state no retry can clear.
            states_to_decline = unbacked if len(unbacked) > 0 else states
            # Written directly to avoid re-entering this function.
            for key, state in states_to_decline.items():
                declined_state = Declined(state.amount, source_id=state.source_id)
                _update_payment_method_state(request, key, declined_state, order_id=order.id)
            _set_order_payment_declined(order, request)
            return
        # Authorized the order and consume all the payments
        _set_order_authorized(order, request)
        for key, state in states.items():
            mark_payment_method_consumed(
                order,
                request,
                key,
                state.amount,
                source_id=state.source_id,
            )


def list_payment_method_states(request: HttpRequest) -> dict[str, PaymentStatus]:
    states = request.session.get(CHECKOUT_PAYMENT_STEPS, {})
    return {method_key: _session_unpickle(state) for method_key, state in states.items()}


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
    order: Order,
    request: HttpRequest,
    method_key: str,
    state: PaymentStatus,
) -> None:
    _update_payment_method_state(request, method_key, state, order_id=order.id)
    _update_order_status(order, request)


def set_payment_method_states(
    order: Order,
    request: HttpRequest,
    states: dict[str, PaymentStatus],
) -> None:
    clear_payment_method_states(request)
    for method_key, state in states.items():
        _update_payment_method_state(request, method_key, state, order_id=order.id)
    _update_order_status(order, request)


def mark_payment_method_completed(
    order: Order,
    request: HttpRequest,
    method_key: str,
    amount: Decimal,
    source_id: int | None = None,
) -> None:
    update_payment_method_state(
        order,
        request,
        method_key,
        Complete(amount, source_id=source_id),
    )


def mark_payment_method_declined(
    order: Order,
    request: HttpRequest,
    method_key: str,
    amount: Decimal,
    source_id: int | None = None,
) -> None:
    update_payment_method_state(
        order,
        request,
        method_key,
        Declined(amount, source_id=source_id),
    )


def mark_payment_method_consumed(
    order: Order,
    request: HttpRequest,
    method_key: str,
    amount: Decimal,
    source_id: int | None = None,
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


class OrderUpdater:
    def update_order(
        self,
        order: Order,
        basket: Basket,
        order_total: Price,
        shipping_method: ShippingMethod,
        shipping_charge: Price,
        user: User | AnonymousUser | None = None,
        shipping_address: ShippingAddress | None = None,
        billing_address: BillingAddress | None = None,
        order_number: str | None = None,
        status: str | None = None,
        request: HttpRequest | None = None,
        **kwargs: Any,
    ) -> Order:
        """
        Similar to OrderCreator.place_order, except this updates an existing "Payment Declined" order instead
        of creating a new order.
        """
        if basket.is_empty:
            # Translators: Error message in checkout
            raise ValueError(_("Empty baskets cannot be submitted"))

        if order.status != ORDER_STATUS_PAYMENT_DECLINED:
            # Translators: Error message in checkout
            raise ValueError(_("Can not update an order that isn't in payment declined state."))

        # Make sure there isn't another order with this number already, besides of course the
        # order we're trying to update.
        try:
            Order._default_manager.exclude(id=order.id).get(number=order_number)
        except Order.DoesNotExist:
            pass
        else:
            # Translators: Error message in checkout
            msg = _("There is already an order with number %(order_number)s") % {"order_number": order_number}
            raise ValueError(msg)

        if order_number is None:
            raise ValueError("order_number is required")
        order_user: AbstractBaseUser | None = user if isinstance(user, AbstractBaseUser) else None
        creator = OrderCreator()

        # Wrap the update in a transaction so that a failure during line/stock
        # creation rolls back the freshly written voucher-usage and discount
        # rows, mirroring the atomic guarantee of OrderCreatorMixin.place_order.
        with transaction.atomic():
            # Remove all the order lines and cancel and stock they allocated. We'll make new lines from the
            # basket after this.
            for order_line in order.lines.all():
                product_class = order_line.product.get_product_class() if order_line.product else None
                if product_class and product_class.track_stock and order_line.stockrecord:
                    order_line.stockrecord.cancel_allocation(order_line.quantity)
                order_line.delete()

            # Use the built in OrderCreator, but specify a pk so that Django actually does an update instead
            # of an insert on the order.Order model.
            order = creator.create_order_model(
                order_user,
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
                application["message"] = application["offer"].apply_deferred_benefit(basket, order, application)

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

            # Make new order lines to replace the ones we deleted. Done last so that
            # create_line_discount_models can link each OrderLine to the OrderDiscount
            # records created above.
            for basket_line in basket.all_lines():
                creator.create_line_models(order, basket_line)
                creator.update_stock_records(basket_line)

        # Done! Return the order.Order model
        return order
