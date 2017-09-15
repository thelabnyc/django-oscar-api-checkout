from oscar.apps.order.utils import OrderCreator as BaseOrderCreator
from oscarapicheckout.mixins import OrderCreatorMixin
import math
import time
import random


class OrderNumberGenerator(object):
    def order_number(self, basket):
        base_num = int(math.floor(time.time() / (3600 * 24)))
        basket_id = str(basket.id).zfill(3)[::-1]
        suffix = random.randrange(100, 999)
        number = 'O' + str(base_num) + basket_id + str(suffix)
        return number


class OrderCreator(OrderCreatorMixin, BaseOrderCreator):
    pass
