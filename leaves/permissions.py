from rest_framework.permissions import BasePermission


class CannotReviewOwnLeave(BasePermission):
    """Object-level rule: nobody can approve/reject a leave they requested."""

    message = "You cannot approve or reject your own leave."

    def has_object_permission(self, request, view, obj):
        return obj.employee_id != request.user.id


class IsLeaveOwnerOrAdmin(BasePermission):
    """Object-level rule: only the owner (or an admin) may delete a leave."""

    message = "You can only delete your own leave."

    def has_object_permission(self, request, view, obj):
        return request.user.is_admin or obj.employee_id == request.user.id
