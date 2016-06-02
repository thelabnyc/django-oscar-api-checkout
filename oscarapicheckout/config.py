from django.apps import AppConfig


class Config(AppConfig):
    name = 'oscarapicheckout'
    label = 'oscarapicheckout'

    def ready(self):
        # Register signal handlers
        from . import handlers  # NOQA
