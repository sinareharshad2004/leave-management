from rest_framework.permissions import BasePermission


class CannotReviewOwnLeave(BasePermission):
    """Object-level rule: nobody can approve/reject a leave they requested."""

    message = "You cannot approve or reject your own leave."

    def has_object_permission(self, request, view, obj):
        return obj.employee_id != request.user.id


class IsLeaveOwner(BasePermission):
    """
    Object-level rule: only the person who requested a leave may edit or delete it.
    Admins can SEE every leave but cannot change someone else's request.
    """

    message = "You can only change your own leave."

    def has_object_permission(self, request, view, obj):
        return obj.employee_id == request.user.id
