from rest_framework.routers import SimpleRouter

from .views import LeaveViewSet

# SimpleRouter (not DefaultRouter) so the API-root view doesn't clash with
# the list route registered on the empty prefix.
router = SimpleRouter()
router.register("", LeaveViewSet, basename="leave")

urlpatterns = router.urls
