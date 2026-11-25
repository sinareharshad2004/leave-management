"""Simple server-rendered pages on top of the existing leave services."""
from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from rest_framework.exceptions import APIException

from leaves import selectors, services
from leaves.models import Leave
from leaves.serializers import LeaveSerializer
from users.enums import Role

from .forms import EmployeeRegisterForm, ManagerRegisterForm

User = get_user_model()

PAGE_SIZE = 10
ORDERINGS = [
    ("-created_at", "Newest first"),
    ("created_at", "Oldest first"),
    ("start_date", "Start date: earliest"),
    ("-start_date", "Start date: latest"),
    ("status", "Status"),
]


def _error_text(exc):
    """Turn a DRF exception into a readable one-line message."""
    detail = exc.detail
    if isinstance(detail, dict):
        parts = []
        for key, value in detail.items():
            value = value if isinstance(value, (list, tuple)) else [value]
            parts.append(f"{key.replace('_', ' ')}: {' '.join(str(v) for v in value)}")
        return " | ".join(parts)
    if isinstance(detail, (list, tuple)):
        return " ".join(str(v) for v in detail)
    return str(detail)


def manager_exists():
    return User.objects.filter(role=Role.MANAGER).exists()


def home_for(user):
    return "web-manager-dashboard" if user.can_review_leaves else "web-employee-dashboard"


def home(request):
    if request.user.is_authenticated:
        return redirect(home_for(request.user))
    return redirect("web-login")


def login_view(request):
    """One login page for everyone. The user's role decides where they land."""
    if request.user.is_authenticated:
        return redirect(home_for(request.user))

    form = AuthenticationForm(request, data=request.POST or None)
    form.fields["username"].label = "Email"
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        login(request, user)
        return redirect(home_for(user))
    return render(
        request,
        "web/login.html",
        {"form": form, "manager_registration_open": not manager_exists()},
    )


def legacy_login(request):
    """Old separate login addresses now go to the single login page."""
    return redirect("web-login")


def employee_register(request):
    if request.user.is_authenticated:
        return redirect("web-home")
    form = EmployeeRegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Account created. You are logged in as an employee.")
        return redirect("web-employee-dashboard")
    return render(
        request,
        "web/register.html",
        {"form": form, "title": "Register as employee", "login_url": "web-login"},
    )


def manager_register(request):
    """Only ONE manager can ever self-register; after that this page is closed."""
    if request.user.is_authenticated:
        return redirect("web-home")
    if manager_exists():
        messages.error(request, "A manager is already registered. Manager sign-up is closed.")
        return redirect("web-login")

    form = ManagerRegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            if manager_exists():  # re-check right before saving
                messages.error(request, "A manager is already registered. Manager sign-up is closed.")
                return redirect("web-login")
            user = form.save()
        login(request, user)
        messages.success(request, "Manager account created. You are logged in as the manager.")
        return redirect("web-manager-dashboard")
    return render(
        request,
        "web/register.html",
        {"form": form, "title": "Register as manager", "login_url": "web-login"},
    )


def logout_view(request):
    logout(request)
    return redirect("web-home")


def role_required(allowed_roles, login_name):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated or request.user.role not in allowed_roles:
                return redirect(login_name)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


employee_required = role_required((Role.EMPLOYEE,), "web-login")
manager_required = role_required((Role.MANAGER, Role.ADMIN), "web-login")
any_role_required = role_required((Role.EMPLOYEE, Role.MANAGER, Role.ADMIN), "web-login")


def _apply_filters(request, queryset, *, by_employee, prefix=""):
    """
    ?status= &leave_type= &employee= &ordering= &page=  (invalid values are ignored).

    `prefix` lets two tables share one page without clashing: the "own leave"
    table on the manager page reads own_status, own_page, ... while the other
    table keeps the plain names.
    """
    get = request.GET
    status = get.get(f"{prefix}status", "")
    leave_type = get.get(f"{prefix}leave_type", "")
    employee = get.get(f"{prefix}employee", "")
    ordering = get.get(f"{prefix}ordering", "-created_at")

    if status in Leave.Status.values:
        queryset = queryset.filter(status=status)
    else:
        status = ""
    if leave_type in Leave.LeaveType.values:
        queryset = queryset.filter(leave_type=leave_type)
    else:
        leave_type = ""
    if by_employee and employee.isdigit():
        queryset = queryset.filter(employee_id=int(employee))
    else:
        employee = ""
    if ordering not in dict(ORDERINGS):
        ordering = "-created_at"

    queryset = queryset.order_by(ordering, "-id")
    page = Paginator(queryset, PAGE_SIZE).get_page(get.get(f"{prefix}page"))

    own_keys = {f"{prefix}{name}" for name in ("status", "leave_type", "employee", "ordering", "page")}
    if prefix:
        # a prefixed table owns only the keys starting with its prefix
        mine = lambda key: key.startswith(prefix)
    else:
        # the plain table owns the plain keys (anything not belonging to a prefixed table)
        mine = lambda key: key in own_keys
    # Parameters of the OTHER table: kept as hidden inputs / in links so that
    # filtering or paging one table does not reset the other one.
    other_items = [(k, v) for k, v in get.items() if not mine(k)]
    keep = get.copy()
    keep.pop(f"{prefix}page", None)
    return page, {
        "prefix": prefix,
        "status": status,
        "leave_type": leave_type,
        "employee": employee,
        "ordering": ordering,
        "querystring": keep.urlencode(),
        "other_params": other_items,
        "reset_query": urlencode(other_items),
    }


