from rest_framework import status
from rest_framework.exceptions import APIException


class LeaveStateConflict(APIException):
    """Raised when an action is not allowed in the leave's current status."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "This action is not allowed for the leave's current status."
    default_code = "leave_state_conflict"
