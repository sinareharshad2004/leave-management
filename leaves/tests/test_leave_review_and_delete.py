import pytest

from leaves.models import Leave

pytestmark = pytest.mark.django_db

URL = "/api/leaves/"


# ---------------------------------------------------------------- approve / reject
def test_employee_cannot_approve_or_reject(client_for, employee, other_employee, make_leave):
    leave = make_leave(other_employee)
    client = client_for(employee)

    assert client.patch(f"{URL}{leave.id}/approve/").status_code == 403
    assert client.patch(f"{URL}{leave.id}/reject/").status_code == 403

    leave.refresh_from_db()
    assert leave.status == "PENDING"
    assert leave.approved_by is None


def test_manager_can_approve_leave(client_for, manager, employee, make_leave):
    leave = make_leave(employee)

    response = client_for(manager).patch(f"{URL}{leave.id}/approve/")

    assert response.status_code == 200
    assert response.data["status"] == "APPROVED"
    assert response.data["approved_by"] == manager.id
    assert response.data["approved_by_name"] == manager.name
    leave.refresh_from_db()
    assert leave.status == "APPROVED"
    assert leave.approved_by == manager


def test_manager_can_reject_leave(client_for, manager, employee, make_leave):
    leave = make_leave(employee)

    response = client_for(manager).patch(f"{URL}{leave.id}/reject/")

    assert response.status_code == 200
    assert response.data["status"] == "REJECTED"
    leave.refresh_from_db()
    assert leave.status == "REJECTED"
    assert leave.approved_by == manager


def test_admin_can_approve_leave(client_for, admin_user, employee, make_leave):
    leave = make_leave(employee)
    assert client_for(admin_user).patch(f"{URL}{leave.id}/approve/").status_code == 200


def test_manager_cannot_approve_own_leave(client_for, manager, make_leave):
    own_leave = make_leave(manager)

    response = client_for(manager).patch(f"{URL}{own_leave.id}/approve/")

    assert response.status_code == 403
    own_leave.refresh_from_db()
    assert own_leave.status == "PENDING"
    assert own_leave.approved_by is None


def test_manager_cannot_reject_own_leave(client_for, manager, make_leave):
    own_leave = make_leave(manager)
    assert client_for(manager).patch(f"{URL}{own_leave.id}/reject/").status_code == 403


def test_manager_can_approve_another_managers_leave(client_for, manager, other_manager, make_leave):
    leave = make_leave(other_manager)
    assert client_for(manager).patch(f"{URL}{leave.id}/approve/").status_code == 200


def test_approved_leave_cannot_be_modified_again(client_for, manager, other_manager, employee, make_leave):
    leave = make_leave(employee, status="APPROVED", approved_by=manager)
    client = client_for(other_manager)

    assert client.patch(f"{URL}{leave.id}/approve/").status_code == 409
    assert client.patch(f"{URL}{leave.id}/reject/").status_code == 409

    leave.refresh_from_db()
    assert leave.status == "APPROVED"
    assert leave.approved_by == manager  # unchanged


def test_rejected_leave_cannot_be_modified_again(client_for, manager, other_manager, employee, make_leave):
    leave = make_leave(employee, status="REJECTED", approved_by=manager)
    client = client_for(other_manager)

    assert client.patch(f"{URL}{leave.id}/approve/").status_code == 409
    assert client.patch(f"{URL}{leave.id}/reject/").status_code == 409

    leave.refresh_from_db()
    assert leave.status == "REJECTED"


def test_second_manager_cannot_approve_the_same_leave_again(
    client_for, manager, other_manager, employee, make_leave
):
    """
    Two managers approving the same leave: whoever gets the row lock second
    sees a non-PENDING status and is refused. Here the two calls run one after
    the other, which is exactly what the second request sees after the lock.
    """
    leave = make_leave(employee)

    first = client_for(manager).patch(f"{URL}{leave.id}/approve/")
    second = client_for(other_manager).patch(f"{URL}{leave.id}/approve/")

    assert first.status_code == 200
    assert second.status_code == 409
    leave.refresh_from_db()
    assert leave.approved_by == manager


def test_approve_unknown_leave_returns_404(client_for, manager):
    assert client_for(manager).patch(f"{URL}9999/approve/").status_code == 404


def test_pending_list_for_manager(client_for, manager, employee, other_employee, make_leave):
    pending = make_leave(employee, start=1)
    make_leave(other_employee, start=1, status="APPROVED")
    make_leave(manager, start=1)  # own pending leave is hidden from the inbox

    response = client_for(manager).get(f"{URL}pending/")

    assert response.status_code == 200
    assert [item["id"] for item in response.data["results"]] == [pending.id]


def test_pending_list_forbidden_for_employee(client_for, employee):
    assert client_for(employee).get(f"{URL}pending/").status_code == 403


# ------------------------------------------------------------------------- delete
def test_employee_can_delete_own_pending_leave(client_for, employee, make_leave):
    leave = make_leave(employee)

    response = client_for(employee).delete(f"{URL}{leave.id}/")

    assert response.status_code == 204
    assert not Leave.objects.filter(pk=leave.pk).exists()


@pytest.mark.parametrize("status", ["APPROVED", "REJECTED"])
def test_employee_cannot_delete_reviewed_leave(client_for, employee, manager, make_leave, status):
    leave = make_leave(employee, status=status, approved_by=manager)

    response = client_for(employee).delete(f"{URL}{leave.id}/")

    assert response.status_code == 409
    assert Leave.objects.filter(pk=leave.pk).exists()


def test_employee_cannot_delete_someone_elses_leave(client_for, employee, other_employee, make_leave):
    leave = make_leave(other_employee)

    response = client_for(employee).delete(f"{URL}{leave.id}/")

    assert response.status_code == 404
    assert Leave.objects.filter(pk=leave.pk).exists()


def test_manager_cannot_delete_someone_elses_leave(client_for, manager, employee, make_leave):
    leave = make_leave(employee)

    response = client_for(manager).delete(f"{URL}{leave.id}/")

    assert response.status_code == 403
    assert Leave.objects.filter(pk=leave.pk).exists()


def test_admin_can_delete_any_pending_leave(client_for, admin_user, employee, make_leave):
    leave = make_leave(employee)
    assert client_for(admin_user).delete(f"{URL}{leave.id}/").status_code == 204
