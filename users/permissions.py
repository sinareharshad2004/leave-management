from rest_framework.permissions import BasePermission
from .enums import Role

class IsAdminRole(BasePermission):
    """Allow access only to users whose role is ADMIN."""

    message = "Only admins can perform this action."

    def has_permission(self, request, view):
        # user = request.user
        # return bool(user and user.is_authenticated and user.is_admin)
        return request.user.is_authenticated and request.user.role == Role.ADMIN

class IsManagerOrAdmin(BasePermission):
    """Allow access only to users whose role is MANAGER or ADMIN."""

    message = "Only managers or admins can perform this action."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.can_review_leaves)


class IsEmployeeRole(BasePermission):
    """Allow access only to users whose role is EMPLOYEE (e.g. creating leave)."""

    message = "Only employees can create leave requests."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == "EMPLOYEE")


class IsEmployeeOrManager(BasePermission):
    """Roles that can apply for leave: EMPLOYEE and MANAGER (not ADMIN)."""

    message = "Only employees and managers can create leave requests."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role in ("EMPLOYEE", "MANAGER"))
