from django.contrib import admin

from .models import Leave

from .models import Holiday

admin.site.register(Holiday)

@admin.register(Leave)
class LeaveAdmin(admin.ModelAdmin):
    list_display = ("id", "employee", "leave_type", "start_date", "end_date", "status", "approved_by", "deleted_by", "deleted_at")
    list_filter = ("status", "leave_type")
    search_fields = ("employee__name", "employee__email", "reason")
    list_select_related = ("employee", "approved_by", "deleted_by")
    ordering = ("-created_at",)
