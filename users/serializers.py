from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

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
        return User.objects.create_user(**validated_data)
