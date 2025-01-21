from typing import TYPE_CHECKING

from django.http import HttpRequest
from oscar.core.loading import get_class

if TYPE_CHECKING:
    from oscar.apps.checkout.mixins import OrderPlacementMixin
else:
    OrderPlacementMixin = get_class("checkout.mixins", "OrderPlacementMixin")


class OrderMessageSender(OrderPlacementMixin):
    def __init__(self, request: HttpRequest):
        self.request = request
