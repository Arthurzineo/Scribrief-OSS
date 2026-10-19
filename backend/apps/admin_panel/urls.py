"""Administrative API routes; proxy isolation does not replace ActiveStaff."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AuditAdminViewSet,
    JobAdminViewSet,
    PendingDeletionAdminViewSet,
    SectorAdminViewSet,
    SystemEventAdminViewSet,
    UsageAdminViewSet,
    UserAdminViewSet,
)
from .views.health import AdminHealthView
from .views.providers import AIProviderCatalogView
from .views.sector_prompts import SectorPromptDetailView, SectorPromptListView

router = DefaultRouter()
router.register("sectors", SectorAdminViewSet, basename="admin-sector")
router.register("users", UserAdminViewSet, basename="admin-user")
router.register("usage", UsageAdminViewSet, basename="admin-usage")
router.register("audit", AuditAdminViewSet, basename="admin-audit")
router.register("system-events", SystemEventAdminViewSet, basename="admin-system-event")
router.register("jobs", JobAdminViewSet, basename="admin-job")
router.register("deletions", PendingDeletionAdminViewSet, basename="admin-deletion")
urlpatterns = [
    path("health/", AdminHealthView.as_view(), name="admin-health"),
    path("ai-providers/", AIProviderCatalogView.as_view(), name="admin-ai-providers"),
    path(
        "sectors/<int:sector_id>/ai-prompts/", SectorPromptListView.as_view(),
        name="admin-sector-ai-prompts",
    ),
    path(
        "sectors/<int:sector_id>/ai-prompts/<str:kind>/", SectorPromptDetailView.as_view(),
        name="admin-sector-ai-prompt",
    ),
    *router.urls,
]
