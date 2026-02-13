# Changes

## v3.9.0b1 (2026-02-13)

## v3.9.0b0 (2026-02-13)

### Feat

- add ClientSidePaymentRequired payment state
- support Python 3.14

### Fix

- **deps**: update dependency django to >=5.2
- **deps**: update dependency django to >=4.2.27

## v3.8.1 (2025-11-19)

### Fix

- **deps**: update dependency django-oscar to >=4.1,<4.2
- **deps**: update dependency drf-recaptcha to >=4.0.3,<5
- prevent renovate from pointing all URLs at gitlab

## v3.8.0 (2025-09-03)

### Feat

- test against django 5.2

### Fix

- update docker image tag format
- **deps**: update dependency django-oscar to >=4.0,<4.1
- **deps**: update dependency django-oscar to >=3.2.6,<4.1

### Refactor

- migrate black/flake8 -> ruff
- migrate from poetry -> uv

## v3.7.0 (2025-04-03)

### Feat

- add support for Django 5.0

### Fix

- **deps**: update dependency django to ^4.2.20
- **deps**: update dependency django to ^4.2.19

### Refactor

- add pyupgrade / django-upgrade precommit hooks

## v3.6.3 (2025-01-30)

### Fix

- increase typing strictness

## v3.6.2 (2025-01-30)

### Fix

- typing tweaks

## v3.6.1 (2025-01-23)

### Fix

- python version in publish job

## v3.6.0 (2025-01-23)

### Feat

- add type annotations

### Fix

- **deps**: update dependency django to ^4.2.18
- **deps**: update dependency django to ^4.2.17

## v3.5.1 (2024-11-06)

### Fix

- **deps**: update dependency drf-recaptcha to v4

## v3.5.0 (2024-09-25)

### Feat

