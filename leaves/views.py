from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.permissions import IsEmployeeOrManager, IsManagerOrAdmin

from . import selectors, services
from .filters import LeaveFilter
from .models import Leave
from .permissions import CannotReviewOwnLeave, IsLeaveOwner
from .serializers import LeaveSerializer


class LeaveViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    POST   /api/leaves/                 create own leave (employee, manager)
    GET    /api/leaves/                 list (employee: own, manager: employees + own, admin: all)
    GET    /api/leaves/{id}/            retrieve
    PATCH  /api/leaves/{id}/            edit own PENDING leave
    DELETE /api/leaves/{id}/            delete own PENDING leave (soft delete: status DELETED)
    GET    /api/leaves/pending/         pending leaves this user can review
    PATCH  /api/leaves/{id}/approve/    approve (manager: employee leaves, admin: any)
    PATCH  /api/leaves/{id}/reject/     reject  (manager: employee leaves, admin: any)

    The views only deal with HTTP. Which rows a user can see lives in
    selectors.py and every business rule lives in services.py.
    """

    serializer_class = LeaveSerializer
    filterset_class = LeaveFilter
    search_fields = ["employee__name", "employee__email", "reason"]
    ordering_fields = ["created_at", "start_date", "end_date", "status"]
    ordering = ["-created_at", "-id"]

    permission_classes_by_action = {
        "create": [IsAuthenticated, IsEmployeeOrManager],
        "pending": [IsAuthenticated, IsManagerOrAdmin],
        "approve": [IsAuthenticated, IsManagerOrAdmin, CannotReviewOwnLeave],
        "reject": [IsAuthenticated, IsManagerOrAdmin, CannotReviewOwnLeave],
        "update": [IsAuthenticated, IsLeaveOwner],
        "partial_update": [IsAuthenticated, IsLeaveOwner],
        "destroy": [IsAuthenticated, IsLeaveOwner],
    }

    def get_permissions(self):
        classes = self.permission_classes_by_action.get(self.action, [IsAuthenticated])
        return [permission() for permission in classes]

    def get_queryset(self):
        """
        Authorization at the queryset level (see selectors.visible_leaves):
        a user's queryset only contains the rows they may see, so someone
        else's leave id is simply a 404. The database does the filtering,
        and select_related avoids N+1 queries.
        """
        return selectors.visible_leaves(self.request.user)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        # get_object() applies the scoped queryset (404) and IsLeaveOwner (403).
        leave = self.get_object()
        # A decided leave is refused BEFORE validating the new data, so the
        # answer is a clear 409 instead of a confusing validation error.
        services.ensure_pending(leave, "edited")

        serializer = self.get_serializer(leave, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()  # -> services.update_leave (re-checks under a row lock)

        leave = self.get_queryset().get(pk=leave.pk)
        return Response(self.get_serializer(leave).data)

    def perform_destroy(self, instance):
        services.delete_pending_leave(leave_id=instance.pk, actor=self.request.user)

    @action(detail=False, methods=["get"])
    def pending(self, request):
        # A reviewer cannot act on their own leave, so hide it from their inbox.
        # get_queryset() already limits a manager to employee leaves.
        queryset = self.filter_queryset(
            self.get_queryset()
            .filter(status=Leave.Status.PENDING)
            .exclude(employee=request.user)
        )
        page = self.paginate_queryset(queryset)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(queryset, many=True).data)

    @action(detail=True, methods=["patch"])
    def approve(self, request, pk=None):
        return self._review(request, services.approve_leave)

    @action(detail=True, methods=["patch"])
    def reject(self, request, pk=None):
        return self._review(request, services.reject_leave)

    def _review(self, request, service_function):
        # get_object() applies the scoped queryset + object permissions (404 / 403).
        leave = self.get_object()
        service_function(leave_id=leave.pk, reviewer=request.user)
        # Re-read with select_related so the response is complete and N+1 free.
        leave = self.get_queryset().get(pk=leave.pk)
        return Response(self.get_serializer(leave).data)