def _filter_context(request, queryset, *, by_employee, prefix=""):
    page, filters = _apply_filters(
        request, queryset, by_employee=by_employee, prefix=prefix
    )
    return {
        "page": page,
        "f": filters,
        "statuses": Leave.Status.choices,
        "leave_types": Leave.LeaveType.choices,
        "orderings": ORDERINGS,
        "next": request.get_full_path(),
    }


def _mark_buttons(page, user):
    """
    Decide, per leave, which buttons are enabled. The rules live in
    leaves.services; the template only shows the result.
      is_mine       -> row belongs to the logged-in user (shows the Delete button)
      can_delete    -> Delete enabled: own leave and still PENDING
      has_review    -> user is allowed to review this row (shows Approve/Reject)
      can_review    -> Approve/Reject enabled: allowed AND still PENDING
    """
    page.object_list = list(page.object_list)  # evaluate once; keep the flags below
    for leave in page.object_list:
        leave.is_mine = leave.employee_id == user.id
        leave.can_delete = services.can_modify_leave(leave, user)
        leave.has_review = services.has_review_rights(leave, user)
        leave.can_review = services.can_review_leave(leave, user)


def _submit_leave_form(request, success_text):
    """
    Handle the 'Request leave' form. Returns True when the leave was created.
    All validation and rules are in LeaveSerializer / leaves.services.
    """
    serializer = LeaveSerializer(data=request.POST, context={"request": request})
    try:
        if serializer.is_valid():
            serializer.save()
            messages.success(request, success_text)
            return True
        for field, errors in serializer.errors.items():
            for error in errors:
                label = "" if field == "non_field_errors" else f"{field.replace('_', ' ')}: "
                messages.error(request, f"{label}{error}")
    except APIException as exc:  # e.g. a role that may not create leave
        messages.error(request, _error_text(exc))
    return False


@employee_required
def employee_dashboard(request):
    form_values = {}
    if request.method == "POST":
        form_values = request.POST
        if _submit_leave_form(
            request, "Leave request submitted. Waiting for manager approval."
        ):
            return redirect("web-employee-dashboard")

    own = selectors.own_leaves(request.user)
    context = _filter_context(request, own, by_employee=False)
    _mark_buttons(context["page"], request.user)
    context.update({"form_leave_types": Leave.LeaveType.choices, "values": form_values})
    return render(request, "web/employee_dashboard.html", context)


@manager_required
def manager_dashboard(request):
    # Managers can apply for leave too (admins cannot); a manager's own
    # request is approved by an admin only.
    can_request = services.can_create_leave(request.user)
    form_values = {}
    if request.method == "POST":
        form_values = request.POST
        if _submit_leave_form(
            request, "Leave request submitted. Waiting for admin approval."
        ):
            return redirect("web-manager-dashboard")

    owners = selectors.visible_leave_owners(request.user)
    if not request.user.is_admin:
        owners = owners.exclude(pk=request.user.pk)  # "Employee leave" filter: other people only
    if request.user.is_admin:
        # An admin has no leave of their own: one table with everything.
        context = _filter_context(
            request, selectors.visible_leaves(request.user), by_employee=True
        )
        _mark_buttons(context["page"], request.user)
        context["sections"] = [
            {
                "title": "All leave requests (employees and managers)",
                "page": context["page"],
                "f": context["f"],
                "show_employee": True,
                "empty": "No leave requests found.",
            }
        ]
    else:
        # A manager sees two separate tables: their own leave, and the leave of employees.
        context = _filter_context(
            request, selectors.other_leaves(request.user), by_employee=True
        )
        own = _filter_context(
            request, selectors.own_leaves(request.user), by_employee=False, prefix="own_"
        )
        _mark_buttons(context["page"], request.user)
        _mark_buttons(own["page"], request.user)
        context.update({"own_page": own["page"], "own_f": own["f"]})
        context["sections"] = [
            {
                "title": "Own leave",
                "hint": "Your own requests. An admin approves or rejects them.",
                "page": own["page"],
                "f": own["f"],
                "show_employee": False,
                "empty": "You have not requested any leave.",
            },
            {
                "title": "Employee leave",
                "page": context["page"],
                "f": context["f"],
                "show_employee": True,
                "empty": "No employee leave requests found.",
            },
        ]

    context.update(
        {
            "employees": owners,
            "can_request": can_request,
            "form_leave_types": Leave.LeaveType.choices,
            "values": form_values,
        }
    )
    return render(request, "web/manager_dashboard.html", context)


def _redirect_back(request, default):
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect(default)


def _review(request, leave_id, service_function, done_text):
    try:
        service_function(leave_id=leave_id, reviewer=request.user)
        messages.success(request, done_text)
    except APIException as exc:
        messages.error(request, _error_text(exc))
    return _redirect_back(request, "web-manager-dashboard")


@manager_required
@require_POST
def approve(request, leave_id):
    return _review(request, leave_id, services.approve_leave, "Leave approved.")


@manager_required
@require_POST
def reject(request, leave_id):
    return _review(request, leave_id, services.reject_leave, "Leave rejected.")


@any_role_required
@require_POST
def delete(request, leave_id):
    """Delete your own leave. The service refuses it once the leave is decided."""
    try:
        services.delete_pending_leave(leave_id=leave_id, actor=request.user)
        messages.success(request, "Leave request deleted.")
    except APIException as exc:
        messages.error(request, _error_text(exc))
    return _redirect_back(request, home_for(request.user))
