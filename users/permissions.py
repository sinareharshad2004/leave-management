from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    """Allow access only to users whose role is ADMIN."""

    message = "Only admins can perform this action."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_admin)


class IsManagerOrAdmin(BasePermission):
    """Allow access only to users whose role is MANAGER or ADMIN."""

    message = "Only managers or admins can perform this action."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.can_review_leaves)
