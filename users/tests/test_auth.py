import pytest

pytestmark = pytest.mark.django_db


def test_register_creates_employee(api_client, password):
    response = api_client.post(
        "/api/auth/register/",
        {"name": "Asha", "email": "asha@example.com", "password": password},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["email"] == "asha@example.com"
    assert response.data["role"] == "EMPLOYEE"
    assert "password" not in response.data


def test_register_cannot_choose_role(api_client, password):
    """Self-registering as ADMIN must not work (privilege escalation)."""
    response = api_client.post(
        "/api/auth/register/",
        {"name": "Evil", "email": "evil@example.com", "password": password, "role": "ADMIN"},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["role"] == "EMPLOYEE"


def test_register_duplicate_email_rejected(api_client, employee, password):
    response = api_client.post(
        "/api/auth/register/",
        {"name": "Dup", "email": employee.email.upper(), "password": password},
        format="json",
    )
    assert response.status_code == 400
    assert "email" in response.data


def test_register_weak_password_rejected(api_client):
    response = api_client.post(
        "/api/auth/register/",
        {"name": "Weak", "email": "weak@example.com", "password": "123"},
        format="json",
    )
    assert response.status_code == 400
    assert "password" in response.data


def test_login_works_and_token_can_access_me(api_client, employee, password):
    response = api_client.post(
        "/api/auth/login/",
        {"email": employee.email, "password": password},
        format="json",
    )
    assert response.status_code == 200
    assert "access" in response.data
    assert "refresh" in response.data

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    me = api_client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.data["email"] == employee.email
    assert me.data["role"] == "EMPLOYEE"


def test_login_with_wrong_password_fails(api_client, employee):
    response = api_client.post(
        "/api/auth/login/",
        {"email": employee.email, "password": "wrong-password"},
        format="json",
    )
    assert response.status_code == 401


def test_me_requires_authentication(api_client):
    assert api_client.get("/api/auth/me/").status_code == 401


def test_user_list_is_admin_only(client_for, employee, manager, admin_user):
    assert client_for(employee).get("/api/users/").status_code == 403
    assert client_for(manager).get("/api/users/").status_code == 403

    response = client_for(admin_user).get("/api/users/")
    assert response.status_code == 200
    assert response.data["count"] == 3


def test_user_list_requires_authentication(api_client):
    assert api_client.get("/api/users/").status_code == 401
