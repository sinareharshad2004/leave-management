"""
Business logic for leaves.

Views stay thin (HTTP only); the rules live here so they can be re-used
(e.g. from a Celery task later) and tested in one place.
"""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError

from .exceptions import LeaveStateConflict
from .models import Leave

User = get_user_model()

# Leaves in these statuses "block" the calendar. A REJECTED leave does not.
BLOCKING_STATUSES = (Leave.Status.PENDING, Leave.Status.APPROVED)


def find_overlapping_leaves(employee, start_date, end_date):
    """
    Return the employee's active leaves that overlap [start_date, end_date].

    Two inclusive ranges overlap when each starts on/before the other ends:
        existing.start <= new.end  AND  existing.end >= new.start
    Example: existing 10-12 Nov vs new 11-15 Nov -> 10 <= 15 and 12 >= 11 -> overlap.
    """
    return Leave.objects.filter(
        employee=employee,
        status__in=BLOCKING_STATUSES,
        start_date__lte=end_date,
        end_date__gte=start_date,
    )


def overlap_message(conflict):
    return (
        f"You already have a {conflict.status.lower()} leave from "
        f"{conflict.start_date} to {conflict.end_date} that overlaps these dates."
    )


def create_leave(*, employee, leave_type, start_date, end_date, reason):
    """
    Create a PENDING leave without allowing overlaps.

    The serializer already checks overlap to give a friendly error, but two
    requests sent at the same moment could both pass that check. So we check
    again inside a transaction after locking the employee's row; the second
    request waits for the first one to commit and then sees its leave.
    (On PostgreSQL select_for_update really locks; SQLite ignores it.)
    """
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


def _review_leave(*, leave_id, reviewer, new_status):
    """Shared logic for approve / reject."""
    if not reviewer.can_review_leaves:
        raise PermissionDenied("Only managers or admins can review leaves.")

    with transaction.atomic():
        # Lock the row. If two managers click "approve" together, the second
        # one waits here, then sees status != PENDING and gets a 409.
        leave = get_object_or_404(Leave.objects.select_for_update(), pk=leave_id)

        if leave.employee_id == reviewer.id:
            raise PermissionDenied("You cannot review your own leave.")

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
    """Delete a leave, but only while it is still PENDING."""
    with transaction.atomic():
        leave = get_object_or_404(Leave.objects.select_for_update(), pk=leave_id)

        if not (actor.is_admin or leave.employee_id == actor.id):
            raise PermissionDenied("You can only delete your own leave.")

        if leave.status != Leave.Status.PENDING:
            raise LeaveStateConflict(
                f"Only PENDING leaves can be deleted. This leave is already {leave.status}."
            )
        leave.delete()
