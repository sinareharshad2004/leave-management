"""python manage.py seed_demo  ->  6 employees, 2 managers, 1 admin and sample leaves."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from leaves.models import Leave

User = get_user_model()
PASSWORD = "StrongPass123!"
EMPLOYEES = ["Emma", "Oliver", "Asha", "Ravi", "Sofia", "Liam"]
MANAGERS = ["Maya", "Mike"]
ADMINS = ["Admin"]
TYPES = ["CASUAL", "SICK", "PAID"]
STATUSES = ["PENDING", "APPROVED", "REJECTED", "PENDING"]


class Command(BaseCommand):
    help = "Create demo employees, managers and leave requests (safe to run twice)."

    def handle(self, *args, **options):
        admins = [self._user(name, "ADMIN") for name in ADMINS]
        managers = [self._user(name, "MANAGER") for name in MANAGERS]
        employees = [self._user(name, "EMPLOYEE") for name in EMPLOYEES]

        today = timezone.localdate()
        created = 0
        for i, employee in enumerate(employees):
            if Leave.objects.filter(employee=employee).exists():
                continue  # already seeded
            for j in range(5):
                start = today + timedelta(days=2 + j * 6 + i)  # spaced out: never overlaps
                status = STATUSES[(i + j) % len(STATUSES)]
                Leave.objects.create(
                    employee=employee,
                    leave_type=TYPES[(i + j) % len(TYPES)],
                    start_date=start,
                    end_date=start + timedelta(days=j % 3),
                    reason=f"Demo leave {j + 1} for {employee.name}",
                    status=status,
                    approved_by=None if status == "PENDING" else managers[j % len(managers)],  # employee leaves: reviewed by a manager
                )
                created += 1

        # A manager's own leave can only be reviewed by an admin.
        for i, manager in enumerate(managers):
            if Leave.objects.filter(employee=manager).exists():
                continue
            start = today + timedelta(days=3 + i * 10)
            Leave.objects.create(
                employee=manager,
                leave_type="PAID",
                start_date=start,
                end_date=start + timedelta(days=1),
                reason=f"Demo leave for manager {manager.name} (waiting for admin)",
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(f"Done. {created} new leaves created."))
        self.stdout.write(f"Password for every demo user: {PASSWORD}")
        for user in admins + managers + employees:
            self.stdout.write(f"  {user.role:9} {user.email}")

    def _user(self, name, role):
        email = f"{name.lower()}@example.com"
        user, created = User.objects.get_or_create(
            email=email, defaults={"name": name, "role": role}
        )
        if created:
            user.set_password(PASSWORD)
            user.save()
        return user
