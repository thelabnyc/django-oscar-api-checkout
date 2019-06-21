from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class Config(AppConfig):
    name = 'oscarapicheckout'
    label = 'oscarapicheckout'
    # Translators: Backend Library Name
    verbose_name = _('Oscar API-Checkout')

    def ready(self):
        # Register signal handlers
        from . import handlers  # NOQA
