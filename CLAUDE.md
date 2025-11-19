# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

django-oscar-api-checkout is a Django extension that provides a flexible checkout API for django-oscar e-commerce framework. It offers a pluggable payment methods interface with support for multiple payment processors.

## Development Commands

**IMPORTANT**: All development commands MUST be run inside Docker via `docker compose` due to the PostgreSQL dependency. The project requires a running PostgreSQL database for tests and migrations.

### Running Tests

```bash
# Run all tests with coverage (via Docker)
docker compose run --rm test uv run python manage.py test oscarapicheckout -v 2 --buffer --noinput

# Run tests via tox (multiple Python/Django versions) - RECOMMENDED
docker compose run --rm test uv run tox

# Run tests for specific environment
docker compose run --rm test uv run tox -e py312-django420-drf316-oscar40

# Run tests for multiple specific environments
docker compose run --rm test uv run tox -e py312-django420-drf316-oscar40,py312-django420-drf316-oscar41
```

### Type Checking

```bash
# Type check main package and sandbox (via Docker)
docker compose run --rm test uv run mypy oscarapicheckout sandbox
```

### Code Quality

```bash
# Format code with ruff (via Docker)
docker compose run --rm test uv run ruff format .

# Run pre-commit hooks (via Docker)
docker compose run --rm test make test_precommit
```

### Migrations

```bash
# Generate migrations (via Docker)
docker compose run --rm test uv run python manage.py makemigrations

# Run migrations (via Docker)
docker compose run --rm test uv run python manage.py migrate
```

### Translations

```bash
# Generate and compile translation files (via Docker)
docker compose run --rm test make translations
```

### Docker Compose Services

The `docker-compose.yml` file defines:
- `postgres`: PostgreSQL database service
- `test`: Python test environment with mounted code volume

## Architecture

### Core Payment Flow

The checkout process follows this state machine:

1. **Order Creation** (`views.CheckoutView.post`):
   - Validates checkout data via `CheckoutSerializer`
   - Freezes the basket
   - Creates order with status `ORDER_STATUS_PENDING` ("Pending")
   - Records payment methods in session
   - Returns order + payment states

2. **Payment State Management** (`utils.py`):
   - Payment states are pickled and stored in session under `CHECKOUT_PAYMENT_STEPS`
   - Each payment method tracks amount and status
   - Status flow: `PENDING` → `COMPLETE`/`DECLINED` → `CONSUMED`

3. **Order Status Transitions** (`utils._update_order_status`):
   - All payments `COMPLETE` → Order becomes `AUTHORIZED`, payments marked `CONSUMED`
   - Any payment `DECLINED` → Order becomes `PAYMENT_DECLINED`
   - Payment declined orders can be updated (not recreated) via `utils.OrderUpdater`

4. **Payment Method Plugins** (`methods.py`):
   - Base class: `PaymentMethod[T: PaymentMethodData]`
   - Subclass `_record_payment()` to implement payment logic
   - Built-in: `Cash` (immediate payment), `PayLater` (deferred payment)
   - Plugins return `PaymentStatus` objects (Complete, Declined, Deferred, FormPostRequired)

### Key Components

**Serializers** (`serializers.py`):
- `CheckoutSerializer`: Main checkout form, extends `oscarapi.serializers.checkout.CheckoutSerializer`
- `PaymentMethodsSerializer`: Dynamic serializer built from `settings.API_ENABLED_PAYMENT_METHODS`
- `DiscriminatedUnionSerializer`: Handles polymorphic payment method data (discriminated union pattern)
- `SignedTokenRelatedField`: Server-signed tokens for baskets/orders to verify client permissions

**Views** (`views.py`):
- `PaymentMethodsView`: Lists available payment methods for current user (GET)
- `CheckoutView`: Places order and begins payment collection (POST)
- `PaymentStatesView`: Checks payment status for pending order (GET)
- `CompleteDeferredPaymentView`: Completes payment for "Pay Later" orders (POST)

**Payment States** (`states.py`):
- `Complete`: Payment successfully authorized/captured
- `Declined`: Payment rejected
- `Deferred`: Payment deferred (e.g., "Pay Later")
- `Consumed`: Payment has been applied to an authorized order
- `FormPostRequired`: Client must POST form to complete payment (returns form data)

**Permissions** (`permissions.py`):
- `Public`: Available to all users
- `StaffOnly`: Staff/admin only
- `CustomerOnly`: Non-staff only

**Fraud Detection** (`fraud.py`):
- Pluggable fraud rules via `settings.API_CHECKOUT_FRAUD_CHECKS`
- Built-in: `AddressVelocity` (rate-limits orders by address)
- Rules implement `FraudRule` protocol with `validate()` method

### Configuration

Payment methods configured in Django settings:

```python
API_ENABLED_PAYMENT_METHODS = [
    {
        'method': 'oscarapicheckout.methods.Cash',
        'permission': 'oscarapicheckout.permissions.StaffOnly',
        'method_kwargs': {},
        'permission_kwargs': {},
    },
]
```

Required order status pipeline:

```python
ORDER_STATUS_PENDING = 'Pending'
ORDER_STATUS_PAYMENT_DECLINED = 'Payment Declined'
ORDER_STATUS_AUTHORIZED = 'Authorized'
```

### Important Patterns

**Payment Method Implementation**:
1. Subclass `PaymentMethod[YourDataType]`
2. Define `name` and `code` class attributes
3. Implement `_record_payment()` returning `PaymentStatus`
4. Create/allocate/debit payment `Source` via `get_source()`
5. Record payment events via `make_authorize_event()`, `make_debit_event()`

**Handling Declined Orders**:
- Declined orders keep the same order number but reset lines/discounts/vouchers
- Basket is thawed and restored to session
- Use `utils.OrderUpdater.update_order()` to retry (never create new order)

**Testing**:
- Test base class: `oscarapicheckout.tests.base.BaseTest`
- Provides `create_product()`, `create_basket_with_product()`
- Uses sandbox settings with PostgreSQL backend

## Type Checking

Project uses strict mypy configuration:
- Plugins: `mypy_django_plugin`, `mypy_drf_plugin`
- Migrations and tests ignore type errors
- Untyped imports followed for `oscar`, `oscarapi`, `drf_recaptcha`

## Sandbox

The `sandbox/` directory contains a test Django project:
- Custom `Order` model in `sandbox.order.models`
- Settings in `sandbox/settings.py`
- Credit card example in `sandbox/creditcards/`
