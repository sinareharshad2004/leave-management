from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from . import services
from .models import Leave

User = get_user_model() 


class EmployeeSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "email"]
        read_only_fields = fields


class LeaveSerializer(serializers.ModelSerializer):
    # Nested + read-only: needs select_related("employee") in the queryset.
    employee = EmployeeSummarySerializer(read_only=True)
    # None when nobody has reviewed the leave yet. Needs select_related("approved_by").
    approved_by_name = serializers.CharField(
        source="approved_by.name", read_only=True, default=None
    )

    class Meta:
        model = Leave
        fields = [
            "id",
            "employee",
            "leave_type",
            "start_date",
            "end_date",
            "reason",
            "status",
            "approved_by",
            "approved_by_name",
            "created_at",
        ]
        # Clients can never set these; the server controls them.
        read_only_fields = ["id", "status", "approved_by", "created_at"]
        extra_kwargs = {"reason": {"max_length": 1000}}

    def validate(self, attrs):
        start_date = attrs["start_date"]
        end_date = attrs["end_date"]

        errors = {}
        if start_date > end_date:
            errors["end_date"] = "End date must be on or after the start date."
        if start_date < timezone.localdate():
            errors["start_date"] = "Start date cannot be in the past."
        if errors:
            raise serializers.ValidationError(errors)

        employee = self.context["request"].user
        conflict = services.find_overlapping_leaves(
            employee, start_date, end_date
        ).first()
        if conflict:
            raise serializers.ValidationError(services.overlap_message(conflict))

        return attrs

    def create(self, validated_data):
        # The employee always comes from the token, never from the request body.
        return services.create_leave(
            employee=self.context["request"].user, **validated_data
        )
