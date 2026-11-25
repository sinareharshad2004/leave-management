from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Leave(models.Model):
    class LeaveType(models.TextChoices):
        CASUAL = "CASUAL", "Casual"
        SICK = "SICK", "Sick"
        PAID = "PAID", "Paid"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        # The owner deleted their own PENDING leave. The row is kept (soft delete)
        # so there is a record of who deleted it and when.
        DELETED = "DELETED", "Deleted"

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="leaves",
    )
    leave_type = models.CharField(max_length=10, choices=LeaveType.choices)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    # The manager/admin who made the decision (approved OR rejected the leave).
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_leaves",
    )
    # Filled only when the owner deletes their own PENDING leave (status DELETED).
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deleted_leaves",
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["employee", "status"], name="leave_employee_status_idx"),
            models.Index(fields=["start_date", "end_date"], name="leave_dates_idx"),
        ]
        constraints = [
            # Last line of defence: the database itself refuses bad date ranges.
            models.CheckConstraint(
                condition=Q(start_date__lte=F("end_date")),
                name="leave_start_date_lte_end_date",
            ),
        ]

    def __str__(self):
        return f"{self.employee_id} {self.leave_type} {self.start_date} -> {self.end_date} ({self.status})"
