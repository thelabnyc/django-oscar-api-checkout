from django.http import HttpRequest
from oscar.core.loading import get_class

OrderPlacementMixin = get_class("checkout.mixins", "OrderPlacementMixin")


class OrderMessageSender(OrderPlacementMixin):
    def __init__(self, request: HttpRequest):
        self.request = request
