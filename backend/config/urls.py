from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.accounts.pages import account_page, login_page
from apps.admin_panel.pages import admin_login_page, admin_page
from apps.admin_panel.permissions import ActiveStaff
from apps.meetings.pages import meeting_page, meetings_page, new_meeting_page

urlpatterns = [
    path("", meetings_page, name="mvt-meetings"),
    path("login/", login_page, name="mvt-login"),
    path("reunioes/nova/", new_meeting_page, name="mvt-new-meeting"),
    path("reunioes/<uuid:meeting_id>/", meeting_page, name="mvt-meeting"),
    path("reunioes/<uuid:meeting_id>/ata/", meeting_page, {"tab": "ata"}, name="mvt-minutes"),
    path("reunioes/<uuid:meeting_id>/mapa/", meeting_page, {"tab": "mapa"}, name="mvt-map"),
    path("conta/", account_page, name="mvt-account"),
    path("admin/login/", admin_login_page, name="mvt-admin-login"),
    path("admin/", admin_page, name="mvt-admin"),
    path("health/", lambda request: JsonResponse({"status": "ok"})),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.meetings.urls")),
    path("api/admin/", include("apps.admin_panel.urls")),
    path(
        "api/schema/", SpectacularAPIView.as_view(permission_classes=[ActiveStaff]), name="schema"
    ),
    path("api/docs/", SpectacularSwaggerView.as_view(
        url_name="schema", permission_classes=[ActiveStaff]
    ), name="swagger-ui"),
]
