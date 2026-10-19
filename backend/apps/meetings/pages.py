"""Server-authorized MVT entry points for meeting pages."""

from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_safe

from config.page_support import member_page, render_page

from .access import readable_meetings


@require_safe
@member_page
def meetings_page(request):
    return render_page(request, "meetings", "Reuniões")


@require_safe
@member_page
def new_meeting_page(request):
    return render_page(request, "new_meeting", "Nova reunião")


@require_safe
@member_page
def meeting_page(request, meeting_id, tab="transcript"):
    meeting = get_object_or_404(readable_meetings(request.user), pk=meeting_id)
    return render_page(request, "meeting", meeting.title, meeting=meeting, tab=tab)
