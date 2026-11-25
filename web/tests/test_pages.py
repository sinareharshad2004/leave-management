import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


def _login(url, user, password):
    client = Client()
    response = client.post(url, {"username": user.email, "password": password})
    return client, response


def test_employee_logs_in_on_single_page_and_lands_on_employee_page(employee, password):
    client, response = _login("/login/", employee, password)
    assert response.status_code == 302 and response.url == "/employee/"
    assert client.get("/employee/").status_code == 200


def test_manager_logs_in_on_same_page_and_lands_on_manager_page(manager, password):
    client, response = _login("/login/", manager, password)
    assert response.status_code == 302 and response.url == "/manager/"
    assert client.get("/manager/").status_code == 200


def test_admin_lands_on_manager_page(admin_user, password):
    client, response = _login("/login/", admin_user, password)
    assert response.url == "/manager/"


def test_wrong_password_shows_error_on_login_page(employee):
    response = Client().post("/login/", {"username": employee.email, "password": "nope"})
    assert response.status_code == 200
    assert b"correct" in response.content


def test_old_login_addresses_forward_to_single_login():
    for old in ("/employee/login/", "/manager/login/"):
        response = Client().get(old)
        assert response.status_code == 302 and response.url == "/login/"


def test_employee_cannot_open_manager_pages(employee, make_leave, password):
    leave = make_leave(employee)
    client, _ = _login("/login/", employee, password)
    assert client.get("/manager/").status_code == 302
    assert client.post(f"/manager/leaves/{leave.id}/approve/").status_code == 302
    leave.refresh_from_db()
    assert leave.status == "PENDING"


def test_employee_creates_manager_approves(employee, manager, password, day):
    emp, _ = _login("/login/", employee, password)
    response = emp.post(
        "/employee/",
        {"leave_type": "SICK", "start_date": str(day(3)), "end_date": str(day(4)), "reason": "Fever"},
    )
    assert response.status_code == 302
    from leaves.models import Leave

    leave = Leave.objects.get(employee=employee)
    mgr, _ = _login("/login/", manager, password)
    assert mgr.post(f"/manager/leaves/{leave.id}/approve/").status_code == 302
    leave.refresh_from_db()
    assert leave.status == "APPROVED" and leave.approved_by == manager


def test_home_redirects_to_login_and_login_page_has_register_links():
    response = Client().get("/")
    assert response.status_code == 302 and response.url == "/login/"
    page = Client().get("/login/").content
    assert b"Register as employee" in page
    assert b"Register as manager" in page  # shown while no manager exists


def test_employee_can_register_and_is_logged_in():
    client = Client()
    response = client.post(
        "/employee/register/",
        {"name": "Asha", "email": "Asha@Example.com", "password1": "StrongPass123!", "password2": "StrongPass123!"},
    )
    assert response.status_code == 302
    from users.models import User

    user = User.objects.get(email="asha@example.com")
    assert user.role == "EMPLOYEE"
    assert client.get("/employee/").status_code == 200


def test_register_rejects_duplicate_email_and_mismatched_password(employee):
    client = Client()
    response = client.post(
        "/employee/register/",
        {"name": "Dup", "email": employee.email, "password1": "StrongPass123!", "password2": "Different123!"},
    )
    assert response.status_code == 200
    assert b"already exists" in response.content
    assert b"do not match" in response.content


def test_manager_register_link_hidden_once_a_manager_exists(manager):
    page = Client().get("/login/").content
    assert b"Register as employee" in page
    assert b"Register as manager" not in page


def test_registered_employee_can_log_out_and_log_in_again():
    client = Client()
    client.post(
        "/employee/register/",
        {"name": "Asha", "email": "asha@example.com", "password1": "StrongPass123!", "password2": "StrongPass123!"},
    )
    client.get("/logout/")
    assert client.get("/employee/").status_code == 302  # logged out

    for email in ("asha@example.com", "ASHA@Example.com"):
        fresh = Client()
        response = fresh.post("/login/", {"username": email, "password": "StrongPass123!"})
        assert response.status_code == 302, email
        assert fresh.get("/employee/").status_code == 200


