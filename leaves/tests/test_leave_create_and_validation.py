import pytest

pytestmark = pytest.mark.django_db

URL = "/api/leaves/"


def payload(day, start, end, leave_type="CASUAL"):
    return {
        "leave_type": leave_type,
        "start_date": day(start).isoformat(),
        "end_date": day(end).isoformat(),
        "reason": "Family function",
    }


def test_unauthorized_requests_are_rejected(api_client, make_leave, employee):
    leave = make_leave(employee)
    assert api_client.get(URL).status_code == 401
    assert api_client.post(URL, {}, format="json").status_code == 401
    assert api_client.get(f"{URL}{leave.id}/").status_code == 401
    assert api_client.delete(f"{URL}{leave.id}/").status_code == 401
    assert api_client.patch(f"{URL}{leave.id}/approve/").status_code == 401


def test_employee_can_create_leave(client_for, employee, day):
    response = client_for(employee).post(URL, payload(day, 5, 6), format="json")

    assert response.status_code == 201
    assert response.data["status"] == "PENDING"
    assert response.data["employee"]["email"] == employee.email
    assert response.data["approved_by"] is None
    assert response.data["approved_by_name"] is None


def test_client_cannot_set_status_or_employee(client_for, employee, other_employee, day):
    data = payload(day, 5, 6)
    data.update({"status": "APPROVED", "employee": other_employee.id, "approved_by": employee.id})

    response = client_for(employee).post(URL, data, format="json")

    assert response.status_code == 201
    assert response.data["status"] == "PENDING"
    assert response.data["employee"]["id"] == employee.id
    assert response.data["approved_by"] is None


def test_start_date_after_end_date_is_rejected(client_for, employee, day):
    response = client_for(employee).post(URL, payload(day, 6, 5), format="json")

    assert response.status_code == 400
    assert "end_date" in response.data


def test_start_date_in_the_past_is_rejected(client_for, employee, day):
    response = client_for(employee).post(URL, payload(day, -2, 1), format="json")

    assert response.status_code == 400
    assert "start_date" in response.data


def test_single_day_leave_is_allowed(client_for, employee, day):
    response = client_for(employee).post(URL, payload(day, 3, 3), format="json")
    assert response.status_code == 201


def test_today_is_allowed(client_for, employee, day):
    response = client_for(employee).post(URL, payload(day, 0, 1), format="json")
    assert response.status_code == 201


def test_missing_and_invalid_fields_give_clear_errors(client_for, employee):
    response = client_for(employee).post(
        URL, {"leave_type": "HOLIDAY", "start_date": "not-a-date"}, format="json"
    )
    assert response.status_code == 400
    assert "leave_type" in response.data
    assert "start_date" in response.data
    assert "end_date" in response.data
    assert "reason" in response.data


def test_overlapping_leave_is_rejected(client_for, employee, make_leave, day):
    # existing: day 10 -> 12, new: day 11 -> 15 (the example from the task)
    make_leave(employee, start=10, end=12)

    response = client_for(employee).post(URL, payload(day, 11, 15), format="json")

    assert response.status_code == 400
    assert "overlaps" in str(response.data["non_field_errors"][0])


@pytest.mark.parametrize(
    "start,end",
    [
        (8, 10),   # touches the first day
        (12, 14),  # touches the last day (end date is inclusive)
        (11, 11),  # inside
        (8, 14),   # wraps around
    ],
)
def test_all_overlap_shapes_are_rejected(client_for, employee, make_leave, day, start, end):
    make_leave(employee, start=10, end=12)
    response = client_for(employee).post(URL, payload(day, start, end), format="json")
    assert response.status_code == 400


def test_adjacent_leave_is_allowed(client_for, employee, make_leave, day):
    make_leave(employee, start=10, end=12)
    response = client_for(employee).post(URL, payload(day, 13, 14), format="json")
    assert response.status_code == 201


def test_rejected_leave_does_not_block_new_request(client_for, employee, make_leave, day):
    make_leave(employee, start=10, end=12, status="REJECTED")
    response = client_for(employee).post(URL, payload(day, 10, 12), format="json")
    assert response.status_code == 201


def test_other_employees_leave_does_not_block(client_for, employee, other_employee, make_leave, day):
    make_leave(other_employee, start=10, end=12)
    response = client_for(employee).post(URL, payload(day, 10, 12), format="json")
    assert response.status_code == 201


def test_manager_can_create_own_leave(client_for, manager, day):
    response = client_for(manager).post(URL, payload(day, 3, 4), format="json")

    assert response.status_code == 201
    assert response.data["status"] == "PENDING"
    assert response.data["employee"]["id"] == manager.id
    assert response.data["approved_by"] is None


def test_admin_cannot_create_leave(client_for, admin_user, day):
    response = client_for(admin_user).post(URL, payload(day, 3, 4), format="json")
    assert response.status_code == 403


def test_overlap_rule_also_applies_to_managers(client_for, manager, make_leave, day):
    make_leave(manager, start=10, end=12)
    response = client_for(manager).post(URL, payload(day, 11, 15), format="json")
    assert response.status_code == 400
