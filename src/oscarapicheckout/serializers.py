from collections import OrderedDict
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.signing import Signer, BadSignature
from django.db import transaction
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _
from django.utils.encoding import force_str, smart_str
from rest_framework import serializers, exceptions
from rest_framework.utils import html
from rest_framework.exceptions import ValidationError
from oscar.core.loading import get_model, get_class
from oscarapi.serializers.checkout import (
    CheckoutSerializer as OscarCheckoutSerializer,
    OrderSerializer as OscarOrderSerializer,
)
from oscarapi.basket.operations import get_basket
from drf_recaptcha.fields import ReCaptchaV3Field
from .signals import pre_calculate_total
from .states import PENDING
from . import utils, settings, fraud
import logging


Basket = get_model("basket", "Basket")
Order = get_model("order", "Order")
BillingAddress = get_model("order", "BillingAddress")
ShippingAddress = get_model("order", "ShippingAddress")

OrderTotalCalculator = get_class("checkout.calculators", "OrderTotalCalculator")

logger = logging.getLogger(__name__)


class DiscriminatedUnionSerializer(serializers.Serializer):
    """
    Serializer for building a discriminated-union of other serializers

    Usage:

    DiscriminatedUnionSerializer(
        # (string) Field name that will uniquely identify which serializer to use.
        discriminant_field_name="some_field_name",

        # (dict <string: serializer class>) Dictionary that indicates which
        # serializer class should be used, based on the value of ``discriminant_field_name``.
        types={
            "some_choice_in_some_field_name": SomeSerializer(),
            ...
        }

        # Other serializers.Serializer arguments
    )

    See this documentation for a good introduction to the concept of discriminated unions.

    - https://www.typescriptlang.org/docs/handbook/advanced-types.html#discriminated-unions
    - https://en.wikipedia.org/wiki/Tagged_union

    """

    def __init__(self, discriminant_field_name, types, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[discriminant_field_name] = serializers.ChoiceField(
            choices=[(t, t) for t in types.keys()]
        )
        self.discriminant_field_name = discriminant_field_name
        self.type_mapping = types

    def to_representation(self, obj):
        concrete_type = self._get_concrete_type(obj)
        if concrete_type:
            return concrete_type.to_representation(obj)
        return super().to_representation(obj)

    def to_internal_value(self, data):
        concrete_type = self._get_concrete_type(data)
        if concrete_type:
            return concrete_type.to_internal_value(data)
        return super().to_internal_value(data)

    def run_validation(self, data):
        concrete_type = self._get_concrete_type(data)
        if concrete_type:
            return concrete_type.run_validation(data)
        return super().run_validation(data)

    def _get_obj_type(self, obj):
        if hasattr(obj, "get"):
            return obj.get(self.discriminant_field_name)
        return getattr(obj, self.discriminant_field_name)

    def _get_concrete_type(self, obj):
        obj_type = self._get_obj_type(obj)
        return self.type_mapping.get(obj_type)


class PaymentMethodsSerializer(serializers.DictField):
    """
    Dynamic serializer created based on the configured payment methods (settings.API_ENABLED_PAYMENT_METHODS)
    """

    def __init__(self, *args, context={}, **kwargs):
        super().__init__(*args, **kwargs)

        request = context.get("request", None)
        assert request is not None, (
            "`%s` requires the request in the serializer"
            " context. Add `context={'request': request}` when instantiating "
            "the serializer." % self.__class__.__name__
        )

        self.methods = {}
        for m in settings.API_ENABLED_PAYMENT_METHODS:
            PermissionClass = import_string(m["permission"])
            permission = PermissionClass(**m.get("permission_kwargs", {}))
            if permission.is_permitted(request=request, user=request.user):
                MethodClass = import_string(m["method"])
                method = MethodClass(**m.get("method_kwargs", {}))
                self.methods[method.code] = method

        if not any(self.methods):
            raise RuntimeError(
                "No payment methods were permitted for user %s" % request.user
            )

        union_types = {}
        for code, method in self.methods.items():
            union_types[method.code] = method.serializer_class(
                method_type_choices=[(code, force_str(method.name))],
                required=False,
                context=context,
            )

        self.child = DiscriminatedUnionSerializer("method_type", union_types)
        self.child.bind(field_name="", parent=self)

    def to_internal_value(self, data):
        """Dicts of native values <- Dicts of primitive datatypes."""
        if html.is_html_input(data):
            data = html.parse_html_dict(data)
        if not isinstance(data, dict):
            self.fail("not_a_dict", input_type=type(data).__name__)
        return self.run_child_validation(data)

    def run_child_validation(self, data):
        # For API backwards compatibility with versions 0.3.x and earlier, if ``method_type`` isn't
        # set, default it to the given method key.
        tmp_data = {}
        for key, value in data.items():
            if "method_type" not in value:
                value["method_type"] = key
                if key in self.methods:
                    tmp_data[key] = value
            else:
                tmp_data[key] = value
        data = tmp_data

        # Run the field-level validation on each child serializer
        result = {}
        errors = OrderedDict()
        for key, value in data.items():
            key = str(key)
            try:
                result[key] = self.child.run_validation(value)
            except ValidationError as e:
                errors[key] = e.detail
        if errors:
            raise ValidationError(errors)

        # Finally, run the business logic validation
        # At least one method must be enabled
        enabled_methods = {k: v for k, v in result.items() if v["enabled"]}
        if len(enabled_methods) <= 0:
            # Translators: User facing error message in checkout
            raise serializers.ValidationError(
                _("At least one payment method must be enabled.")
            )

        # Respect payment method limit
        if (
            settings.API_MAX_PAYMENT_METHODS > 0
            and len(enabled_methods) > settings.API_MAX_PAYMENT_METHODS
        ):
            # Translators: User facing error message in checkout
            msg = _("No more than %(num)s payment method can be enabled.") % dict(
                num=settings.API_MAX_PAYMENT_METHODS
            )
            raise serializers.ValidationError(msg)

        # Must set pay_balance flag on exactly one payment method
        balance_methods = {k: v for k, v in enabled_methods.items() if v["pay_balance"]}
        if len(balance_methods) > 1:
            # Translators: User facing error message in checkout
            raise serializers.ValidationError(
                _("Can not set pay_balance flag on multiple payment methods.")
            )
        elif len(balance_methods) < 1:
            # Translators: User facing error message in checkout
            raise serializers.ValidationError(
                _("Must set pay_balance flag on at least one payment method.")
            )

        return result


class SignedTokenRelatedField(serializers.SlugRelatedField):
    """
    Similar to a SlugRelatedField, but uses a server-signed version of the slug.
    Thus, this can be used to both identify an object and verify the client has
    permission to view/modify it.
    """

    @classmethod
    def get_signer(cls):
        signer = Signer(salt=f"oscarapicheckout.{cls.__name__}")
        print(f"salt == oscarapicheckout.{cls.__name__}")
        return signer

    @classmethod
    def verify_token(cls, token):
        return cls.get_signer().unsign(token)

    def get_token(self, model_inst):
        """Generate the signed token value for the given model instance"""
        raw_value = getattr(model_inst, self.slug_field)
        logger.info(
            "Generating %s token for %s[%s]",
            self.__class__.__name__,
            model_inst.__class__.__name__,
            raw_value,
        )
        return self.get_signer().sign(raw_value)

    def get_choices(self, cutoff=None):
        """Don't include choices in the DRF HTML form"""
        return {}

    def to_internal_value(self, data):
        # Verify the token
        try:
            raw_value = self.verify_token(data)
        except BadSignature:
            self.fail(
                "does_not_exist", slug_name=self.slug_field, value=smart_str(data)
            )
        except (TypeError, ValueError):
            self.fail("invalid")
        return super().to_internal_value(raw_value)

    def to_representation(self, obj):
        return self.get_token(obj)


class OrderTokenField(SignedTokenRelatedField):
    @classmethod
    def get_order_token(cls, order):
        return cls().get_token(order)

    def __init__(self, **kwargs):
        kwargs["queryset"] = Order.objects.all()
        kwargs["slug_field"] = "number"
        super().__init__(**kwargs)


class BasketTokenField(SignedTokenRelatedField):
    @classmethod
    def get_basket_token(cls, basket):
        return cls().get_token(basket)

    def __init__(self, **kwargs):
        kwargs["queryset"] = Basket.objects.all()
        kwargs["slug_field"] = "pk"
        super().__init__(**kwargs)


class PaymentStateSerializer(serializers.Serializer):
    status = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    required_action = serializers.SerializerMethodField()

    def get_required_action(self, state):
        return state.get_required_action() if state.status == PENDING else None


class OrderSerializer(OscarOrderSerializer):
    pass


class CheckoutSerializer(OscarCheckoutSerializer):
    user = serializers.HyperlinkedRelatedField(
        view_name="user-detail",
        required=False,
        queryset=get_user_model().objects.get_queryset(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Build PaymentMethods field
        self.fields["payment"] = PaymentMethodsSerializer(context=self.context)

        # We require a request because we need to know what accounts are valid for the
        # user to be drafting from. This is derived from the user when authenticated or
        # the session store when anonymous
        request = self.context.get("request", None)
        assert request is not None, (
            "`%s` requires the request in the serializer"
            " context. Add `context={'request': request}` when instantiating "
            "the serializer." % self.__class__.__name__
        )

        # Optionally add a captcha field
        captcha_kwargs = None
        if settings.API_CHECKOUT_CAPTCHA:
            if settings.API_CHECKOUT_CAPTCHA is True:
                captcha_kwargs = {
                    "action": "checkout",
                    "required_score": 0.5,
                }
            elif isinstance(settings.API_CHECKOUT_CAPTCHA, dict):
                captcha_kwargs = settings.API_CHECKOUT_CAPTCHA
            elif isinstance(settings.API_CHECKOUT_CAPTCHA, str):
                get_captcha_settings = import_string(settings.API_CHECKOUT_CAPTCHA)
                captcha_kwargs = get_captcha_settings(request)
        if captcha_kwargs:
            self.fields["recaptcha"] = ReCaptchaV3Field(**captcha_kwargs)

        # Limit baskets to only the one that is active and owned by the user.
        basket = get_basket(request)
        self.fields["basket"].queryset = Basket.objects.filter(pk=basket.pk)

    def get_ownership_calc(self):
        if hasattr(settings.ORDER_OWNERSHIP_CALCULATOR, "__call__"):
            return settings.ORDER_OWNERSHIP_CALCULATOR
        return import_string(settings.ORDER_OWNERSHIP_CALCULATOR)

    def get_recaptcha_score(self) -> float | None:
        recaptcha_score = None
        if "recaptcha" in self.fields:
            recaptcha_score = self.fields["recaptcha"].score
        return recaptcha_score

    def validate(self, data):
        # Cache guest email since it might get removed during super validation
        given_user = data.get("user")
        guest_email = data.get("guest_email")

        # Calculate totals and whatnot
        data = super().validate(data)

        # Check that the basket is still valid
        basket_errors = []
        basket = data["basket"]
        for line in basket.all_lines():
            result = basket.strategy.fetch_for_line(line)
            is_permitted, reason = result.availability.is_purchase_permitted(
                line.quantity
            )
            if not is_permitted:
                # Create a meaningful message to return in the error response
                # Translators: User facing error message in checkout
                msg = _(
                    "'%(title)s' is no longer available to buy (%(reason)s). Please adjust your basket to continue."
                ) % {
                    "title": line.product.get_title(),
                    "reason": reason,
                }
                basket_errors.append(msg)
        if len(basket_errors) > 0:
            raise serializers.ValidationError({"basket": basket_errors})

        # Screen the order through the enabled fraud rules. A rule will raise a
        # serializers.ValidationError() if it finds something fishy.
        fraud.run_enabled_fraud_checks(
            data=data,
            recaptcha_score=self.get_recaptcha_score(),
            request=self.context.get("request", None),
        )

        # Figure out who should own the order
        request = self.context["request"]
        ownership_calc = self.get_ownership_calc()
        user, guest_email = ownership_calc(request, given_user, guest_email)
        if not ((user and user.email) or guest_email):
            # Translators: User facing error message in checkout
            raise serializers.ValidationError(_("Email address is required."))
        data["user"] = user
        data["guest_email"] = guest_email

        # Allow application to calculate taxes before the total is calculated
        pre_calculate_total.send(
            sender=self.__class__,
            basket=data["basket"],
            shipping_address=data["shipping_address"],
            shipping_charge=data["shipping_charge"],
        )

        # Figure out the final total order price
        data["total"] = OrderTotalCalculator().calculate(
            data["basket"], data["shipping_charge"]
        )

        # Payment amounts specified must not be more than the order total
        posted_total = Decimal("0.00")
        methods = {
            k: v
            for k, v in data["payment"].items()
            if v["enabled"] and not v["pay_balance"]
        }
        for code, method in methods.items():
            posted_total += method["amount"]

        if posted_total > data["total"].incl_tax:
            # Translators: User facing error message in checkout
            raise serializers.ValidationError(
                _("Specified payment amounts exceed order total.")
            )

        return data

    @transaction.atomic()
    def create(self, validated_data):
        basket = validated_data.get("basket")
        order_number = self.generate_order_number(basket)

        billing_address = None
        if "billing_address" in validated_data:
            billing_address = BillingAddress(**validated_data["billing_address"])

        shipping_address = None
        if "shipping_address" in validated_data:
            shipping_address = ShippingAddress(**validated_data["shipping_address"])

        # Place the order
        try:
            order = self._insupd_order(
                basket=basket,
                user=validated_data.get("user") or AnonymousUser(),
                order_number=order_number,
                billing_address=billing_address,
                shipping_address=shipping_address,
                order_total=validated_data.get("total"),
                shipping_method=validated_data.get("shipping_method"),
                shipping_charge=validated_data.get("shipping_charge"),
                guest_email=validated_data.get("guest_email") or "",
            )
        except ValueError as e:
            raise exceptions.NotAcceptable(str(e))

        # Return the order
        return order

    def _insupd_order(
        self, basket, user=None, shipping_address=None, billing_address=None, **kwargs
    ):
        existing_orders = basket.order_set.all()
        if existing_orders.exclude(
            status=settings.ORDER_STATUS_PAYMENT_DECLINED
        ).exists():
            # Translators: User facing error message in checkout
            raise exceptions.NotAcceptable(
                _("An non-declined order already exists for this basket.")
            )

        existing_count = existing_orders.count()
        if existing_count > 1:
            # Translators: User facing error message in checkout
            raise exceptions.NotAcceptable(
                _(
                    "Multiple order exist for this basket! This should never happen and we don't know what to do."
                )
            )

        # Get request object from context
        request = self.context.get("request", None)

        # If no orders were pre-existing, make a new one.
        if existing_count == 0:
            return self.place_order(
                basket=basket,
                user=user,
                shipping_address=shipping_address,
                billing_address=billing_address,
                request=request,
                **kwargs,
            )

        # Update this order instead of making a new one.
        order = existing_orders.first()
        kwargs["order_number"] = order.number
        status = self.get_initial_order_status(basket)
        shipping_address = self.create_shipping_address(
            user=user, shipping_address=shipping_address
        )
        billing_address = self.create_billing_address(
            user=user,
            billing_address=billing_address,
            shipping_address=shipping_address,
            **kwargs,
        )
        return utils.OrderUpdater().update_order(
            order=order,
            basket=basket,
            user=user,
            shipping_address=shipping_address,
            billing_address=billing_address,
            status=status,
            request=request,
            **kwargs,
        )


class CompleteDeferredPaymentSerializer(serializers.Serializer):
    order = OrderTokenField(
        help_text=_(
            "Server-signed order number token used to identify the order and verify the client has permission to modify it."
        )
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Build PaymentMethods field
        self.fields["payment"] = PaymentMethodsSerializer(context=self.context)
