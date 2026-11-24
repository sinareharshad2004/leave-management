from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.permissions import IsManagerOrAdmin

from . import services
from .filters import LeaveFilter
from .models import Leave
from .permissions import CannotReviewOwnLeave, IsLeaveOwnerOrAdmin
from .serializers import LeaveSerializer


class LeaveViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    POST   /api/leaves/                 create a leave (any logged-in user)
    GET    /api/leaves/                 list (employee: own, manager/admin: all)
    GET    /api/leaves/{id}/            retrieve
    DELETE /api/leaves/{id}/            delete own PENDING leave
    GET    /api/leaves/pending/         pending leaves of other people (manager/admin)
    PATCH  /api/leaves/{id}/approve/    approve (manager/admin)
    PATCH  /api/leaves/{id}/reject/     reject  (manager/admin)
    """

    serializer_class = LeaveSerializer
    filterset_class = LeaveFilter
    search_fields = ["employee__name", "employee__email", "reason"]
    ordering_fields = ["created_at", "start_date", "end_date", "status"]
    ordering = ["-created_at", "-id"]

    permission_classes_by_action = {
        "pending": [IsAuthenticated, IsManagerOrAdmin],
        "approve": [IsAuthenticated, IsManagerOrAdmin, CannotReviewOwnLeave],
        "reject": [IsAuthenticated, IsManagerOrAdmin, CannotReviewOwnLeave],
        "destroy": [IsAuthenticated, IsLeaveOwnerOrAdmin],
    }

    def get_permissions(self):
        classes = self.permission_classes_by_action.get(self.action, [IsAuthenticated])
        return [permission() for permission in classes]

    def get_queryset(self):
        """
        Authorization at the queryset level: an employee's queryset only
        contains their own rows, so another employee's leave id is simply a 404.

        select_related() joins employee and approved_by in the SAME query.
        Without it the serializer would run 1-2 extra queries per leave (N+1).
        Both are ForeignKeys (one related row each), which is what
        select_related is meant for.
        """
        queryset = Leave.objects.select_related("employee", "approved_by")
        user = self.request.user
        if user.can_review_leaves:
            return queryset
        return queryset.filter(employee=user)

    def perform_destroy(self, instance):
        services.delete_pending_leave(leave_id=instance.pk, actor=self.request.user)

    @action(detail=False, methods=["get"])
    def pending(self, request):
        # A reviewer cannot act on their own leave, so hide it from their inbox.
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
        # get_object() applies the queryset + object permissions (404 / 403).
        leave = self.get_object()
        service_function(leave_id=leave.pk, reviewer=request.user)
        # Re-read with select_related so the response is complete and N+1 free.
        leave = self.get_queryset().get(pk=leave.pk)
        return Response(self.get_serializer(leave).data)
