from django.contrib import admin

from .models import Leave


@admin.register(Leave)
class LeaveAdmin(admin.ModelAdmin):
    list_display = ("id", "employee", "leave_type", "start_date", "end_date", "status", "approved_by")
    list_filter = ("status", "leave_type")
    search_fields = ("employee__name", "employee__email", "reason")
    list_select_related = ("employee", "approved_by")
    ordering = ("-created_at",)
