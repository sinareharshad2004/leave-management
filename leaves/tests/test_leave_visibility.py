import pytest

pytestmark = pytest.mark.django_db

URL = "/api/leaves/"


def ids(response):
    return {item["id"] for item in response.data["results"]}


def test_employee_sees_only_own_leaves(client_for, employee, other_employee, make_leave):
    mine = make_leave(employee, start=1)
    theirs = make_leave(other_employee, start=1)

    response = client_for(employee).get(URL)

    assert response.status_code == 200
    assert ids(response) == {mine.id}
    assert theirs.id not in ids(response)


def test_employee_cannot_open_another_employees_leave(client_for, employee, other_employee, make_leave):
    theirs = make_leave(other_employee)

    response = client_for(employee).get(f"{URL}{theirs.id}/")

    # 404 (not 403) so we don't even reveal that the id exists.
    assert response.status_code == 404


def test_employee_filter_by_other_employee_id_still_returns_nothing(
    client_for, employee, other_employee, make_leave
):
    make_leave(other_employee)
    response = client_for(employee).get(f"{URL}?employee={other_employee.id}")
    assert response.status_code == 200
    assert response.data["count"] == 0


def test_admin_can_access_all_leaves(client_for, admin_user, employee, other_employee, make_leave):
    a = make_leave(employee, start=1)
    b = make_leave(other_employee, start=1)

    response = client_for(admin_user).get(URL)

    assert response.status_code == 200
    assert ids(response) == {a.id, b.id}
    assert client_for(admin_user).get(f"{URL}{a.id}/").status_code == 200


def test_filter_by_status_leave_type_and_employee(
    client_for, admin_user, employee, other_employee, make_leave
):
    pending_casual = make_leave(employee, start=1, leave_type="CASUAL", status="PENDING")
    approved_sick = make_leave(employee, start=3, leave_type="SICK", status="APPROVED")
    other_paid = make_leave(other_employee, start=1, leave_type="PAID", status="PENDING")
    client = client_for(admin_user)

    assert ids(client.get(f"{URL}?status=PENDING")) == {pending_casual.id, other_paid.id}
    assert ids(client.get(f"{URL}?leave_type=SICK")) == {approved_sick.id}
    assert ids(client.get(f"{URL}?employee={employee.id}")) == {pending_casual.id, approved_sick.id}
    assert ids(client.get(f"{URL}?employee={employee.id}&status=APPROVED")) == {approved_sick.id}


def test_invalid_filter_value_returns_400(client_for, admin_user):
    assert client_for(admin_user).get(f"{URL}?status=NOPE").status_code == 400


def test_search_by_employee_name(client_for, admin_user, employee, other_employee, make_leave):
    mine = make_leave(employee, start=1)
    make_leave(other_employee, start=1)
    response = client_for(admin_user).get(f"{URL}?search=Emma")
    assert ids(response) == {mine.id}


def test_ordering(client_for, admin_user, employee, make_leave):
    first = make_leave(employee, start=1)
    second = make_leave(employee, start=5)

    newest_first = client_for(admin_user).get(f"{URL}?ordering=-created_at")
    oldest_first = client_for(admin_user).get(f"{URL}?ordering=created_at")
    latest_start = client_for(admin_user).get(f"{URL}?ordering=-start_date")

    assert [i["id"] for i in newest_first.data["results"]] == [second.id, first.id]
    assert [i["id"] for i in oldest_first.data["results"]] == [first.id, second.id]
    assert [i["id"] for i in latest_start.data["results"]] == [second.id, first.id]


def test_pagination(client_for, admin_user, employee, make_leave):
    for i in range(12):
        make_leave(employee, start=i * 2 + 1)

    client = client_for(admin_user)
    page1 = client.get(URL)
    page2 = client.get(f"{URL}?page=2")
    small = client.get(f"{URL}?page_size=5")

    assert page1.data["count"] == 12
    assert len(page1.data["results"]) == 10
    assert page1.data["next"] is not None
    assert len(page2.data["results"]) == 2
    assert len(small.data["results"]) == 5


def test_list_has_no_n_plus_one_queries(
    client_for, admin_user, employee, other_employee, manager, make_leave, django_assert_max_num_queries
):
    for i in range(5):
        make_leave(employee, start=i * 2 + 1, status="APPROVED", approved_by=manager)
        make_leave(other_employee, start=i * 2 + 1, status="APPROVED", approved_by=manager)

    # 1 COUNT query for pagination + 1 SELECT with JOINs, no matter how many rows.
    with django_assert_max_num_queries(3):
        response = client_for(admin_user).get(URL)

    assert response.status_code == 200
    first = response.data["results"][0]
    assert first["employee"]["name"]
    assert first["employee"]["email"]
    assert first["approved_by_name"] == manager.name