def test_registered_employee_can_log_in_through_api_too():
    from rest_framework.test import APIClient

    Client().post(
        "/employee/register/",
        {"name": "Ravi", "email": "ravi@example.com", "password1": "StrongPass123!", "password2": "StrongPass123!"},
    )
    response = APIClient().post(
        "/api/auth/employee/login/",
        {"email": "Ravi@Example.com", "password": "StrongPass123!"},
        format="json",
    )
    assert response.status_code == 200


def test_manager_page_filters_orders_and_paginates(employee, other_employee, manager, make_leave, password):
    for i in range(12):
        make_leave(employee, start=1 + i * 3, leave_type="SICK" if i % 2 else "CASUAL")
    make_leave(other_employee, start=1, status="APPROVED", approved_by=manager)
    client, _ = _login("/login/", manager, password)

    page1 = client.get("/manager/").context["page"]
    assert page1.paginator.count == 13 and len(page1.object_list) == 10
    assert len(client.get("/manager/?page=2").context["page"].object_list) == 3

    only_approved = client.get("/manager/?status=APPROVED").context["page"]
    assert [l.employee_id for l in only_approved.object_list] == [other_employee.id]

    only_sick = client.get("/manager/?leave_type=SICK").context["page"]
    assert only_sick.paginator.count == 6

    mine = client.get(f"/manager/?employee={other_employee.id}").context["page"]
    assert mine.paginator.count == 1

    oldest = client.get("/manager/?ordering=created_at").context["page"].object_list
    assert oldest[0].created_at <= oldest[len(oldest) - 1].created_at

    junk = client.get("/manager/?status=NOPE&ordering=;drop&employee=abc")
    assert junk.status_code == 200


def test_employee_filter_only_sees_own_leaves(employee, other_employee, make_leave, password):
    make_leave(employee, start=1, status="APPROVED")
    make_leave(employee, start=10)
    make_leave(other_employee, start=1)
    client, _ = _login("/login/", employee, password)
    page = client.get(f"/employee/?employee={other_employee.id}").context["page"]
    assert page.paginator.count == 2  # employee filter is ignored for employees
    assert client.get("/employee/?status=APPROVED").context["page"].paginator.count == 1


def test_seed_demo_creates_many_employees_and_is_repeatable():
    from django.core.management import call_command
    from leaves.models import Leave
    from users.models import User

    call_command("seed_demo")
    employees = User.objects.filter(role="EMPLOYEE").count()
    leaves = Leave.objects.count()
    assert employees >= 5 and leaves > 0
    call_command("seed_demo")
    assert Leave.objects.count() == leaves


def _register(client, url, email, name="Test"):
    return client.post(
        url,
        {"name": name, "email": email, "password1": "StrongPass123!", "password2": "StrongPass123!"},
    )


def test_many_employees_can_register():
    from users.models import User

    for i in range(4):
        assert _register(Client(), "/employee/register/", f"emp{i}@example.com").status_code == 302
    assert User.objects.filter(role="EMPLOYEE").count() == 4


def test_first_manager_can_register_and_reach_manager_page():
    from users.models import User

    client = Client()
    assert b"Register as manager" in client.get("/login/").content
    assert _register(client, "/manager/register/", "boss@example.com", "Boss").status_code == 302
    assert User.objects.get(email="boss@example.com").role == "MANAGER"
    assert client.get("/manager/").status_code == 200


def test_second_manager_cannot_register(manager):
    from users.models import User

    client = Client()
    assert b"Register as manager" not in client.get("/login/").content
    response = _register(client, "/manager/register/", "second@example.com")
    assert response.status_code == 302  # bounced to the manager login
    assert not User.objects.filter(email="second@example.com").exists()
    assert User.objects.filter(role="MANAGER").count() == 1


