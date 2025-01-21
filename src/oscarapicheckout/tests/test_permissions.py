from rest_framework.test import APIRequestFactory

from ..permissions import Public, StaffOnly
from .base import BaseTest


class PublicTest(BaseTest):
    def test_public_anon(self):
        factory = APIRequestFactory()
        request = factory.get("/")
        self.assertTrue(Public().is_permitted(request))

    def test_public_not_staff(self):
        user = self.login(is_staff=False)
        factory = APIRequestFactory()
        request = factory.get("/")
        self.assertTrue(Public().is_permitted(request, user))

    def test_public_is_staff(self):
        user = self.login(is_staff=True)
        factory = APIRequestFactory()
        request = factory.get("/")
        self.assertTrue(Public().is_permitted(request, user))


class StaffOnlyTest(BaseTest):
    def test_staff_only_anon(self):
        factory = APIRequestFactory()
        request = factory.get("/")
        self.assertFalse(StaffOnly().is_permitted(request))

    def test_staff_only_not_staff(self):
        user = self.login(is_staff=False)
        factory = APIRequestFactory()
        request = factory.get("/")
        self.assertFalse(StaffOnly().is_permitted(request, user))

    def test_staff_only_is_staff(self):
        user = self.login(is_staff=True)
        factory = APIRequestFactory()
        request = factory.get("/")
        self.assertTrue(StaffOnly().is_permitted(request, user))
