from leaves.models import LeaveNotification


def leave_notifications(request):
    """Expose only the signed-in user's unread notifications to page templates."""
    if not request.user.is_authenticated:
        return {"leave_notifications": []}
    return {
        "leave_notifications": LeaveNotification.objects.filter(
            recipient=request.user, read_at__isnull=True
        )[:5]
    }