def test_manager_registration_never_makes_an_employee_a_manager(employee):
    from users.models import User

    _register(Client(), "/employee/register/", "new@example.com")
    assert User.objects.get(email="new@example.com").role == "EMPLOYEE"


# ------------------------------------------------ leave buttons and role rules
def _page_leaves(client, url, key="page"):
    return {leave.id: leave for leave in client.get(url).context[key].object_list}


def test_delete_button_is_enabled_only_while_leave_is_pending(employee, manager, make_leave, password):
    pending = make_leave(employee, start=1)
    approved = make_leave(employee, start=5, status="APPROVED", approved_by=manager)
    rejected = make_leave(employee, start=9, status="REJECTED", approved_by=manager)
    client, _ = _login("/login/", employee, password)

    response = client.get("/employee/")
    html = response.content.decode()
    leaves = {leave.id: leave for leave in response.context["page"].object_list}

    assert leaves[pending.id].can_delete is True
    assert leaves[approved.id].can_delete is False
    assert leaves[rejected.id].can_delete is False
    assert f'id="delete-{pending.id}">' in html  # enabled
    assert f'id="delete-{approved.id}" disabled' in html
    assert f'id="delete-{rejected.id}" disabled' in html


def test_button_becomes_disabled_after_manager_decides(employee, manager, make_leave, password):
    leave = make_leave(employee)
    emp, _ = _login("/login/", employee, password)
    assert f'id="delete-{leave.id}">' in emp.get("/employee/").content.decode()

    mgr, _ = _login("/login/", manager, password)
    mgr.post(f"/manager/leaves/{leave.id}/reject/")

    assert f'id="delete-{leave.id}" disabled' in emp.get("/employee/").content.decode()


def test_employee_can_delete_own_pending_leave_from_the_page(employee, make_leave, password):
    from leaves.models import Leave

    leave = make_leave(employee)
    client, _ = _login("/login/", employee, password)

    response = client.post(f"/leaves/{leave.id}/delete/")

    assert response.status_code == 302
    leave.refresh_from_db()  # soft delete: still in the database
    assert leave.status == "DELETED" and leave.deleted_by == employee


@pytest.mark.parametrize("status", ["APPROVED", "REJECTED"])
def test_decided_leave_cannot_be_deleted_even_by_posting_directly(
    employee, manager, make_leave, password, status
):
    """The button is only a convenience: the server refuses it as well."""
    from leaves.models import Leave

    leave = make_leave(employee, status=status, approved_by=manager)
    client, _ = _login("/login/", employee, password)

    response = client.post(f"/leaves/{leave.id}/delete/")

    assert response.status_code == 302
    assert Leave.objects.filter(pk=leave.pk, status=status).exists()


def test_cannot_delete_another_users_leave_from_the_page(employee, other_employee, make_leave, password):
    from leaves.models import Leave

    leave = make_leave(other_employee)
    client, _ = _login("/login/", employee, password)

    client.post(f"/leaves/{leave.id}/delete/")

    assert Leave.objects.filter(pk=leave.pk).exists()  # refused by the service


def test_manager_cannot_delete_an_employees_leave_from_the_page(employee, manager, make_leave, password):
    from leaves.models import Leave

    leave = make_leave(employee)
    client, _ = _login("/login/", manager, password)

    client.post(f"/leaves/{leave.id}/delete/")

    assert Leave.objects.filter(pk=leave.pk).exists()


def test_delete_page_needs_login_and_post(employee, make_leave):
    from leaves.models import Leave

    leave = make_leave(employee)
    assert Client().post(f"/leaves/{leave.id}/delete/").status_code == 302  # to login
    assert Leave.objects.filter(pk=leave.pk).exists()


def test_manager_can_request_own_leave_from_manager_page(manager, password, day):
    from leaves.models import Leave

    client, _ = _login("/login/", manager, password)
    response = client.post(
        "/manager/",
        {"leave_type": "PAID", "start_date": str(day(3)), "end_date": str(day(4)), "reason": "Trip"},
    )

    assert response.status_code == 302
    leave = Leave.objects.get(employee=manager)
    assert leave.status == "PENDING" and leave.approved_by is None


