from .access import manageable_meetings


def owned_meetings(user):
    """The only queryset entry point for user-facing meeting access."""
    return manageable_meetings(user)
