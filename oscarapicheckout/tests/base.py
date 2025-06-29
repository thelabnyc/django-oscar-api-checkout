from django.contrib.auth.models import User
from oscar.core.loading import get_model
from rest_framework.test import APITestCase

Country = get_model("address", "Country")


class BaseTest(APITestCase):
    def setUp(self):
        Country.objects.create(
            display_order=0,
            is_shipping_country=True,
            iso_3166_1_a2="US",
            iso_3166_1_a3="USA",
            iso_3166_1_numeric="840",
            name="United States of America",
            printable_name="United States",
        )

    def login(self, is_staff=False, email="joe@example.com"):
        user = User.objects.create_user(username="joe", password="schmoe", email=email)
        user.is_staff = is_staff
        user.save()
        self.client.login(username="joe", password="schmoe")
        return user