def test_admin_cannot_request_leave(admin_user, password, day):
    from leaves.models import Leave

    client, _ = _login("/login/", admin_user, password)
    assert client.get("/manager/").context["can_request"] is False
    client.post(
        "/manager/",
        {"leave_type": "PAID", "start_date": str(day(3)), "end_date": str(day(4)), "reason": "Trip"},
    )
    assert not Leave.objects.filter(employee=admin_user).exists()


def test_manager_page_shows_own_leave_with_delete_and_no_review_buttons(manager, make_leave, password):
    own = make_leave(manager)
    client, _ = _login("/login/", manager, password)

    response = client.get("/manager/")
    html = response.content.decode()
    leave = _page_leaves(client, "/manager/", "own_page")[own.id]

    assert leave.is_mine and leave.can_delete and not leave.has_review
    assert f'id="delete-{own.id}">' in html
    assert f'id="approve-{own.id}"' not in html  # cannot approve own leave


def test_manager_page_hides_other_managers_leaves_but_admin_sees_them(
    manager, other_manager, admin_user, make_leave, password
):
    theirs = make_leave(other_manager)
    mgr, _ = _login("/login/", manager, password)
    adm, _ = _login("/login/", admin_user, password)

    assert theirs.id not in _page_leaves(mgr, "/manager/")
    assert theirs.id in _page_leaves(adm, "/manager/")


def test_manager_cannot_approve_another_managers_leave_from_the_page(
    manager, other_manager, make_leave, password
):
    leave = make_leave(other_manager)
    client, _ = _login("/login/", manager, password)

    client.post(f"/manager/leaves/{leave.id}/approve/")

    leave.refresh_from_db()
    assert leave.status == "PENDING" and leave.approved_by is None


def test_admin_approves_a_managers_leave_from_the_page(manager, admin_user, make_leave, password):
    leave = make_leave(manager)
    client, _ = _login("/login/", admin_user, password)

    client.post(f"/manager/leaves/{leave.id}/approve/")

    leave.refresh_from_db()
    assert leave.status == "APPROVED" and leave.approved_by == admin_user


def test_approve_and_reject_buttons_are_disabled_once_decided(employee, manager, make_leave, password):
    pending = make_leave(employee, start=1)
    decided = make_leave(employee, start=5, status="APPROVED", approved_by=manager)
    client, _ = _login("/login/", manager, password)

    html = client.get("/manager/").content.decode()

    assert f'id="approve-{pending.id}">' in html
    assert f'id="approve-{decided.id}" disabled' in html
    assert f'id="reject-{decided.id}" disabled' in html


def test_decided_leave_cannot_be_reviewed_again_from_the_page(employee, manager, admin_user, make_leave, password):
    leave = make_leave(employee, status="APPROVED", approved_by=manager)
    client, _ = _login("/login/", admin_user, password)

    client.post(f"/manager/leaves/{leave.id}/reject/")

    leave.refresh_from_db()
    assert leave.status == "APPROVED" and leave.approved_by == manager


# --------------------------------------- soft delete and the two manager tables
def test_deleted_leave_stays_visible_on_employee_page_with_who_deleted_it(employee, make_leave, password):
    leave = make_leave(employee)
    client, _ = _login("/login/", employee, password)
    client.post(f"/leaves/{leave.id}/delete/")

    response = client.get("/employee/")
    html = response.content.decode()

    assert leave.id in {l.id for l in response.context["page"].object_list}
    assert "Deleted" in html
    assert f"Deleted by {employee.name}" in html
    assert f'id="delete-{leave.id}" disabled' in html  # button is disabled


