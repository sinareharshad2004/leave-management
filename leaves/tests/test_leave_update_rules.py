"""Edit rules and the 'button enabled / disabled' flags (can_modify, can_review)."""
import pytest

from leaves.models import Leave

pytestmark = pytest.mark.django_db

URL = "/api/leaves/"


# ---------------------------------------------------------------- editing a leave
def test_owner_can_edit_pending_leave(client_for, employee, make_leave, day):
    leave = make_leave(employee, start=10, end=11)

    response = client_for(employee).patch(
        f"{URL}{leave.id}/",
        {"reason": "New reason", "end_date": str(day(12))},
        format="json",
    )

    assert response.status_code == 200
    leave.refresh_from_db()
    assert leave.reason == "New reason"
    assert leave.end_date == day(12)
    assert leave.status == "PENDING"


def test_manager_can_edit_own_pending_leave(client_for, manager, make_leave):
    leave = make_leave(manager)
    response = client_for(manager).patch(f"{URL}{leave.id}/", {"reason": "Updated"}, format="json")
    assert response.status_code == 200


@pytest.mark.parametrize("status", ["APPROVED", "REJECTED"])
def test_decided_leave_cannot_be_edited(client_for, employee, manager, make_leave, status):
    leave = make_leave(employee, status=status, approved_by=manager)

    response = client_for(employee).patch(f"{URL}{leave.id}/", {"reason": "Changed"}, format="json")

    assert response.status_code == 409
    leave.refresh_from_db()
    assert leave.reason == "Test reason"  # unchanged
    assert leave.status == status


@pytest.mark.parametrize("status", ["APPROVED", "REJECTED"])
def test_decided_managers_leave_cannot_be_edited(client_for, manager, admin_user, make_leave, status):
    leave = make_leave(manager, status=status, approved_by=admin_user)
    response = client_for(manager).patch(f"{URL}{leave.id}/", {"reason": "Changed"}, format="json")
    assert response.status_code == 409


def test_decided_leave_with_invalid_data_still_gets_409_not_400(client_for, employee, manager, make_leave):
    leave = make_leave(employee, status="APPROVED", approved_by=manager)
    response = client_for(employee).patch(
        f"{URL}{leave.id}/", {"start_date": "not-a-date"}, format="json"
    )
    assert response.status_code == 409


def test_cannot_edit_someone_elses_leave(client_for, employee, other_employee, make_leave):
    leave = make_leave(other_employee)

    response = client_for(employee).patch(f"{URL}{leave.id}/", {"reason": "Hacked"}, format="json")

    assert response.status_code == 404
    leave.refresh_from_db()
    assert leave.reason == "Test reason"


@pytest.mark.parametrize("who", ["manager", "admin_user"])
def test_reviewers_cannot_edit_an_employees_leave(client_for, request, who, employee, make_leave):
    leave = make_leave(employee)

    response = client_for(request.getfixturevalue(who)).patch(
        f"{URL}{leave.id}/", {"reason": "Hacked"}, format="json"
    )

    assert response.status_code == 403
    leave.refresh_from_db()
    assert leave.reason == "Test reason"


def test_edit_cannot_change_status_or_owner(client_for, employee, other_employee, make_leave):
    leave = make_leave(employee)

    response = client_for(employee).patch(
        f"{URL}{leave.id}/",
        {"status": "APPROVED", "employee": other_employee.id, "approved_by": employee.id},
        format="json",
    )

    assert response.status_code == 200
    leave.refresh_from_db()
    assert leave.status == "PENDING"
    assert leave.employee == employee
    assert leave.approved_by is None


def test_edit_with_invalid_dates_is_rejected(client_for, employee, make_leave, day):
    leave = make_leave(employee, start=10, end=11)

    response = client_for(employee).patch(
        f"{URL}{leave.id}/", {"end_date": str(day(5))}, format="json"
    )

    assert response.status_code == 400
    assert "end_date" in response.data
    leave.refresh_from_db()
    assert leave.end_date == day(11)


def test_edit_into_the_past_is_rejected(client_for, employee, make_leave, day):
    leave = make_leave(employee, start=10, end=11)
    response = client_for(employee).patch(
        f"{URL}{leave.id}/", {"start_date": str(day(-3)), "end_date": str(day(-2))}, format="json"
    )
    assert response.status_code == 400
    assert "start_date" in response.data


