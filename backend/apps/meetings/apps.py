from django.apps import AppConfig


class MeetingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.meetings"

    def ready(self):
        from . import ai_checks  # noqa: F401 - register Django deployment checks
