"""
Business logic for leaves.

Views stay thin (HTTP only); every rule lives here so the API views, the web
pages and tests all share exactly the same behaviour.

Rules implemented here
----------------------
* EMPLOYEE and MANAGER can create their own leave. ADMIN cannot.
* The owner can edit or delete their leave ONLY while it is PENDING.
* "Delete" is a SOFT delete: the row stays in the database with status DELETED,
  plus who deleted it (deleted_by) and when (deleted_at).
* APPROVED / REJECTED / DELETED leaves are final: no edit, no delete, no review.
* Employee leaves are reviewed by a manager or an admin.
* A MANAGER's leave is reviewed by an ADMIN only.
* Nobody can review their own leave.
"""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from users.enums import Role

from .exceptions import LeaveStateConflict
from .models import Leave

User = get_user_model()

# Leaves in these statuses "block" the calendar. REJECTED and DELETED leaves do not.
BLOCKING_STATUSES = (Leave.Status.PENDING, Leave.Status.APPROVED)

# Roles that have their own leave balance and can apply for leave.
LEAVE_APPLICANT_ROLES = (Role.EMPLOYEE, Role.MANAGER)

# Fields the owner may change while the leave is still PENDING.
EDITABLE_FIELDS = ("leave_type", "start_date", "end_date", "reason")


# ------------------------------------------------------------------ policies
# Pure functions: no database writes. The API serializer and the web pages use
# them to decide whether a button is enabled; the actions below use them to
# actually enforce the rule.
def can_create_leave(user):
    return user.role in LEAVE_APPLICANT_ROLES


def can_modify_leave(leave, user):
    """Edit/delete allowed: only the owner, and only before a decision is made."""
    return leave.employee_id == user.id and leave.status == Leave.Status.PENDING


def review_denial_reason(leave, reviewer):
    """
    Why `reviewer` may never review `leave` (regardless of its status).
    Returns None when the reviewer has the right to review it.
    """
    if not reviewer.can_review_leaves:
        return "Only managers or admins can review leaves."
    if leave.employee_id == reviewer.id:
        return "You cannot review your own leave."
    if reviewer.is_manager and leave.employee.role != Role.EMPLOYEE:
        return "Only an admin can review a manager's leave."
    return None


def has_review_rights(leave, reviewer):
    return review_denial_reason(leave, reviewer) is None


def can_review_leave(leave, reviewer):
    """Approve/Reject buttons are enabled: has the right AND still PENDING."""
    return has_review_rights(leave, reviewer) and leave.status == Leave.Status.PENDING


# ------------------------------------------------------------------- queries
def find_overlapping_leaves(employee, start_date, end_date, exclude_leave_id=None):
    """
    Return the employee's active leaves that overlap [start_date, end_date].

    Two inclusive ranges overlap when each starts on/before the other ends:
        existing.start <= new.end  AND  existing.end >= new.start
    Example: existing 10-12 Nov vs new 11-15 Nov -> 10 <= 15 and 12 >= 11 -> overlap.

    `exclude_leave_id` lets a leave be edited without clashing with itself.
    """
    queryset = Leave.objects.filter(
        employee=employee,
        status__in=BLOCKING_STATUSES,
        start_date__lte=end_date,
        end_date__gte=start_date,
    )
    if exclude_leave_id is not None:
        queryset = queryset.exclude(pk=exclude_leave_id)
    return queryset


def overlap_message(conflict):
    return (
        f"You already have a {conflict.status.lower()} leave from "
        f"{conflict.start_date} to {conflict.end_date} that overlaps these dates."
    )


