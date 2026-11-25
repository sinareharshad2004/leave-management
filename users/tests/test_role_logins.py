import pytest

pytestmark = pytest.mark.django_db

EMPLOYEE_LOGIN = "/api/auth/employee/login/"
MANAGER_LOGIN = "/api/auth/manager/login/"


def _login(client, url, user, password):
    return client.post(
        url, {"email": user.email, "password": password}, format="json"
    )


def test_employee_can_log_in_on_employee_login(api_client, employee, password):
    response = _login(api_client, EMPLOYEE_LOGIN, employee, password)
    assert response.status_code == 200
    assert "access" in response.data and "refresh" in response.data
    assert response.data["user"]["role"] == "EMPLOYEE"


def test_manager_can_log_in_on_manager_login(api_client, manager, password):
    response = _login(api_client, MANAGER_LOGIN, manager, password)
    assert response.status_code == 200
    assert response.data["user"]["role"] == "MANAGER"


def test_admin_can_log_in_on_manager_login(api_client, admin_user, password):
    assert _login(api_client, MANAGER_LOGIN, admin_user, password).status_code == 200


def test_manager_cannot_use_employee_login(api_client, manager, password):
    response = _login(api_client, EMPLOYEE_LOGIN, manager, password)
    assert response.status_code == 403
    assert "access" not in response.data


def test_employee_cannot_use_manager_login(api_client, employee, password):
    response = _login(api_client, MANAGER_LOGIN, employee, password)
    assert response.status_code == 403
    assert "access" not in response.data


@pytest.mark.parametrize("url", [EMPLOYEE_LOGIN, MANAGER_LOGIN])
def test_wrong_password_is_401_on_both_logins(api_client, employee, url):
    response = api_client.post(
        url, {"email": employee.email, "password": "wrong-password"}, format="json"
    )
    assert response.status_code == 401


def test_full_flow_employee_creates_manager_approves(
    api_client, employee, manager, password, day
):
    from rest_framework.test import APIClient

    # Employee logs in on the employee portal and creates a leave.
    employee_client = APIClient()
    token = _login(employee_client, EMPLOYEE_LOGIN, employee, password).data["access"]
    employee_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    created = employee_client.post(
        "/api/leaves/",
        {
            "leave_type": "SICK",
            "start_date": str(day(5)),
            "end_date": str(day(6)),
            "reason": "Fever",
        },
        format="json",
    )
    assert created.status_code == 201
    leave_id = created.data["id"]

    # The employee's token cannot approve.
    assert employee_client.patch(f"/api/leaves/{leave_id}/approve/").status_code == 403

    # Manager logs in on the manager portal and approves.
    manager_client = APIClient()
    token = _login(manager_client, MANAGER_LOGIN, manager, password).data["access"]
    manager_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    approved = manager_client.patch(f"/api/leaves/{leave_id}/approve/")
    assert approved.status_code == 200
    assert approved.data["status"] == "APPROVED"