def test_manager_sees_two_tables_own_leave_and_employee_leave(manager, employee, make_leave, password):
    own = make_leave(manager, start=1)
    theirs = make_leave(employee, start=1)
    client, _ = _login("/login/", manager, password)

    response = client.get("/manager/")
    html = response.content.decode()

    assert "Own leave" in html and "Employee leave" in html
    assert [l.id for l in response.context["own_page"].object_list] == [own.id]
    assert [l.id for l in response.context["page"].object_list] == [theirs.id]
    assert [s["title"] for s in response.context["sections"]] == ["Own leave", "Employee leave"]


def test_own_leave_table_never_contains_other_peoples_leaves(manager, employee, other_manager, make_leave, password):
    make_leave(employee)
    make_leave(other_manager)
    client, _ = _login("/login/", manager, password)
    assert client.get("/manager/").context["own_page"].paginator.count == 0


def test_employee_leave_table_never_contains_own_leaves(manager, make_leave, password):
    make_leave(manager)
    client, _ = _login("/login/", manager, password)
    assert client.get("/manager/").context["page"].paginator.count == 0


def test_the_two_tables_filter_independently(manager, employee, make_leave, password):
    make_leave(manager, start=1, status="PENDING")
    make_leave(manager, start=5, status="DELETED")
    make_leave(employee, start=1, status="PENDING")
    make_leave(employee, start=5, status="APPROVED", approved_by=manager)
    client, _ = _login("/login/", manager, password)

    # filtering the own-leave table does not touch the employee-leave table
    response = client.get("/manager/?own_status=DELETED")
    assert response.context["own_page"].paginator.count == 1
    assert response.context["page"].paginator.count == 2

    # and the other way round
    response = client.get("/manager/?status=APPROVED")
    assert response.context["page"].paginator.count == 1
    assert response.context["own_page"].paginator.count == 2

    # both at once
    response = client.get("/manager/?status=APPROVED&own_status=PENDING")
    assert response.context["page"].paginator.count == 1
    assert response.context["own_page"].paginator.count == 1


def test_each_table_has_its_own_pagination(manager, employee, make_leave, password):
    for i in range(12):
        make_leave(manager, start=1 + i * 3)
    for i in range(3):
        make_leave(employee, start=1 + i * 3)
    client, _ = _login("/login/", manager, password)

    first = client.get("/manager/")
    assert len(first.context["own_page"].object_list) == 10
    second = client.get("/manager/?own_page=2")
    assert len(second.context["own_page"].object_list) == 2
    assert len(second.context["page"].object_list) == 3  # other table unaffected


def test_filter_form_keeps_the_other_tables_settings(manager, employee, make_leave, password):
    make_leave(employee)
    client, _ = _login("/login/", manager, password)

    html = client.get("/manager/?status=PENDING").content.decode()

    # the own-leave form carries the employee table's filter as a hidden field
    assert '<input type="hidden" name="status" value="PENDING">' in html


def test_deleted_employee_leave_is_shown_to_manager_but_cannot_be_reviewed(
    employee, manager, make_leave, password
):
    leave = make_leave(employee)
    emp, _ = _login("/login/", employee, password)
    emp.post(f"/leaves/{leave.id}/delete/")
    mgr, _ = _login("/login/", manager, password)

    response = mgr.get("/manager/")
    html = response.content.decode()

    assert leave.id in {l.id for l in response.context["page"].object_list}
    assert f"Deleted by {employee.name}" in html
    assert f'id="approve-{leave.id}" disabled' in html
    assert f'id="reject-{leave.id}" disabled' in html

    mgr.post(f"/manager/leaves/{leave.id}/approve/")
    leave.refresh_from_db()
    assert leave.status == "DELETED" and leave.approved_by is None


def test_admin_page_is_one_table_with_everything(admin_user, manager, employee, make_leave, password):
    make_leave(manager)
    make_leave(employee)
    client, _ = _login("/login/", admin_user, password)

    response = client.get("/manager/")

    assert len(response.context["sections"]) == 1
    assert response.context["page"].paginator.count == 2
