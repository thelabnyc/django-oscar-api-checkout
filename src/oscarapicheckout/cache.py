from django.core.cache import cache
from django.utils.module_loading import import_string
from rest_framework import serializers
from oscar.core.loading import get_model
from . import settings as pkgsettings

Country = get_model('address', 'Country')


class EmailAddressSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ShippingMethodSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=128)
    name = serializers.CharField(max_length=128)
    price = serializers.DecimalField(decimal_places=2, max_digits=12)


class AbstractCheckoutCache(object):
    serializer_class_path = None
    cache_timeout = (60 * 60 * 24)  # 24 hours

    def __init__(self, basket_id, enable_validation=True):
        self.basket_id = basket_id
        self.enable_validation = enable_validation

    @property
    def cache_key(self):
        return 'oscarapicheckout.cache.{}.{}'.format(self.__class__.__name__, self.basket_id)

    def set(self, data):
        data = self._transform_incoming_data(data)
        cache.set(self.cache_key, data, self.cache_timeout)

    def get(self):
        data = cache.get(self.cache_key)
        return self._transform_outgoing_data(data)

    def invalidate(self):
        cache.delete(self.cache_key)

    def _transform_incoming_data(self, data):
        if self.enable_validation:
            serializer = self._get_serializer(data)
            if serializer:
                serializer.is_valid(raise_exception=True)
                data = serializer.validated_data
        return data

    def _transform_outgoing_data(self, data):
        return data

    def _get_serializer(self, data):
        serializer_class = self._get_serializer_class()
        if serializer_class:
            serializer_class(data=data)
        return None

    def _get_serializer_class(self):
        if self.serializer_class_path:
            import_string(self.serializer_class_path)
        return None


class AbstractCheckoutAddressCache(AbstractCheckoutCache):
    def _transform_incoming_data(self, data):
        data = super()._transform_incoming_data(data)
        if data and 'country' in data and hasattr(data['country'], 'pk'):
            data['country'] = data['country'].pk
        return data

    def _transform_outgoing_data(self, data):
        data = super()._transform_outgoing_data(data)
        if data and 'country' in data and not hasattr(data['country'], 'pk'):
            try:
                data['country'] = Country.objects.get(pk=data['country'])
            except Country.DoesNotExist:
                data['country'] = None
        return data


class EmailAddressCache(AbstractCheckoutCache):
    serializer_class_path = pkgsettings.CHECKOUT_CACHE_SERIALIZERS.get('email_address', 'oscarapicheckout.cache.EmailAddressSerializer')


class ShippingAddressCache(AbstractCheckoutAddressCache):
    serializer_class_path = pkgsettings.CHECKOUT_CACHE_SERIALIZERS.get('shipping_address', 'oscarapi.serializers.checkout.ShippingAddressSerializer')


class BillingAddressCache(AbstractCheckoutAddressCache):
    serializer_class_path = pkgsettings.CHECKOUT_CACHE_SERIALIZERS.get('billing_address', 'oscarapi.serializers.checkout.BillingAddressSerializer')


class ShippingMethodCache(AbstractCheckoutCache):
    serializer_class_path = pkgsettings.CHECKOUT_CACHE_SERIALIZERS.get('shipping_method', 'oscarapicheckout.cache.ShippingMethodSerializer')
