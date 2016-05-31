import pickle
import base64
from .settings import ORDER_STATUS_AUTHORIZED, ORDER_STATUS_PAYMENT_DECLINED
from .signals import order_payment_declined, order_payment_authorized
from .states import COMPLETE, DECLINED, Complete, Declined

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


def _update_payment_method_state(session, code, state):
    states = session.get(CHECKOUT_PAYMENT_STEPS, {})
    states[code] = _session_pickle(state)
    session[CHECKOUT_PAYMENT_STEPS] = states
    session.modified = True


def _update_order_status(order, session):
    states = list_payment_method_states(session)

    declined = [s for k, s in states.items() if s.status == DECLINED]
    if len(declined) > 0:
        order.set_status(ORDER_STATUS_PAYMENT_DECLINED)
        order_payment_declined.send(sender=order, order=order)

    not_complete = [s for k, s in states.items() if s.status != COMPLETE]
    if len(not_complete) <= 0:
        order.set_status(ORDER_STATUS_AUTHORIZED)
        order_payment_authorized.send(sender=order, order=order)


def list_payment_method_states(session):
    states = session.get(CHECKOUT_PAYMENT_STEPS, {})
    return { code: _session_unpickle(state) for code, state in states.items() }


def clear_payment_method_states(session):
    session[CHECKOUT_PAYMENT_STEPS] = {}
    session.modified = True


def update_payment_method_state(order, session, code, state):
    _update_payment_method_state(session, code, state)
    _update_order_status(order, session)


def set_payment_method_states(order, session, states):
    for code, state in states.items():
        _update_payment_method_state(session, code, state)
    _update_order_status(order, session)


def mark_payment_method_completed(order, session, code, amount):
    update_payment_method_state(order, session, code, Complete(amount))


def mark_payment_method_declined(order, session, code, amount):
    update_payment_method_state(order, session, code, Declined(amount))
