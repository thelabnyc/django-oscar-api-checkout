from decimal import Decimal as D
from django.contrib.auth.models import User
from oscar.core.loading import get_model
from oscar.test import factories
from rest_framework import status
from rest_framework.reverse import reverse
from ..signals import pre_calculate_total, order_placed, order_payment_authorized
from .base import BaseTest
import mock

Order = get_model('order', 'Order')
Basket = get_model('basket', 'Basket')


class CheckoutAPITest(BaseTest):

    def test_minimal_cash_order(self):
        self.login(is_staff=True)

        # Place a cash order
        basket_id = self._prepare_basket()
        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'cash': {
                'enabled': True,
                'pay_balance': True,
            }
        }
        order_resp = self._checkout(data)
        self.assertEqual(order_resp.status_code, status.HTTP_200_OK)

        # Fetch payment states
        states_resp = self.client.get(order_resp.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Authorized')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['status'], 'Complete')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['amount'], '10.00')
        self.assertIsNone(states_resp.data['payment_method_states']['cash']['required_action'])
        self.assertPaymentSource(order_resp.data['number'], 'Cash', allocated=D('10.00'), debited=D('10.00'))


    def test_out_of_stock_errors(self):
        self.login(is_staff=True)

        # Create a product with 4 items in stock, but 2 already allocated to other orders.
        product = self._create_product()
        product.product_class.track_stock = True
        product.product_class.save()
        stockrecord = product.stockrecords.first()
        stockrecord.num_in_stock = 4
        stockrecord.num_allocated = 2
        stockrecord.save()

        # Create a basket
        basket_id = self._get_basket_id()

        # Try to add 3 of the product, make sure it errors
        resp = self._add_to_basket(product.id, quantity=3)
        self.assertEqual(resp.status_code, status.HTTP_406_NOT_ACCEPTABLE)
        self.assertEqual(resp.data['reason'], 'a maximum of 2 can be bought')

        # Reduce the quantity from 3 to 2 and it should work
        resp = self._add_to_basket(product.id, quantity=2)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['total_excl_tax'], '20.00')

        # After the product is already in the basket, someone else bought one more of the items, meaning you can only buy 1.
        stockrecord.num_allocated += 1
        stockrecord.save()

        # Now, try and checkout. Make sure it errors (since your basket has 2 of the item, but only 1 more exists)
        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'cash': {
                'enabled': True,
                'pay_balance': True,
            }
        }
        order_resp = self._checkout(data)
        self.assertEqual(order_resp.status_code, status.HTTP_406_NOT_ACCEPTABLE)
        self.assertEqual(order_resp.data['basket'], [
            "'My Product' is no longer available to buy (a maximum of 1 can be bought). Please adjust your basket to continue.",
        ])

        # Next, make the product completely out of stock.
        stockrecord.num_allocated += 1
        stockrecord.save()

        # Try and checkout again without changing anything. Make sure it errors (since your basket has 2 of the item, but no more exists)
        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'cash': {
                'enabled': True,
                'pay_balance': True,
            }
        }
        order_resp = self._checkout(data)
        self.assertEqual(order_resp.status_code, status.HTTP_406_NOT_ACCEPTABLE)
        self.assertEqual(order_resp.data['basket'], [
            "'My Product' is no longer available to buy (no stock available). Please adjust your basket to continue.",
        ])

        # Increase the stock level so that 1 is available.
        stockrecord.num_in_stock += 1
        stockrecord.save()

        # Reduce the basket quantity from 2 to 1.
        resp = self._add_to_basket(product.id, quantity=-1)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['total_excl_tax'], '10.00')

        # Try and checkout again once more. This time it should work.
        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'cash': {
                'enabled': True,
                'pay_balance': True,
            }
        }
        order_resp = self._checkout(data)
        self.assertEqual(order_resp.status_code, status.HTTP_200_OK)

        # Fetch payment states. Make sure the order went through.
        states_resp = self.client.get(order_resp.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Authorized')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['status'], 'Complete')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['amount'], '10.00')
        self.assertIsNone(states_resp.data['payment_method_states']['cash']['required_action'])
        self.assertPaymentSource(order_resp.data['number'], 'Cash', allocated=D('10.00'), debited=D('10.00'))


    def test_signal_ordering(self):
        self.login(is_staff=True)

        _test = {'last_signal_called': None}

        def handle_pre_calculate_total(*args, **kwargs):
            self.assertEqual(_test['last_signal_called'], None)
            _test['last_signal_called'] = 'pre_calculate_total'

        def handle_order_placed(*args, **kwargs):
            self.assertEqual(_test['last_signal_called'], 'pre_calculate_total')
            _test['last_signal_called'] = 'order_placed'

        def handle_order_payment_authorized(*args, **kwargs):
            self.assertEqual(_test['last_signal_called'], 'order_placed')
            _test['last_signal_called'] = 'order_payment_authorized'

        pre_calculate_total.connect(handle_pre_calculate_total)
        order_placed.connect(handle_order_placed)
        order_payment_authorized.connect(handle_order_payment_authorized)

        # Make a basket
        basket_id = self._get_basket_id()
        product = self._create_product(price=D('5.00'))
        resp = self._add_to_basket(product.id)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # Checkout
        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'cash': {
                'enabled': True,
                'pay_balance': True,
            }
        }
        order_resp = self._checkout(data)
        self.assertEqual(order_resp.status_code, status.HTTP_200_OK)

        # Make sure order_payment_authorized was the last signal called, thereby asserting the entire chain's order
        self.assertEqual(_test['last_signal_called'], 'order_payment_authorized')

        # Fetch payment states
        states_resp = self.client.get(order_resp.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Authorized')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['status'], 'Complete')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['amount'], '5.00')
        self.assertIsNone(states_resp.data['payment_method_states']['cash']['required_action'])
        self.assertPaymentSource(order_resp.data['number'], 'Cash', allocated=D('5.00'), debited=D('5.00'))

        # Cleanup signal handlers
        pre_calculate_total.disconnect(handle_pre_calculate_total)
        order_placed.disconnect(handle_order_placed)
        order_payment_authorized.disconnect(handle_order_payment_authorized)


    def test_invalid_email_anon_user(self):
        basket_id = self._prepare_basket()
        data = self._get_checkout_data(basket_id)
        data['guest_email'] = ''
        data['payment'] = {
            'credit-card': {
                'enabled': True,
                'pay_balance': True,
            }
        }
        resp = self._checkout(data)
        self.assertEqual(resp.status_code, status.HTTP_406_NOT_ACCEPTABLE)
        self.assertEqual(resp.data['non_field_errors'][0], 'Guest email is required for anonymous checkouts')


    def test_invalid_email_authed_user(self):
        self.login(is_staff=True, email=None)
        basket_id = self._prepare_basket()
        data = self._get_checkout_data(basket_id)
        data['guest_email'] = ''
        data['payment'] = {
            'credit-card': {
                'enabled': True,
                'pay_balance': True,
            }
        }
        resp = self._checkout(data)
        self.assertEqual(resp.status_code, status.HTTP_406_NOT_ACCEPTABLE)
        self.assertEqual(resp.data['non_field_errors'][0], 'Email address is required.')


    def test_invalid_basket(self):
        self.login(is_staff=True)
        basket_id = self._prepare_basket()

        data = self._get_checkout_data(basket_id + 1)
        resp = self._checkout(data)
        self.assertEqual(resp.status_code, status.HTTP_406_NOT_ACCEPTABLE)
        self.assertEqual(resp.data['basket'][0], 'Invalid hyperlink - Object does not exist.')


    def test_no_payment_methods_provided(self):
        self.login(is_staff=True)
        basket_id = self._prepare_basket()

        data = self._get_checkout_data(basket_id)
        data.pop('payment', None)
        resp = self._checkout(data)
        self.assertEqual(resp.status_code, status.HTTP_406_NOT_ACCEPTABLE)
        self.assertEqual(resp.data['payment'][0], 'This field is required.')


    def test_no_payment_methods_selected(self):
        self.login(is_staff=True)
        basket_id = self._prepare_basket()

        data = self._get_checkout_data(basket_id)
        data['payment'] = {}
        resp = self._checkout(data)
        self.assertEqual(resp.status_code, status.HTTP_406_NOT_ACCEPTABLE)
        self.assertEqual(resp.data['payment']['non_field_errors'][0], 'At least one payment method must be enabled.')


    def test_no_payment_methods_enabled(self):
        self.login(is_staff=True)
        basket_id = self._prepare_basket()

        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'cash': {
                'enabled': False
            }
        }
        resp = self._checkout(data)
        self.assertEqual(resp.status_code, status.HTTP_406_NOT_ACCEPTABLE)
        self.assertEqual(resp.data['payment']['non_field_errors'][0], 'At least one payment method must be enabled.')


    def test_no_payment_amount_provided(self):
        self.login(is_staff=True)
        basket_id = self._prepare_basket()

        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'cash': {
                'enabled': True,
                'pay_balance': False,
            }
        }
        resp = self._checkout(data)
        self.assertEqual(resp.status_code, status.HTTP_406_NOT_ACCEPTABLE)
        self.assertEqual(resp.data['payment']['cash']['non_field_errors'][0], 'Amount must be greater then 0.00 or pay_balance must be enabled.')

        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'cash': {
                'enabled': True,
                'pay_balance': False,
                'amount': '0.00'
            }
        }
        resp = self._checkout(data)
        self.assertEqual(resp.status_code, status.HTTP_406_NOT_ACCEPTABLE)
        self.assertEqual(resp.data['payment']['cash']['non_field_errors'][0], 'Amount must be greater then 0.00 or pay_balance must be enabled.')


    def test_provided_payment_method_not_permitted(self):
        basket_id = self._prepare_basket()

        # Cash payments not allowed since user isn't staff
        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'cash': {
                'enabled': True,
                'pay_balance': True,
            }
        }
        resp = self._checkout(data)
        self.assertEqual(resp.status_code, status.HTTP_406_NOT_ACCEPTABLE)
        self.assertEqual(resp.data['payment']['non_field_errors'][0], 'At least one payment method must be enabled.')


    def test_free_product(self):
        self.login(is_staff=True)

        # Make a basket that will cost nothing
        basket_id = self._get_basket_id()
        product = self._create_product(price=D('0.00'))
        resp = self._add_to_basket(product.id)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # Checkout
        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'cash': {
                'enabled': True,
            }
        }
        order_resp = self._checkout(data)
        self.assertEqual(order_resp.status_code, status.HTTP_200_OK)

        # Fetch payment states
        states_resp = self.client.get(order_resp.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Authorized')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['status'], 'Complete')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['amount'], '0.00')
        self.assertIsNone(states_resp.data['payment_method_states']['cash']['required_action'])
        self.assertPaymentSource(order_resp.data['number'], 'Cash')


    def test_payment_method_requiring_form_post(self):
        basket_id = self._prepare_basket()

        # Select credit-card auth, which requires two additional form posts from the client
        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'credit-card': {
                'enabled': True,
                'pay_balance': True,
            }
        }
        order_resp = self._checkout(data)
        self.assertEqual(order_resp.status_code, status.HTTP_200_OK)

        # Fetch payment states
        states_resp = self.client.get(order_resp.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['amount'], '10.00')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['required_action']['name'], 'get-token')

        # Perform the get-token step
        required_action = states_resp.data['payment_method_states']['credit-card']['required_action']
        get_token_resp = self._do_payment_step_form_post(required_action)
        self.assertEqual(get_token_resp.data['status'], 'Success')

        # Fetch payment states again
        states_resp = self.client.get(order_resp.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['amount'], '10.00')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['required_action']['name'], 'authorize')

        # Perform the authorize step
        required_action = states_resp.data['payment_method_states']['credit-card']['required_action']
        authorize_resp = self._do_payment_step_form_post(required_action)
        self.assertEqual(authorize_resp.data['status'], 'Success')
        self.assertPaymentSource(order_resp.data['number'], 'Credit Card', allocated=D('10.00'))

        # Fetch payment states again
        states_resp = self.client.get(order_resp.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Authorized')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['status'], 'Complete')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['amount'], '10.00')
        self.assertIsNone(states_resp.data['payment_method_states']['credit-card']['required_action'])
        self.assertPaymentSource(order_resp.data['number'], 'Credit Card', allocated=D('10.00'))


    def test_split_payment_methods_conflict(self):
        self.login(is_staff=True)
        basket_id = self._prepare_basket()

        # Try and pay_in_full with two methods, isn't allow because it doesn't make sense
        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'credit-card': {
                'enabled': True,
                'pay_balance': True,
            },
            'cash': {
                'enabled': True,
                'pay_balance': True,
            },
        }
        resp = self._checkout(data)
        self.assertEqual(resp.status_code, status.HTTP_406_NOT_ACCEPTABLE)
        self.assertEqual(resp.data['payment']['non_field_errors'][0], 'Can not set pay_balance flag on multiple payment methods.')


    def test_split_payment_methods_missing_pay_balance(self):
        self.login(is_staff=True)
        basket_id = self._prepare_basket()

        # Try and pay_in_full with two methods, isn't allow because it doesn't make sense
        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'credit-card': {
                'enabled': True,
                'pay_balance': False,
                'amount': '2.00'
            },
            'cash': {
                'enabled': True,
                'pay_balance': False,
                'amount': '8.00'
            },
        }
        resp = self._checkout(data)
        self.assertEqual(resp.status_code, status.HTTP_406_NOT_ACCEPTABLE)
        self.assertEqual(resp.data['payment']['non_field_errors'][0], 'Must set pay_balance flag on at least one payment method.')


    def test_split_payment_methods_exceeding_balance(self):
        self.login(is_staff=True)
        basket_id = self._prepare_basket()

        # Try and provide more payment than is necessary
        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'cash': {
                'enabled': True,
                'pay_balance': False,
                'amount': '20.00'
            },
            'credit-card': {
                'enabled': True,
                'pay_balance': True,
            },
        }
        resp = self._checkout(data)
        self.assertEqual(resp.status_code, status.HTTP_406_NOT_ACCEPTABLE)
        self.assertEqual(resp.data['non_field_errors'][0], 'Specified payment amounts exceed order total.')


    def test_split_payment_methods(self):
        self.login(is_staff=True)
        basket_id = self._prepare_basket()

        # Provide split payments
        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'cash': {
                'enabled': True,
                'pay_balance': False,
                'amount': '2.00'
            },
            'credit-card': {
                'enabled': True,
                'pay_balance': True,
            },
        }
        order_resp = self._checkout(data)
        self.assertEqual(order_resp.status_code, status.HTTP_200_OK)

        # Fetch payment states
        states_resp = self.client.get(order_resp.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['status'], 'Complete')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['amount'], '2.00')
        self.assertIsNone(states_resp.data['payment_method_states']['cash']['required_action'])
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['amount'], '8.00')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['required_action']['name'], 'get-token')
        self.assertPaymentSource(order_resp.data['number'], 'Cash', allocated=D('2.00'), debited=D('2.00'))

        # Perform the get-token step
        required_action = states_resp.data['payment_method_states']['credit-card']['required_action']
        get_token_resp = self._do_payment_step_form_post(required_action)
        self.assertEqual(get_token_resp.data['status'], 'Success')
        self.assertPaymentSource(order_resp.data['number'], 'Cash', allocated=D('2.00'), debited=D('2.00'))

        # Fetch payment states again
        states_resp = self.client.get(order_resp.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['status'], 'Complete')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['amount'], '2.00')
        self.assertIsNone(states_resp.data['payment_method_states']['cash']['required_action'])
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['amount'], '8.00')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['required_action']['name'], 'authorize')
        self.assertPaymentSource(order_resp.data['number'], 'Cash', allocated=D('2.00'), debited=D('2.00'))

        # Perform the authorize step
        required_action = states_resp.data['payment_method_states']['credit-card']['required_action']
        authorize_resp = self._do_payment_step_form_post(required_action)
        self.assertEqual(authorize_resp.data['status'], 'Success')
        self.assertPaymentSource(order_resp.data['number'], 'Cash', allocated=D('2.00'), debited=D('2.00'))

        # Fetch payment states again
        states_resp = self.client.get(order_resp.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Authorized')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['status'], 'Complete')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['amount'], '2.00')
        self.assertIsNone(states_resp.data['payment_method_states']['cash']['required_action'])
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['status'], 'Complete')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['amount'], '8.00')
        self.assertIsNone(states_resp.data['payment_method_states']['credit-card']['required_action'])
        self.assertPaymentSource(order_resp.data['number'], 'Cash', allocated=D('2.00'), debited=D('2.00'))
        self.assertPaymentSource(order_resp.data['number'], 'Credit Card', allocated=D('8.00'))


    def test_retry_order_after_payment_decline(self):
        self.login(is_staff=True)

        resp = self._get_basket()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        basket_id = resp.data['id']

        product = self._create_product()
        resp = self._add_to_basket(product.id, quantity=2)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # Try and provide more payment than is necessary
        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'cash': {
                'enabled': True,
                'pay_balance': False,
                'amount': '10.00'
            },
            'credit-card': {
                'enabled': True,
                'pay_balance': True,
            },
        }
        order_resp1 = self._checkout(data)
        self.assertEqual(order_resp1.status_code, status.HTTP_200_OK)

        # Fetch payment states
        states_resp = self.client.get(order_resp1.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['status'], 'Complete')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['amount'], '10.00')
        self.assertIsNone(states_resp.data['payment_method_states']['cash']['required_action'])
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['amount'], '10.00')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['required_action']['name'], 'get-token')
        self.assertPaymentSource(order_resp1.data['number'], 'Cash', allocated=D('10.00'), debited=D('10.00'))

        # Perform the get-token step, but make it decline the request
        required_action = states_resp.data['payment_method_states']['credit-card']['required_action']
        required_action['fields'].append({ 'key': 'deny', 'value': True })
        get_token_resp = self._do_payment_step_form_post(required_action)
        self.assertEqual(get_token_resp.data['status'], 'Declined')
        self.assertPaymentSource(order_resp1.data['number'], 'Cash', allocated=D('10.00'), debited=D('10.00'))

        # Fetch payment states again
        states_resp = self.client.get(order_resp1.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Payment Declined')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['status'], 'Complete')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['amount'], '10.00')
        self.assertIsNone(states_resp.data['payment_method_states']['cash']['required_action'])
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['status'], 'Declined')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['amount'], '10.00')
        self.assertIsNone(states_resp.data['payment_method_states']['credit-card']['required_action'])
        self.assertPaymentSource(order_resp1.data['number'], 'Cash', allocated=D('10.00'), debited=D('10.00'))

        # Make sure we have access to the same basket
        self.assertEqual(self._get_basket_id(), basket_id)

        # Since order was declined, add another product to the basket
        resp = self._add_to_basket(product.id, quantity=1)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # Check order integrity before retying
        order = Order.objects.get(number=order_resp1.data['number'])
        self.assertEqual(order.lines.count(), 1)
        self.assertEqual(order.lines.first().quantity, 2)

        # Retry the checkout with our newly modified basket
        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'cash': {
                'enabled': True,
                'pay_balance': False,
                'amount': '12.75'
            },
            'credit-card': {
                'enabled': True,
                'pay_balance': True,
            },
        }
        order_resp2 = self._checkout(data)
        self.assertEqual(order_resp2.status_code, status.HTTP_200_OK)

        # Make sure the checkout attempt edited the existing, declined order, not made a new one.
        self.assertEqual(order_resp2.data['number'], order_resp1.data['number'])

        # Fetch payment states
        states_resp = self.client.get(order_resp2.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['status'], 'Complete')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['amount'], '12.75')
        self.assertIsNone(states_resp.data['payment_method_states']['cash']['required_action'])
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['amount'], '17.25')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['required_action']['name'], 'get-token')
        self.assertPaymentSource(order_resp2.data['number'], 'Cash', allocated=D('12.75'), debited=D('12.75'))

        # Perform the get-token step, but make it decline the request
        required_action = states_resp.data['payment_method_states']['credit-card']['required_action']
        get_token_resp = self._do_payment_step_form_post(required_action)
        self.assertEqual(get_token_resp.data['status'], 'Success')
        self.assertPaymentSource(order_resp2.data['number'], 'Cash', allocated=D('12.75'), debited=D('12.75'))

        # Fetch payment states again
        states_resp = self.client.get(order_resp2.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['status'], 'Complete')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['amount'], '12.75')
        self.assertIsNone(states_resp.data['payment_method_states']['cash']['required_action'])
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['amount'], '17.25')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['required_action']['name'], 'authorize')
        self.assertPaymentSource(order_resp2.data['number'], 'Cash', allocated=D('12.75'), debited=D('12.75'))

        # Perform the authorize step
        required_action = states_resp.data['payment_method_states']['credit-card']['required_action']
        authorize_resp = self._do_payment_step_form_post(required_action)
        self.assertEqual(authorize_resp.data['status'], 'Success')
        self.assertPaymentSource(order_resp2.data['number'], 'Cash', allocated=D('12.75'), debited=D('12.75'))

        # Fetch payment states again
        states_resp = self.client.get(order_resp2.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Authorized')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['status'], 'Complete')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['amount'], '12.75')
        self.assertIsNone(states_resp.data['payment_method_states']['cash']['required_action'])
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['status'], 'Complete')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['amount'], '17.25')
        self.assertIsNone(states_resp.data['payment_method_states']['credit-card']['required_action'])
        self.assertPaymentSource(order_resp2.data['number'], 'Cash', allocated=D('12.75'), debited=D('12.75'))
        self.assertPaymentSource(order_resp2.data['number'], 'Credit Card', allocated=D('17.25'))

        # Check order integrity after retry
        order = Order.objects.get(number=order_resp2.data['number'])
        self.assertEqual(order.lines.count(), 1)
        self.assertEqual(order.lines.first().quantity, 3)


    def test_cannot_retry_order_unless_declined(self):
        self.login(is_staff=True)
        basket_id = self._prepare_basket()

        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'cash': {
                'enabled': True,
                'pay_balance': True,
            }
        }
        order_resp1 = self._checkout(data)
        self.assertEqual(order_resp1.status_code, status.HTTP_200_OK)
        self.assertPaymentSource(order_resp1.data['number'], 'Cash', allocated=D('10.00'), debited=D('10.00'))

        # Check order integrity
        order = Order.objects.get(number=order_resp1.data['number'])
        self.assertEqual(order.lines.count(), 1)
        self.assertEqual(order.lines.first().quantity, 1)

        # Check payment states
        states_resp = self.client.get(order_resp1.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Authorized')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['status'], 'Complete')
        self.assertEqual(states_resp.data['payment_method_states']['cash']['amount'], '10.00')
        self.assertIsNone(states_resp.data['payment_method_states']['cash']['required_action'])

        # Make sure the API made a new basket for us
        self.assertNotEqual(self._get_basket_id(), basket_id)

        # Try checking out again with the old basket
        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'cash': {
                'enabled': True,
                'pay_balance': True,
            }
        }
        order_resp2 = self._checkout(data)
        self.assertEqual(order_resp2.status_code, status.HTTP_406_NOT_ACCEPTABLE)
        self.assertPaymentSource(order_resp1.data['number'], 'Cash', allocated=D('10.00'), debited=D('10.00'))


    def test_place_consecutive_orders(self):
        self.login(is_staff=True)

        # Place an order
        basket_id = self._prepare_basket()
        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'cash': {
                'enabled': True,
                'pay_balance': True,
            }
        }
        order_resp1 = self._checkout(data)
        self.assertEqual(order_resp1.status_code, status.HTTP_200_OK)
        self.assertPaymentSource(order_resp1.data['number'], 'Cash', allocated=D('10.00'), debited=D('10.00'))
        order = Order.objects.get(number=order_resp1.data['number'])
        self.assertEqual(order.lines.count(), 1)
        self.assertEqual(order.lines.first().quantity, 1)

        # Place another order
        basket_id = self._prepare_basket()
        data = self._get_checkout_data(basket_id)
        data['payment'] = {
            'cash': {
                'enabled': True,
                'pay_balance': True,
            }
        }
        order_resp2 = self._checkout(data)
        self.assertEqual(order_resp2.status_code, status.HTTP_200_OK)
        self.assertPaymentSource(order_resp2.data['number'], 'Cash', allocated=D('10.00'), debited=D('10.00'))
        order = Order.objects.get(number=order_resp2.data['number'])
        self.assertEqual(order.lines.count(), 1)
        self.assertEqual(order.lines.first().quantity, 1)

        # Make sure different orders were placed
        self.assertNotEqual(order_resp1.data['number'], order_resp2.data['number'])


    def test_order_ownership_transfer(self):
        # Login as one user
        self.login(is_staff=True)

        # Make a basket
        basket_id = self._get_basket_id()
        product = self._create_product(price=D('5.00'))
        resp = self._add_to_basket(product.id)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # Configure get_order_ownership so that the order becomes property of a different user. This is
        # conceivable for situations like a salesperson placing an order for someone else.
        some_other_user = User.objects.create_user(username='jim', password='doe', email='jim@example.cpom')

        def get_order_ownership(request, given_user, guest_email):
            return some_other_user, None

        # Checkout
        with mock.patch('oscarapicheckout.serializers.settings.ORDER_OWNERSHIP_CALCULATOR', get_order_ownership):
            data = self._get_checkout_data(basket_id)
            data['payment'] = {
                'cash': {
                    'enabled': True,
                    'pay_balance': True,
                }
            }
            order_resp = self._checkout(data)
        self.assertEqual(order_resp.status_code, status.HTTP_200_OK)

        # Make sure order payment is complete
        states_resp = self.client.get(order_resp.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Authorized')

        # Get the order from the DB and make sure that the order and the basket both belong to the user returned by
        # get_order_ownership, even though that wasn't the user who placed the order.
        order = Order.objects.get(number=order_resp.data['number'])
        self.assertEqual(order.user_id, some_other_user.id)
        self.assertEqual(order.basket.status, 'Submitted')
        self.assertEqual(order.basket.owner_id, some_other_user.id)



    def test_order_ownership_transfer_with_multistep_payment_method(self):
        # Login as one user
        request_user = self.login(is_staff=False)

        # Make a basket
        basket_id = self._get_basket_id()
        product = self._create_product(price=D('5.00'))
        resp = self._add_to_basket(product.id)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # Configure get_order_ownership so that the order becomes property of a different user. This is
        # conceivable for situations like a salesperson placing an order for someone else.
        some_other_user = User.objects.create_user(username='jim', password='doe', email='jim@example.cpom')

        def get_order_ownership(request, given_user, guest_email):
            return some_other_user, None

        # Checkout, using a multi-step payment method (credit card)
        with mock.patch('oscarapicheckout.serializers.settings.ORDER_OWNERSHIP_CALCULATOR', get_order_ownership):
            data = self._get_checkout_data(basket_id)
            data['payment'] = {
                'credit-card': {
                    'enabled': True,
                    'pay_balance': True,
                }
            }
            order_resp = self._checkout(data)
        self.assertEqual(order_resp.status_code, status.HTTP_200_OK)

        # Fetch payment states. Credit Card payment should be pending since we need to fetch a token
        states_resp = self.client.get(order_resp.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['amount'], '5.00')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['required_action']['name'], 'get-token')

        # Order should belong to the user returned by get_order_ownership, but basket should still belong to the request user
        self.assertEqual(Order.objects.get(number=order_resp.data['number']).user_id, some_other_user.pk)
        self.assertEqual(Basket.objects.get(pk=basket_id).owner_id, request_user.pk)

        # Perform the get-token step
        required_action = states_resp.data['payment_method_states']['credit-card']['required_action']
        get_token_resp = self._do_payment_step_form_post(required_action)
        self.assertEqual(get_token_resp.data['status'], 'Success')

        # Fetch payment states again, order and payment should still be pending
        states_resp = self.client.get(order_resp.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['amount'], '5.00')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['required_action']['name'], 'authorize')

        # Order should belong to the user returned by get_order_ownership, but basket should still belong to the request user
        self.assertEqual(Order.objects.get(number=order_resp.data['number']).user_id, some_other_user.pk)
        self.assertEqual(Basket.objects.get(pk=basket_id).owner_id, request_user.pk)

        # Perform the authorize step
        required_action = states_resp.data['payment_method_states']['credit-card']['required_action']
        authorize_resp = self._do_payment_step_form_post(required_action)
        self.assertEqual(authorize_resp.data['status'], 'Success')

        # Fetch payment states again
        states_resp = self.client.get(order_resp.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Authorized')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['status'], 'Complete')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['amount'], '5.00')
        self.assertIsNone(states_resp.data['payment_method_states']['credit-card']['required_action'])
        self.assertPaymentSource(order_resp.data['number'], 'Credit Card', allocated=D('5.00'))

        # Check order integrity
        order = Order.objects.get(number=order_resp.data['number'])
        self.assertEqual(order.status, 'Authorized')

        # Order and Basket should now both have been transfered from the request user to the get_order_ownership user
        self.assertEqual(Order.objects.get(number=order_resp.data['number']).user_id, some_other_user.pk)
        self.assertEqual(Basket.objects.get(pk=basket_id).owner_id, some_other_user.pk)

        # API should return a new Basket
        self.assertNotEqual(self._get_basket_id(), basket_id)


    def test_order_ownership_transfer_with_multistep_payment_method_with_retry(self):
        # Login as one user
        request_user = self.login(is_staff=False)

        # Make a basket
        basket_id = self._get_basket_id()
        product = self._create_product(price=D('5.00'))
        resp = self._add_to_basket(product.id)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # Configure get_order_ownership so that the order becomes property of a different user. This is
        # conceivable for situations like a salesperson placing an order for someone else.
        some_other_user = User.objects.create_user(username='jim', password='doe', email='jim@example.cpom')

        def get_order_ownership(request, given_user, guest_email):
            return some_other_user, None

        # Checkout, using a multi-step payment method (credit card)
        with mock.patch('oscarapicheckout.serializers.settings.ORDER_OWNERSHIP_CALCULATOR', get_order_ownership):
            data = self._get_checkout_data(basket_id)
            data['payment'] = {
                'credit-card': {
                    'enabled': True,
                    'pay_balance': True,
                }
            }
            order_resp = self._checkout(data)
        self.assertEqual(order_resp.status_code, status.HTTP_200_OK)
        order_number1 = order_resp.data['number']

        # Fetch payment states. Credit Card payment should be pending since we need to fetch a token
        states_resp = self.client.get(order_resp.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['amount'], '5.00')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['required_action']['name'], 'get-token')

        # Order should belong to the user returned by get_order_ownership, but basket should still belong to the request user
        self.assertEqual(Order.objects.get(number=order_number1).user_id, some_other_user.pk)
        self.assertEqual(Basket.objects.get(pk=basket_id).owner_id, request_user.pk)

        # Perform the get-token step
        required_action = states_resp.data['payment_method_states']['credit-card']['required_action']
        get_token_resp = self._do_payment_step_form_post(required_action)
        self.assertEqual(get_token_resp.data['status'], 'Success')

        # Fetch payment states again, order and payment should still be pending
        states_resp = self.client.get(order_resp.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['amount'], '5.00')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['required_action']['name'], 'authorize')

        # Order should belong to the user returned by get_order_ownership, but basket should still belong to the request user
        self.assertEqual(Order.objects.get(number=order_number1).user_id, some_other_user.pk)
        self.assertEqual(Basket.objects.get(pk=basket_id).owner_id, request_user.pk)

        # Perform the authorize step, but make the payment method decline payment
        required_action = states_resp.data['payment_method_states']['credit-card']['required_action']
        required_action['fields'].append({ 'key': 'deny', 'value': True })
        authorize_resp = self._do_payment_step_form_post(required_action)
        self.assertEqual(authorize_resp.data['status'], 'Declined')

        # Fetch payment states again
        states_resp = self.client.get(order_resp.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Payment Declined')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['status'], 'Declined')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['amount'], '5.00')
        self.assertIsNone(states_resp.data['payment_method_states']['credit-card']['required_action'])

        # Check order integrity
        order = Order.objects.get(number=order_number1)
        self.assertEqual(order.status, 'Payment Declined')

        # Order should belong to the user returned by get_order_ownership, but basket should still belong to the request user
        self.assertEqual(Order.objects.get(number=order_number1).user_id, some_other_user.pk)
        self.assertEqual(Basket.objects.get(pk=basket_id).owner_id, request_user.pk)

        # API should return the same basket we've been working with
        self.assertEqual(self._get_basket_id(), basket_id)

        # Checkout again, using a multi-step payment method (credit card)
        with mock.patch('oscarapicheckout.serializers.settings.ORDER_OWNERSHIP_CALCULATOR', get_order_ownership):
            data = self._get_checkout_data(basket_id)
            data['payment'] = {
                'credit-card': {
                    'enabled': True,
                    'pay_balance': True,
                }
            }
            order_resp = self._checkout(data)
        self.assertEqual(order_resp.status_code, status.HTTP_200_OK)

        # Order number should get recycled
        order_number2 = order_resp.data['number']
        self.assertEqual(order_number2, order_number1)

        # Fetch payment states. Credit Card payment should be pending since we need to fetch a token
        states_resp = self.client.get(order_resp.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['amount'], '5.00')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['required_action']['name'], 'get-token')

        # Order should belong to the user returned by get_order_ownership, but basket should still belong to the request user
        self.assertEqual(Order.objects.get(number=order_number2).user_id, some_other_user.pk)
        self.assertEqual(Basket.objects.get(pk=basket_id).owner_id, request_user.pk)

        # Perform the get-token step
        required_action = states_resp.data['payment_method_states']['credit-card']['required_action']
        get_token_resp = self._do_payment_step_form_post(required_action)
        self.assertEqual(get_token_resp.data['status'], 'Success')

        # Fetch payment states again, order and payment should still be pending
        states_resp = self.client.get(order_resp.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['status'], 'Pending')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['amount'], '5.00')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['required_action']['name'], 'authorize')

        # Order should belong to the user returned by get_order_ownership, but basket should still belong to the request user
        self.assertEqual(Order.objects.get(number=order_number2).user_id, some_other_user.pk)
        self.assertEqual(Basket.objects.get(pk=basket_id).owner_id, request_user.pk)

        # Perform the authorize step, this time make it accept the transaction
        required_action = states_resp.data['payment_method_states']['credit-card']['required_action']
        authorize_resp = self._do_payment_step_form_post(required_action)
        self.assertEqual(authorize_resp.data['status'], 'Success')

        # Fetch payment states again
        states_resp = self.client.get(order_resp.data['payment_url'])
        self.assertEqual(states_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(states_resp.data['order_status'], 'Authorized')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['status'], 'Complete')
        self.assertEqual(states_resp.data['payment_method_states']['credit-card']['amount'], '5.00')
        self.assertIsNone(states_resp.data['payment_method_states']['credit-card']['required_action'])
        self.assertPaymentSource(order_number2, 'Credit Card', allocated=D('5.00'))

        # Check order integrity
        order = Order.objects.get(number=order_number2)
        self.assertEqual(order.status, 'Authorized')

        # Order and Basket should now both have been transfered from the request user to the get_order_ownership user
        self.assertEqual(Order.objects.get(number=order_number2).user_id, some_other_user.pk)
        self.assertEqual(Basket.objects.get(pk=basket_id).owner_id, some_other_user.pk)

        # API should return a new Basket now
        self.assertNotEqual(self._get_basket_id(), basket_id)



    def assertPaymentSource(self, order_number, source_name, allocated=D('0.00'), debited=D('0.00'), refunded=D('0.00')):
        order = Order.objects.get(number=order_number)
        source = order.sources.get(source_type__name=source_name)
        self.assertEqual(source.amount_allocated, allocated)
        self.assertEqual(source.amount_debited, debited)
        self.assertEqual(source.amount_refunded, refunded)


    def _do_payment_step_form_post(self, required_action):
        method = required_action['method'].lower()
        url = required_action['url']

        fields = required_action['fields']
        fields = { field['key']: field['value'] for field in fields }

        resp = getattr(self.client, method)(url, fields)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        return resp


    def _prepare_basket(self):
        basket_id = self._get_basket_id()
        product = self._create_product()
        resp = self._add_to_basket(product.id)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return basket_id


    def _get_basket_id(self):
        resp = self._get_basket()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return resp.data['id']


    def _create_product(self, price=D('10.00')):
        product = factories.create_product(
            title='My Product',
            product_class='My Product Class')
        record = factories.create_stockrecord(
            currency='USD',
            product=product,
            num_in_stock=10,
            price_excl_tax=price)
        factories.create_purchase_info(record)
        return product


    def _get_basket(self):
        url = reverse('api-basket')
        return self.client.get(url)


    def _add_to_basket(self, product_id, quantity=1):
        url = reverse('api-basket-add-product')
        data = {
            "url": reverse('product-detail', args=[product_id]),
            "quantity": quantity
        }
        return self.client.post(url, data)


    def _get_checkout_data(self, basket_id):
        data = {
            "guest_email": "anonymous_joe@example.com",
            "basket": reverse('basket-detail', args=[basket_id]),
            "shipping_address": {
                "first_name": "Joe",
                "last_name": "Schmoe",
                "line1": "234 5th Ave",
                "line4": "Manhattan",
                "postcode": "10001",
                "state": "NY",
                "country": reverse('country-detail', args=['US']),
                "phone_number": "+1 (717) 467-1111",
            },
            "billing_address": {
                "first_name": "Joe",
                "last_name": "Schmoe",
                "line1": "234 5th Ave",
                "line4": "Manhattan",
                "postcode": "10001",
                "state": "NY",
                "country": reverse('country-detail', args=['US']),
                "phone_number": "+1 (717) 467-1111",
            },
            "payment": {
                'cash': {
                    'enabled': False
                }
            }
        }
        return data

    def _checkout(self, data):
        url = reverse('api-checkout')
        return self.client.post(url, data, format='json')
