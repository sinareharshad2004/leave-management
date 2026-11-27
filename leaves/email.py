from django.conf import settings
from django.core.mail import send_mail

def send_leave_request_email(leave):
    employee = leave.employee
    if not employee.email:
        return
    status = leave.status.lower()
    subject = f"Your leave request has been {status}"
    message = (
        f"hi {employee.get_full_name() or employee.username},\n\n"
        f""
    )