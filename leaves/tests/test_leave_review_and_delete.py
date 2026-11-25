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


def test_manager_cannot_approve_another_managers_leave(client_for, manager, other_manager, make_leave):
    """A manager's leave is reviewed by an admin only. Via the API it is not even visible."""
    leave = make_leave(other_manager)
    client = client_for(manager)

    assert client.patch(f"{URL}{leave.id}/approve/").status_code == 404
    assert client.patch(f"{URL}{leave.id}/reject/").status_code == 404

    leave.refresh_from_db()
    assert leave.status == "PENDING"
    assert leave.approved_by is None


def test_service_refuses_manager_reviewing_a_manager_leave(manager, other_manager, make_leave):
    """The web pages call the service directly, so the rule must hold there too."""
    from rest_framework.exceptions import PermissionDenied

    from leaves import services

    leave = make_leave(other_manager)

    with pytest.raises(PermissionDenied):
        services.approve_leave(leave_id=leave.id, reviewer=manager)
    with pytest.raises(PermissionDenied):
        services.reject_leave(leave_id=leave.id, reviewer=manager)

    leave.refresh_from_db()
    assert leave.status == "PENDING"


def test_admin_can_approve_a_managers_leave(client_for, admin_user, manager, make_leave):
    leave = make_leave(manager)

    response = client_for(admin_user).patch(f"{URL}{leave.id}/approve/")

    assert response.status_code == 200
    assert response.data["status"] == "APPROVED"
    leave.refresh_from_db()
    assert leave.status == "APPROVED"
    assert leave.approved_by == admin_user


def test_admin_can_reject_a_managers_leave(client_for, admin_user, manager, make_leave):
    leave = make_leave(manager)
    assert client_for(admin_user).patch(f"{URL}{leave.id}/reject/").status_code == 200
    leave.refresh_from_db()
    assert leave.status == "REJECTED"


def test_employee_cannot_approve_a_managers_leave(client_for, employee, manager, make_leave):
    leave = make_leave(manager)
    assert client_for(employee).patch(f"{URL}{leave.id}/approve/").status_code == 403
    leave.refresh_from_db()
    assert leave.status == "PENDING"


def test_decided_managers_leave_cannot_be_reviewed_again(client_for, admin_user, manager, make_leave):
    leave = make_leave(manager, status="APPROVED", approved_by=admin_user)
    client = client_for(admin_user)
    assert client.patch(f"{URL}{leave.id}/approve/").status_code == 409
    assert client.patch(f"{URL}{leave.id}/reject/").status_code == 409


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


def test_pending_list_for_manager(client_for, manager, other_manager, employee, other_employee, make_leave):
    pending = make_leave(employee, start=1)
    make_leave(other_employee, start=1, status="APPROVED")
    make_leave(manager, start=1)  # own pending leave is hidden from the inbox
    make_leave(other_manager, start=1)  # another manager's leave is for admins only

    response = client_for(manager).get(f"{URL}pending/")

    assert response.status_code == 200
    assert [item["id"] for item in response.data["results"]] == [pending.id]


def test_pending_list_for_admin_includes_managers_leaves(
    client_for, admin_user, manager, employee, make_leave
):
    employee_leave = make_leave(employee, start=1)
    manager_leave = make_leave(manager, start=1)

    response = client_for(admin_user).get(f"{URL}pending/")

    assert {item["id"] for item in response.data["results"]} == {employee_leave.id, manager_leave.id}


def test_pending_list_forbidden_for_employee(client_for, employee):
    assert client_for(employee).get(f"{URL}pending/").status_code == 403


# ------------------------------------------------------------------------- delete
def test_employee_can_delete_own_pending_leave(client_for, employee, make_leave):
    leave = make_leave(employee)

    response = client_for(employee).delete(f"{URL}{leave.id}/")

    assert response.status_code == 204
    # soft delete: the row is NOT removed, it is marked as deleted by the owner
    leave.refresh_from_db()
    assert leave.status == "DELETED"
    assert leave.deleted_by == employee
    assert leave.deleted_at is not None


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


def test_admin_cannot_delete_someone_elses_leave(client_for, admin_user, employee, make_leave):
    leave = make_leave(employee)

    response = client_for(admin_user).delete(f"{URL}{leave.id}/")

    assert response.status_code == 403
    assert Leave.objects.filter(pk=leave.pk).exists()


def test_manager_can_delete_own_pending_leave(client_for, manager, make_leave):
    leave = make_leave(manager)

    response = client_for(manager).delete(f"{URL}{leave.id}/")

    assert response.status_code == 204
    leave.refresh_from_db()
    assert leave.status == "DELETED"
    assert leave.deleted_by == manager


@pytest.mark.parametrize("status", ["APPROVED", "REJECTED"])
def test_manager_cannot_delete_own_decided_leave(client_for, manager, admin_user, make_leave, status):
    leave = make_leave(manager, status=status, approved_by=admin_user)

    response = client_for(manager).delete(f"{URL}{leave.id}/")

    assert response.status_code == 409
    assert Leave.objects.filter(pk=leave.pk).exists()


def test_manager_cannot_delete_another_managers_leave(client_for, manager, other_manager, make_leave):
    leave = make_leave(other_manager)
    assert client_for(manager).delete(f"{URL}{leave.id}/").status_code == 404
    assert Leave.objects.filter(pk=leave.pk).exists()
