from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .enums import Role

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Read-only representation used by /me/ and the admin user list."""

    class Meta:
        model = User
        fields = ["id", "name", "email", "role"]
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    """
    Public registration.

    NOTE: `role` is deliberately NOT accepted here. Anyone who registers
    becomes an EMPLOYEE; otherwise a user could register themselves as ADMIN.
    Admins promote users from the Django admin site.
    """

    password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
        validators=[validate_password],
    )

    class Meta:
        model = User
        fields = ["id", "name", "email", "password"]
        read_only_fields = ["id"]

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def create(self, validated_data):
        # create_user() hashes the password.
        return User.objects.create_user(role=Role.EMPLOYEE, **validated_data)


class _RoleRestrictedTokenSerializer(TokenObtainPairSerializer):
    """
    Login that only succeeds for users whose role is in `allowed_roles`.

    Credentials are checked first (wrong password -> 401 as usual). Only then
    is the role checked, so a wrong-portal attempt gets a clear 403 message.
    """

    allowed_roles = ()
    wrong_portal_message = "You are not allowed to log in here."

    def validate(self, attrs):
        data = super().validate(attrs)  # raises 401-style error on bad credentials
        if self.user.role not in self.allowed_roles:
            raise PermissionDenied(self.wrong_portal_message)
        data["user"] = UserSerializer(self.user).data
        return data


class EmployeeTokenObtainPairSerializer(_RoleRestrictedTokenSerializer):
    allowed_roles = (Role.EMPLOYEE,)
    wrong_portal_message = "This is the employee login. Managers must use the manager login."


class ManagerTokenObtainPairSerializer(_RoleRestrictedTokenSerializer):
    allowed_roles = (Role.MANAGER, Role.ADMIN)
    wrong_portal_message = "This is the manager login. Employees must use the employee login."

class ManagerCreateSerializer(serializers.ModelSerializer):
 
    password = serializers.CharField(write_only=True, min_length=8)
    class Meta:
        model = User
        field = ["username", "email", "password"]

    def create(self, validated_data):
        return User.objects.create_user(role=Role.MANAGER, **validated_data)    