# ------------------------------------------------------------------- actions
def create_leave(*, employee, leave_type, start_date, end_date, reason):
    """
    Create a PENDING leave without allowing overlaps.

    The serializer already checks overlap to give a friendly error, but two
    requests sent at the same moment could both pass that check. So we check
    again inside a transaction after locking the employee's row; the second
    request waits for the first one to commit and then sees its leave.
    (On PostgreSQL select_for_update really locks; SQLite ignores it.)
    """
    if not can_create_leave(employee):
        raise PermissionDenied("Your role cannot create leave requests.")

    with transaction.atomic():
        User.objects.select_for_update().get(pk=employee.pk)

        conflict = find_overlapping_leaves(employee, start_date, end_date).first()
        if conflict:
            raise ValidationError({"non_field_errors": [overlap_message(conflict)]})

        return Leave.objects.create(
            employee=employee,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
        )


def ensure_pending(leave, action):
    """Raise 409 unless the leave is still PENDING. `action` e.g. 'edited'."""
    if leave.status != Leave.Status.PENDING:
        raise LeaveStateConflict(
            f"Only PENDING leaves can be {action}. This leave is already {leave.status}."
        )


def update_leave(*, leave_id, actor, **changes):
    """Edit your own leave, but only while it is still PENDING."""
    changes = {key: value for key, value in changes.items() if key in EDITABLE_FIELDS}

    with transaction.atomic():
        User.objects.select_for_update().get(pk=actor.pk)  # serialise overlap checks
        leave = get_object_or_404(Leave.objects.select_for_update(), pk=leave_id)

        if leave.employee_id != actor.id:
            raise PermissionDenied("You can only edit your own leave.")
        ensure_pending(leave, "edited")

        start_date = changes.get("start_date", leave.start_date)
        end_date = changes.get("end_date", leave.end_date)
        if start_date > end_date:
            raise ValidationError({"end_date": ["End date must be on or after the start date."]})

        conflict = find_overlapping_leaves(
            leave.employee, start_date, end_date, exclude_leave_id=leave.pk
        ).first()
        if conflict:
            raise ValidationError({"non_field_errors": [overlap_message(conflict)]})

        for field, value in changes.items():
            setattr(leave, field, value)
        leave.save(update_fields=list(changes) or None)
    return leave


def _review_leave(*, leave_id, reviewer, new_status):
    """Shared logic for approve / reject."""
    if not reviewer.can_review_leaves:
        raise PermissionDenied("Only managers or admins can review leaves.")

    with transaction.atomic():
        # Lock the row. If two reviewers click "approve" together, the second
        # one waits here, then sees status != PENDING and gets a 409.
        leave = get_object_or_404(Leave.objects.select_for_update(), pk=leave_id)

        denial = review_denial_reason(leave, reviewer)
        if denial:
            raise PermissionDenied(denial)

        if leave.status != Leave.Status.PENDING:
            raise LeaveStateConflict(
                f"Only PENDING leaves can be reviewed. This leave is already {leave.status}."
            )

        leave.status = new_status
        leave.approved_by = reviewer
        leave.save(update_fields=["status", "approved_by"])
    return leave


def approve_leave(*, leave_id, reviewer):
    return _review_leave(
        leave_id=leave_id, reviewer=reviewer, new_status=Leave.Status.APPROVED
    )


def reject_leave(*, leave_id, reviewer):
    return _review_leave(
        leave_id=leave_id, reviewer=reviewer, new_status=Leave.Status.REJECTED
    )


def delete_pending_leave(*, leave_id, actor):
    """
    Delete your own leave, but only while it is still PENDING.

    This is a SOFT delete: nothing is removed from the database. The leave is
    marked DELETED and remembers who deleted it and when, so the history stays
    visible. A deleted leave no longer blocks the calendar and cannot be
    reviewed, edited or deleted again.
    """
    with transaction.atomic():
        leave = get_object_or_404(Leave.objects.select_for_update(), pk=leave_id)

        if leave.employee_id != actor.id:
            raise PermissionDenied("You can only delete your own leave.")
        ensure_pending(leave, "deleted")

        leave.status = Leave.Status.DELETED
        leave.deleted_by = actor
        leave.deleted_at = timezone.now()
        leave.save(update_fields=["status", "deleted_by", "deleted_at"])
    return leave