- allow setting API_CHECKOUT_CAPTCHA to a callable function, thereby allowing captcha config to be configured per-request (#26990)

### Fix

- **deps**: update dependency django-oscar to v3.2.5
- **deps**: update dependency django-oscar-api to v3.3.0
- pin django-oscar version due to breaking changes in patch versions
- **deps**: update dependency drf-recaptcha to ^3.2.0
- **deps**: update dependency django to ^4.2.16

## v3.4.1 (2024-08-31)

### Fix

- **deps**: update dependency django to ^4.2.15

## v3.4.1b0 (2024-08-08)

### Fix

- **deps**: update dependency django to ^4.2.14
- **deps**: update dependency django to ^4.2.13
- **deps**: update dependency drf-recaptcha to v3.1.0
- **deps**: update dependency django to v4.2.13

## v3.4.0

- Update recaptcha field from v2 to v3.

## v3.3.1

- Ensure order confirmation emails are not sent until after the DB transaction wrapping checkout is committed.

## v3.3.0

- Add support for requiring a recaptcha field at checkout. Enable with the ``API_CHECKOUT_CAPTCHA`` setting.
- Add support for customizable fraud check rules that run during checkout. These are controlled with the ``API_CHECKOUT_FRAUD_CHECKS`` setting. Once example rule is provided: ``oscarapicheckout.fraud.AddressVelocity``.

## v3.2.0

- Add support for django-oscar 3.2.2
- Add support for django 4.2

## v3.1.1

- Fix bug where, on occasion, ``OrderUpdater`` would try to decrement ``Voucher.num_orders`` below 0.

## v3.1.0

- Add new “Pay Later” deferred payment functionality.

## v3.0.0

- Oscar 3.0 Compatibility

## v2.0.0


## v1.1.0

- Add support for calculating taxes on shipping charges.
- Fix bug with ``Voucher.num_orders`` value when retrying payment declined orders.

## v1.0.0

- Remove direct dependency on ``phonenumberslite`` since it's actually a dependency of ``django-oscar``.

## v0.6.0

- Add support for django-oscar 2.x.
- Drop support for django-oscar 1.x.

## v0.5.2

- Internationalization

## v0.5.1

- Add new permission: ``oscarapicheckout.permissions.CustomerOnly``

## v0.5.0

- Make payment methods create separate ``payment.Source`` objects per Reference number (`!6 <https://gitlab.com/thelabnyc/django-oscar/django-oscar-api-checkout/merge_requests/6>`_).
- Delete Voucher applications upon payment decline, rather than waiting for an order placement retry. This fixes issues associated with payment declined orders consuming vouchers.

## v0.4.1

- Fixed bug that prevented transitioning an order from ``Payment Declined`` to ``Authorized`` if the payment type was changed.

## v0.4.0

- Improved split-pay support by allowing multiple payments of the same type. E.g. two credit cards, etc.
    - *[Important]* To accomplish this, the payment provider plug-in interface changed slightly. Plugins must be updated to support the new interface. The REST API front-end added parameters, but retained backwards compatibility with ``0.3.x``.
- Fixed bug caused by changing the status of a Payment Declined order (e.g. to Canceled) caused checkout to break for the customer, because they were now editable a basket connected to a non-payment-declined order. Fixes the bug by setting a basket to "Submitted" status whenever the order status transitions from "Payment Declined" to another status.

## v0.3.4

- Fix Django 2.0 Deprecation warnings.

## v0.3.3

- Add validation to checkout API to prevent placing an order for an item that went out of stock after the item was added to the customer's basket.

## v0.3.2

- Fix issue in Python 3 when ``OrderCreator.place_order`` raises a ``ValueError`` exception.
- Fix bug occurring in Oscar 1.5 when vouchers can be used by the user placing an order, but not by the order owner.

## v0.3.1

- Add support for Django 1.11 and Oscar 1.5

## v0.3.0

- Add helper classes for caching structured data during a multi-step checkout process.
    - See `oscarapicheckout.cache` module for details.
    - Doesn't yet include API views for editing or view such data.
    - Currently includes classes for storing email address, shipping address, billing address, and shipping method.
    - Required [Django Cache](https://docs.djangoproject.com/en/dev/topics/cache/) framework to be configured.

## v0.2.7

- *[Important]* Fix bug introduced in *r0.2.6* with multi-step payment methods when retrying a payment decline.

## v0.2.6

- *[Important]* Fix bug causing mismatch between ``Order.user`` and ``Basket.owner`` when, during placement, the order ownership calculator assigns the order to a user other than the basket owner. Now, after creating the order model, the owner of the basket associated with the order is updated to match the order's owner.
- Make it possible to set the ``ORDER_OWNERSHIP_CALCULATOR`` to a callable or a string instead of just a string.

## v0.2.5

- Improve testing by using tox in the CI runner.

## v0.2.4

- Upgrade dependencies.

## v0.2.3

- Make the order in which signals are sent during checkout consistent for synchronous and asynchronous payment methods.
    - Previously a synchronous payment method resulted in sending ``order_payment_authorized`` before sending ``order_placed``, but an asynchronous payment method would trigger ``order_placed`` first followed by ``order_payment_authorized`` (on a subsequent HTTP request). They are still different in terms of synchronous payment methods firing both signals on the same request and asynchronous payment methods triggering them on different request, but at least now they are always fired in the same order: ``order_placed`` first followed by ``order_payment_authorized``.

## v0.2.2

- Require an email address during checkout

## v0.2.1

- Explicitly dis-allow cache on API views

## v0.2.0

- Add setting to allow configuring how many payment types may be used on an order
- Add hook for setting the ownership information on an order during placement
- Prevent PaymentEvent.reference from ever being None

## v0.1.5

- Fix bug where order number wouldn't be recycled for a declined order

## v0.1.4

- Add context to payment method serializers

## v0.1.3

- Simplify dependencies

## v0.1.2

- Allow PaymentMethods to handle 0.00-amount transactions

## v0.1.1

- Send confirmation message upon order authorization
- Add pep8 linting

## v0.1.0

- Initial release.
