import django_filters

from .models import Leave


class LeaveFilter(django_filters.FilterSet):
    """?status=PENDING&leave_type=SICK&employee=5"""

    employee = django_filters.NumberFilter(field_name="employee_id")

    class Meta:
        model = Leave
        fields = ["status", "leave_type", "employee"]
