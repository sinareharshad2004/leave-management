"""
Read-side rules: WHICH leaves a user is allowed to see.

Authorization happens in the database query, not in Python. A user's queryset
simply does not contain rows they may not see, so a guessed id is a 404.

    EMPLOYEE -> only their own leaves
    MANAGER  -> their own leaves + the leaves of employees
                (NOT other managers' or admins' leaves)
    ADMIN    -> every leave, including managers' leaves
"""
from django.contrib.auth import get_user_model
from django.db.models import Q

from users.enums import Role

from .models import Leave

User = get_user_model()


def visible_leaves(user):
    """Leaves `user` may see. select_related avoids N+1 queries in serializers."""
    queryset = Leave.objects.select_related("employee", "approved_by", "deleted_by")
    if user.is_admin:
        return queryset
    if user.is_manager:
        return queryset.filter(Q(employee=user) | Q(employee__role=Role.EMPLOYEE))
    return queryset.filter(employee=user)


def own_leaves(user):
    """The user's own leaves (deleted ones included, so the history stays visible)."""
    return visible_leaves(user).filter(employee=user)


def other_leaves(user):
    """Leaves of other people that `user` is allowed to see."""
    return visible_leaves(user).exclude(employee=user)


def visible_leave_owners(user):
    """People whose leaves `user` can see (used for the 'Employee' filter dropdown)."""
    if user.is_admin:
        return User.objects.filter(role__in=[Role.EMPLOYEE, Role.MANAGER]).order_by("name")
    if user.is_manager:
        return User.objects.filter(Q(role=Role.EMPLOYEE) | Q(pk=user.pk)).order_by("name")
    return User.objects.filter(pk=user.pk)
