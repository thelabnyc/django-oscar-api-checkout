from oscar.core.loading import get_class, get_model
from oscarapi.basket import operations
from .settings import ORDER_STATUS_AUTHORIZED, ORDER_STATUS_PAYMENT_DECLINED
from .signals import order_payment_declined, order_payment_authorized
from .states import COMPLETE, DECLINED, Complete, Declined
import pickle
import base64

Order = get_model('order', 'Order')
OrderCreator = get_class('order.utils', 'OrderCreator')

CHECKOUT_ORDER_ID = 'api_checkout_pending_order_id'
CHECKOUT_PAYMENT_STEPS = 'api_checkout_payment_steps'


def _session_pickle(obj):
    pickled = pickle.dumps(obj)
    base64ed = base64.standard_b64encode(pickled)
    utfed = base64ed.decode('utf8')
    return utfed


def _session_unpickle(utfed):
    base64ed = utfed.encode('utf8')
    pickled = base64.standard_b64decode(base64ed)
    obj = pickle.loads(pickled)
    return obj


def _update_payment_method_state(request, code, state):
    states = request.session.get(CHECKOUT_PAYMENT_STEPS, {})
    states[code] = _session_pickle(state)
    request.session[CHECKOUT_PAYMENT_STEPS] = states
    request.session.modified = True


def _update_order_status(order, request):
    states = list_payment_method_states(request)

    declined = [s for k, s in states.items() if s.status == DECLINED]
    if len(declined) > 0:
        order.set_status(ORDER_STATUS_PAYMENT_DECLINED)
        order.basket.thaw()  # Thaw the basket and put it back into the request.session so that it can be retried
        operations.store_basket_in_session(order.basket, request.session)
        order_payment_declined.send(sender=order, order=order, request=request)

    not_complete = [s for k, s in states.items() if s.status != COMPLETE]
    if len(not_complete) <= 0:
        order.set_status(ORDER_STATUS_AUTHORIZED)
        order.basket.submit()  # Mark the basket as submitted
        order_payment_authorized.send(sender=order, order=order, request=request)


def list_payment_method_states(request):
    states = request.session.get(CHECKOUT_PAYMENT_STEPS, {})
    return { code: _session_unpickle(state) for code, state in states.items() }


def clear_payment_method_states(request):
    request.session[CHECKOUT_PAYMENT_STEPS] = {}
    request.session.modified = True


def update_payment_method_state(order, request, code, state):
    _update_payment_method_state(request, code, state)
    _update_order_status(order, request)


def set_payment_method_states(order, request, states):
    for code, state in states.items():
        _update_payment_method_state(request, code, state)
    _update_order_status(order, request)


def mark_payment_method_completed(order, request, code, amount):
    update_payment_method_state(order, request, code, Complete(amount))


def mark_payment_method_declined(order, request, code, amount):
    update_payment_method_state(order, request, code, Declined(amount))



class OrderUpdater(object):
    def update_order(self, order, basket, order_total,
                     shipping_method, shipping_charge, user=None,
                     shipping_address=None, billing_address=None,
                     order_number=None, status=None, **kwargs):

        if basket.is_empty:
            raise ValueError(_("Empty baskets cannot be submitted"))

        if order.status != ORDER_STATUS_PAYMENT_DECLINED:
            raise ValueError(_("Can not update an order that isn't in payment declined state."))

        try:
            Order._default_manager.exclude(id=order.id).get(number=order_number)
        except Order.DoesNotExist:
            pass
        else:
            raise ValueError(_("There is already an order with number %s") % order_number)

        # Delete some related objects
        order.discounts.all().delete()
        order.line_prices.all().delete()
        order.voucherapplication_set.all().delete()

        # Remove all the order lines and cancel and stock they allocated. We'll make new lines from the
        # basket after this.
        for order_line in order.lines.all():
            if order_line.product.get_product_class().track_stock:
                order_line.stockrecord.cancel_allocation(order_line.quantity)
            order_line.delete()

        # Use the built in OrderCreator, but specify a pk so that Django actually does an update instead
        creator = OrderCreator()
        order = creator.create_order_model(
            user, basket, shipping_address, shipping_method, shipping_charge,
            billing_address, order_total, order_number, status, id=order.id, **kwargs)

        # Make new order lines to replace the ones we deleted.
        for basket_line in basket.all_lines():
            creator.create_line_models(order, basket_line)
            creator.update_stock_records(basket_line)

        # Record any discounts associated with this order
        for application in basket.offer_applications:
            # Trigger any deferred benefits from offers and capture the
            # resulting message
            application['message'] = application['offer'].apply_deferred_benefit(basket, order, application)

            # Record offer application results
            if application['result'].affects_shipping:
                # Skip zero shipping discounts
                shipping_discount = shipping_method.discount(basket)
                if shipping_discount <= D('0.00'):
                    continue
                # If a shipping offer, we need to grab the actual discount off
                # the shipping method instance, which should be wrapped in an
                # OfferDiscount instance.
                application['discount'] = shipping_discount
            creator.create_discount_model(order, application)
            creator.record_discount(application)

        for voucher in basket.vouchers.all():
            creator.record_voucher_usage(order, voucher, user)

        return order
