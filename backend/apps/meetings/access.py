"""Single server-side policy for meeting access.

All media and artifact endpoints resolve through the viewset's filtered queryset.
Administrators do not silently bypass this policy on the public API.
"""

from django.db.models import Q

from .models import Meeting


def _active_sector_id(user):
    if not user.is_authenticated or not user.is_active:
        return None
    from apps.accounts.models import UserMembership

    return (
        UserMembership.objects.filter(
            user=user, sector__is_active=True,
        )
        .values_list("sector_id", flat=True)
        .first()
    )


def manageable_meetings(user):
    sector_id = _active_sector_id(user)
    if sector_id is None:
        return Meeting.objects.none()
    return Meeting.objects.filter(
        owner=user, sector_id=sector_id, deletion_requested_at__isnull=True
    )


def readable_meetings(user):
    sector_id = _active_sector_id(user)
    if sector_id is None:
        return Meeting.objects.none()
    return Meeting.objects.filter(
        sector_id=sector_id, deletion_requested_at__isnull=True,
        staged_at__isnull=True,
    ).filter(
        Q(owner=user) | Q(shared_with_sector=True)
    )


def can_manage(meeting, user):
    return bool(
        meeting.deletion_requested_at is None
        and _active_sector_id(user) == meeting.sector_id
        and meeting.owner_id == user.pk
    )
