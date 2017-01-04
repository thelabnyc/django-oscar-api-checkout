from django.contrib.auth.models import User
from rest_framework.test import APITestCase


class BaseTest(APITestCase):
    fixtures = ['api-checkout-test']

    def login(self, is_staff=False, email='joe@example.com'):
        user = User.objects.create_user(username='joe', password='schmoe', email=email)
        user.is_staff = is_staff
        user.save()
        self.client.login(username='joe', password='schmoe')
        return user
