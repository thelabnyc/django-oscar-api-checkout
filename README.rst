=========================
django-oscar-api-checkout
=========================

|  |build| |coverage| |license| |kit| |format|

An extension on top of django-oscar-api providing a more flexible checkout API with a pluggable payment methods interface.

.. |build| image:: https://gitlab.com/thelabnyc/django-oscar/django-oscar-api-checkout/badges/master/pipeline.svg
    :target: https://gitlab.com/thelabnyc/django-oscar/django-oscar-api-checkout/commits/master
.. |coverage| image:: https://gitlab.com/thelabnyc/django-oscar/django-oscar-api-checkout/badges/master/coverage.svg
    :target: https://gitlab.com/thelabnyc/django-oscar/django-oscar-api-checkout/commits/master
.. |license| image:: https://img.shields.io/pypi/l/django-oscar-api-checkout.svg
    :target: https://pypi.python.org/pypi/django-oscar-api-checkout
.. |kit| image:: https://badge.fury.io/py/django-oscar-api-checkout.svg
    :target: https://pypi.python.org/pypi/django-oscar-api-checkout
.. |format| image:: https://img.shields.io/pypi/format/django-oscar-api-checkout.svg
    :target: https://pypi.python.org/pypi/django-oscar-api-checkout


Compatible Payment Plugins
==========================

- `django-oscar-cybersource <https://gitlab.com/thelabnyc/django-oscar/django-oscar-cybersource>`_: Provides order payment using Cybersource Secure Acceptance Silent Order POST for PCI SAQ A-EP compliant credit card processing.
- `django-oscar-wfrs <https://gitlab.com/thelabnyc/django-oscar/django-oscar-wfrs>`_: Provides order payment using financing via the Wells Fargo Retail Services SOAP API.


Installation
============

1. Install `django-oscar-api` using the `documentation <https://django-oscar-api.readthedocs.io/en/latest/#installation>`_.

2. Install the `django-oscar-api-checkout` package.::

    $ pip install django-oscar-api-checkout

3. Add `oscarapicheckout` to your `INSTALLED_APPS`::

    # myproject/settings.py
    ...
    INSTALLED_APPS = [
        ...
        'oscarapicheckout',
    ] + get_core_apps([])
    ...

4. Configure Oscar's order status pipeline.::

    # myproject/settings.py
    ...
    # Needed by oscarapicheckout
    ORDER_STATUS_PENDING = 'Pending'
    ORDER_STATUS_PAYMENT_DECLINED = 'Payment Declined'
    ORDER_STATUS_AUTHORIZED = 'Authorized'

    # Other statuses
    ORDER_STATUS_SHIPPED = 'Shipped'
    ORDER_STATUS_CANCELED = 'Canceled'

    # Pipeline Config
    OSCAR_INITIAL_ORDER_STATUS = ORDER_STATUS_PENDING
    OSCARAPI_INITIAL_ORDER_STATUS = ORDER_STATUS_PENDING
    OSCAR_ORDER_STATUS_PIPELINE = {
        ORDER_STATUS_PENDING: (ORDER_STATUS_PAYMENT_DECLINED, ORDER_STATUS_AUTHORIZED, ORDER_STATUS_CANCELED),
        ORDER_STATUS_PAYMENT_DECLINED: (ORDER_STATUS_AUTHORIZED, ORDER_STATUS_CANCELED),
        ORDER_STATUS_AUTHORIZED: (ORDER_STATUS_SHIPPED, ORDER_STATUS_CANCELED),
        ORDER_STATUS_SHIPPED: (),
        ORDER_STATUS_CANCELED: (),
    }

    OSCAR_INITIAL_LINE_STATUS = ORDER_STATUS_PENDING
    OSCAR_LINE_STATUS_PIPELINE = {
        ORDER_STATUS_PENDING: (ORDER_STATUS_SHIPPED, ORDER_STATUS_CANCELED),
        ORDER_STATUS_SHIPPED: (),
        ORDER_STATUS_CANCELED: (),
    }

5. Configure what payment methods are enabled and who can use them.::

    # myproject/settings.py
    ...
    API_ENABLED_PAYMENT_METHODS = [
        {
            'method': 'oscarapicheckout.methods.Cash',
            'permission': 'oscarapicheckout.permissions.StaffOnly',
        },
        {
            'method': 'some.other.methods.CreditCard',
            'permission': 'oscarapicheckout.permissions.Public',
        },
    ]

6. Add `oscarapicheckout` to your root URL configuration directly before oscarapi.::

    # myproject/urls.py
    ...
    from django.apps import apps
    from oscarapi.app import application as oscar_api
    from oscarapicheckout.app import application as oscar_api_checkout

    urlpatterns = patterns('',
        ...
        url(r'^api/', include(apps.get_app_config("oscarapicheckout").urls[0])), # Must be before oscar_api.urls
        url(r'^api/', include(oscar_api.urls)),
        ...
    )


Usage
=====

These are the basic steps to add an item to the basket and checkout using the API.

1. Add an item to the basket.::

    POST /api/basket/add-product/

    {
        "url": "/api/products/1/",
        "quantity": 1
    }


2. List the payment methods available to the current user.::

    GET /api/checkout/payment-methods/

3. Submit the order, specifying which payment method(s) to use.::

    POST /api/checkout/

    {
        "guest_email": "joe@example.com",
        "basket": "/api/baskets/1/",
        "shipping_address": {
            "first_name": "Joe",
            "last_name": "Schmoe",
            "line1": "234 5th Ave",
            "line4": "Manhattan",
            "postcode": "10001",
            "state": "NY",
            "country": "/api/countries/US/",
            "phone_number": "+1 (717) 467-1111",
        },
        "billing_address": {
            "first_name": "Joe",
            "last_name": "Schmoe",
            "line1": "234 5th Ave",
            "line4": "Manhattan",
            "postcode": "10001",
            "state": "NY",
            "country": "/api/countries/US/",
            "phone_number": "+1 (717) 467-1111",
        },
        "payment": {
            "cash": {
                "enabled": true,
                "amount": "10.00",
            },
            "creditcard": {
                "enabled": true,
                "pay_balance": true,
            }
        }
    }

4. Check the status of each enabled payment option.::

    GET /api/checkout/payment-states/
