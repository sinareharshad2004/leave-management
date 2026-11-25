"""Deleting your own PENDING leave keeps the row and records who deleted it."""
import pytest

from leaves.models import Leave

pytestmark = pytest.mark.django_db

URL = "/api/leaves/"


def ids(response):
    return {item["id"] for item in response.data["results"]}


def test_delete_keeps_the_row_and_records_who_and_when(client_for, employee, make_leave):
    leave = make_leave(employee)

    assert client_for(employee).delete(f"{URL}{leave.id}/").status_code == 204

    assert Leave.objects.filter(pk=leave.pk).count() == 1  # nothing removed
    leave.refresh_from_db()
    assert leave.status == "DELETED"
    assert leave.deleted_by == employee
    assert leave.deleted_at is not None
    assert leave.approved_by is None


def test_deleted_leave_is_still_listed_with_who_deleted_it(client_for, employee, make_leave):
    leave = make_leave(employee)
    client = client_for(employee)
    client.delete(f"{URL}{leave.id}/")

    response = client.get(URL)
    item = next(i for i in response.data["results"] if i["id"] == leave.id)

    assert item["status"] == "DELETED"
    assert item["deleted_by"] == employee.id
    assert item["deleted_by_name"] == employee.name
    assert item["deleted_at"] is not None
    assert item["can_modify"] is False  # the button is disabled
    assert client.get(f"{URL}{leave.id}/").status_code == 200


def test_manager_deleting_own_leave_is_recorded_too(client_for, manager, make_leave):
    leave = make_leave(manager)
    client_for(manager).delete(f"{URL}{leave.id}/")
    leave.refresh_from_db()
    assert leave.status == "DELETED" and leave.deleted_by == manager


def test_deleted_leave_cannot_be_deleted_again(client_for, employee, make_leave):
    leave = make_leave(employee)
    client = client_for(employee)
    client.delete(f"{URL}{leave.id}/")
    first_deleted_at = Leave.objects.get(pk=leave.pk).deleted_at

    response = client.delete(f"{URL}{leave.id}/")

    assert response.status_code == 409
    assert Leave.objects.get(pk=leave.pk).deleted_at == first_deleted_at


def test_deleted_leave_cannot_be_edited(client_for, employee, make_leave):
    leave = make_leave(employee, status="DELETED")
    response = client_for(employee).patch(f"{URL}{leave.id}/", {"reason": "Again"}, format="json")
    assert response.status_code == 409
    leave.refresh_from_db()
    assert leave.reason == "Test reason" and leave.status == "DELETED"


@pytest.mark.parametrize("who", ["manager", "admin_user"])
def test_deleted_leave_cannot_be_approved_or_rejected(client_for, request, who, employee, make_leave):
    leave = make_leave(employee)
    client_for(employee).delete(f"{URL}{leave.id}/")
    reviewer = client_for(request.getfixturevalue(who))

    assert reviewer.patch(f"{URL}{leave.id}/approve/").status_code == 409
    assert reviewer.patch(f"{URL}{leave.id}/reject/").status_code == 409
    leave.refresh_from_db()
    assert leave.status == "DELETED" and leave.approved_by is None


def test_deleted_leave_is_not_in_the_pending_inbox(client_for, manager, employee, make_leave):
    kept = make_leave(employee, start=1)
    gone = make_leave(employee, start=5)
    client_for(employee).delete(f"{URL}{gone.id}/")

    response = client_for(manager).get(f"{URL}pending/")

    assert ids(response) == {kept.id}


def test_deleted_leave_does_not_block_the_same_dates(client_for, employee, make_leave, day):
    leave = make_leave(employee, start=10, end=12)
    client_for(employee).delete(f"{URL}{leave.id}/")

    response = client_for(employee).post(
        URL,
        {
            "leave_type": "CASUAL",
            "start_date": str(day(10)),
            "end_date": str(day(12)),
            "reason": "Again",
        },
        format="json",
    )

    assert response.status_code == 201


def test_manager_and_admin_can_see_a_deleted_leave(client_for, manager, admin_user, employee, make_leave):
    leave = make_leave(employee)
    client_for(employee).delete(f"{URL}{leave.id}/")

    for viewer in (manager, admin_user):
        item = client_for(viewer).get(f"{URL}{leave.id}/").data
        assert item["status"] == "DELETED"
        assert item["deleted_by_name"] == employee.name


def test_filter_by_status_deleted(client_for, employee, make_leave):
    kept = make_leave(employee, start=1)
    gone = make_leave(employee, start=5)
    client = client_for(employee)
    client.delete(f"{URL}{gone.id}/")

    assert ids(client.get(f"{URL}?status=DELETED")) == {gone.id}
    assert ids(client.get(f"{URL}?status=PENDING")) == {kept.id}


def test_someone_else_cannot_delete_it(client_for, employee, other_employee, make_leave):
    leave = make_leave(employee)
    assert client_for(other_employee).delete(f"{URL}{leave.id}/").status_code == 404
    leave.refresh_from_db()
    assert leave.status == "PENDING" and leave.deleted_by is None
