"""Shared pytest fixtures for the whole project."""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from leaves.models import Leave

User = get_user_model()
PASSWORD = "StrongPass123!"


@pytest.fixture(autouse=True)
def fast_password_hasher(settings):
    """Cheap hasher so creating users in tests is fast."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def password():
    return PASSWORD


def _make_user(email, name, role):
    return User.objects.create_user(email=email, name=name, password=PASSWORD, role=role)


@pytest.fixture
def employee(db):
    return _make_user("employee@example.com", "Emma Employee", "EMPLOYEE")


@pytest.fixture
def other_employee(db):
    return _make_user("other@example.com", "Oliver Other", "EMPLOYEE")


@pytest.fixture
def manager(db):
    return _make_user("manager@example.com", "Maya Manager", "MANAGER")


@pytest.fixture
def other_manager(db):
    return _make_user("manager2@example.com", "Mike Manager", "MANAGER")


@pytest.fixture
def admin_user(db):
    return _make_user("admin@example.com", "Adam Admin", "ADMIN")


@pytest.fixture
def api_client():
    """Anonymous client (no credentials)."""
    return APIClient()


@pytest.fixture
def client_for():
    """client_for(user) -> APIClient authenticated as that user."""

    def _client_for(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    return _client_for


@pytest.fixture
def day():
    """day(n) -> the date n days from today (so tests never depend on a fixed date)."""

    def _day(offset):
        return timezone.localdate() + timedelta(days=offset)

    return _day


@pytest.fixture
def make_leave(day):
    """Create a leave directly in the DB (skips API validation)."""

    def _make_leave(
        employee,
        start=1,
        end=None,
        leave_type="CASUAL",
        status="PENDING",
        approved_by=None,
    ):
        end = start if end is None else end
        return Leave.objects.create(
            employee=employee,
            leave_type=leave_type,
            start_date=day(start),
            end_date=day(end),
            reason="Test reason",
            status=status,
            approved_by=approved_by,
        )

    return _make_leave
