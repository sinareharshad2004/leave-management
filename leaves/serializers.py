from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from . import services
from .models import Leave

User = get_user_model()


class EmployeeSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "email", "role","review_comment"]
        read_only_fields = fields


class LeaveSerializer(serializers.ModelSerializer):
    # Nested + read-only: needs select_related("employee") in the queryset.
    employee = EmployeeSummarySerializer(read_only=True)
    # None when nobody has reviewed the leave yet. Needs select_related("approved_by").
    approved_by_name = serializers.CharField(
        source="approved_by.name", read_only=True, default=None
    )
    # Set only after the owner deleted their own pending leave (status DELETED).
    deleted_by_name = serializers.CharField(
        source="deleted_by.name", read_only=True, default=None
    )
    # Drives the buttons in a UI: false once the leave is APPROVED / REJECTED,
    # or when the current user is not the owner.
    can_modify = serializers.SerializerMethodField(
        help_text="true while the owner may still edit or delete this leave."
    )
    can_review = serializers.SerializerMethodField(
        help_text="true while the current user may still approve or reject this leave."
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
            "deleted_by",
            "deleted_by_name",
            "deleted_at",
            "created_at",
            "can_modify",
            "can_review",
        ]
        # Clients can never set these; the server controls them.
        read_only_fields = [
            "id",
            "status",
            "approved_by",
            "deleted_by",
            "deleted_at",
            "created_at",
        ]
        extra_kwargs = {"reason": {"max_length": 1000}}

    def _user(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    def get_can_modify(self, obj):
        user = self._user()
        return bool(user and user.is_authenticated and services.can_modify_leave(obj, user))

    def get_can_review(self, obj):
        user = self._user()
        return bool(user and user.is_authenticated and services.can_review_leave(obj, user))

    def validate(self, attrs):
        instance = self.instance  # None when creating, the Leave when editing
        start_date = attrs.get("start_date", instance.start_date if instance else None)
        end_date = attrs.get("end_date", instance.end_date if instance else None)

        errors = {}
        if start_date > end_date:
            errors["end_date"] = "End date must be on or after the start date."

        # Past dates are refused for new leaves and when the start date is being
        # changed. Editing only the reason of a leave that already started is fine.
        start_changed = instance is None or start_date != instance.start_date
        if start_changed and start_date < timezone.localdate():
            errors["start_date"] = "Start date cannot be in the past."
        if errors:
            raise serializers.ValidationError(errors)

        if services.count_working_days(start_date, end_date) == 0:
           raise serializers.ValidationError(
               "This leave has no working days. Please select a valid date range."
           )
        employee = instance.employee if instance else self.context["request"].user
        conflict = services.find_overlapping_leaves(
            employee,
            start_date,
            end_date,
            exclude_leave_id=instance.pk if instance else None,
        ).first()
        if conflict:
            raise serializers.ValidationError(services.overlap_message(conflict))

        return attrs

    def create(self, validated_data):
        # The employee always comes from the token, never from the request body.
        return services.create_leave(
            employee=self.context["request"].user, **validated_data
        )

    def update(self, instance, validated_data):
        return services.update_leave(
            leave_id=instance.pk, actor=self.context["request"].user, **validated_data
        )

    def get_working_days(self, obj):
        return services.count_working_days(obj.start_date, obj.end_date)