def test_edit_into_an_overlap_is_rejected(client_for, employee, make_leave, day):
    make_leave(employee, start=10, end=12)
    leave = make_leave(employee, start=20, end=21)

    response = client_for(employee).patch(
        f"{URL}{leave.id}/", {"start_date": str(day(11)), "end_date": str(day(13))}, format="json"
    )

    assert response.status_code == 400
    leave.refresh_from_db()
    assert leave.start_date == day(20)


def test_leave_can_be_edited_within_its_own_dates(client_for, employee, make_leave, day):
    """A leave must not count as overlapping with itself."""
    leave = make_leave(employee, start=10, end=12)
    response = client_for(employee).patch(
        f"{URL}{leave.id}/", {"start_date": str(day(10)), "end_date": str(day(11))}, format="json"
    )
    assert response.status_code == 200


def test_rejected_leave_does_not_block_editing_into_its_dates(client_for, employee, make_leave, day):
    make_leave(employee, start=10, end=12, status="REJECTED")
    leave = make_leave(employee, start=20, end=21)
    response = client_for(employee).patch(
        f"{URL}{leave.id}/", {"start_date": str(day(10)), "end_date": str(day(12))}, format="json"
    )
    assert response.status_code == 200


def test_unauthenticated_edit_is_rejected(api_client, employee, make_leave):
    leave = make_leave(employee)
    assert api_client.patch(f"{URL}{leave.id}/", {"reason": "x"}, format="json").status_code == 401


# ------------------------------------------- button state: can_modify / can_review
def test_can_modify_is_true_only_while_pending_for_the_owner(client_for, employee, manager, make_leave):
    pending = make_leave(employee, start=1)
    approved = make_leave(employee, start=5, status="APPROVED", approved_by=manager)
    rejected = make_leave(employee, start=9, status="REJECTED", approved_by=manager)

    results = {
        item["id"]: item["can_modify"] for item in client_for(employee).get(URL).data["results"]
    }

    assert results == {pending.id: True, approved.id: False, rejected.id: False}


def test_creating_a_leave_returns_can_modify_true(client_for, employee, day):
    response = client_for(employee).post(
        URL,
        {"leave_type": "CASUAL", "start_date": str(day(3)), "end_date": str(day(4)), "reason": "x"},
        format="json",
    )
    assert response.data["can_modify"] is True


def test_can_modify_becomes_false_after_the_decision(client_for, employee, manager, make_leave):
    leave = make_leave(employee)
    assert client_for(employee).get(f"{URL}{leave.id}/").data["can_modify"] is True

    client_for(manager).patch(f"{URL}{leave.id}/approve/")

    assert client_for(employee).get(f"{URL}{leave.id}/").data["can_modify"] is False


def test_can_modify_is_false_for_reviewers_viewing_someone_elses_leave(
    client_for, manager, admin_user, employee, make_leave
):
    leave = make_leave(employee)
    assert client_for(manager).get(f"{URL}{leave.id}/").data["can_modify"] is False
    assert client_for(admin_user).get(f"{URL}{leave.id}/").data["can_modify"] is False


def test_can_review_flag_follows_the_rules(
    client_for, manager, other_manager, admin_user, employee, make_leave
):
    employee_leave = make_leave(employee, start=1)
    managers_leave = make_leave(manager, start=5)
    decided = make_leave(employee, start=9, status="APPROVED", approved_by=admin_user)

    def flags(user):
        return {i["id"]: i["can_review"] for i in client_for(user).get(URL).data["results"]}

    manager_flags = flags(manager)
    assert manager_flags[employee_leave.id] is True       # employee leave, pending
    assert manager_flags[managers_leave.id] is False      # own leave
    assert manager_flags[decided.id] is False             # already decided

    admin_flags = flags(admin_user)
    assert admin_flags[employee_leave.id] is True
    assert admin_flags[managers_leave.id] is True         # only an admin can review it
    assert admin_flags[decided.id] is False

    assert set(flags(employee).values()) == {False}


def test_leave_model_still_pending_after_failed_actions(client_for, employee, manager, make_leave):
    leave = make_leave(employee)
    client_for(employee).patch(f"{URL}{leave.id}/approve/")  # 403
    client_for(manager).delete(f"{URL}{leave.id}/")  # 403
    leave.refresh_from_db()
    assert leave.status == "PENDING"
    assert Leave.objects.filter(pk=leave.pk).exists()
