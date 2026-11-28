from django.contrib.auth import get_user_model
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from .permissions import IsAdminRole
from .serializers import (
    EmployeeTokenObtainPairSerializer,
    ManagerCreateSerializer,
    ManagerTokenObtainPairSerializer,
    RegisterSerializer,
    UserSerializer,
)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/"""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []  # a bad/expired token must not block sign-up

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class MeView(generics.RetrieveAPIView):
    """GET /api/auth/me/ - the currently logged-in user."""

    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class UserListView(generics.ListAPIView):
    """GET /api/users/ - admin only."""

    serializer_class = UserSerializer
    permission_classes = [IsAdminRole]
    queryset = User.objects.order_by("id")
    filterset_fields = ["role"]
    search_fields = ["name", "email"]
    ordering_fields = ["id", "name", "email"]


class EmployeeLoginView(TokenObtainPairView):
    """POST /api/auth/employee/login/ - only EMPLOYEE accounts can log in here."""

    serializer_class = EmployeeTokenObtainPairSerializer


class ManagerLoginView(TokenObtainPairView):
    """POST /api/auth/manager/login/ - only MANAGER (and ADMIN) accounts can log in here."""

    serializer_class = ManagerTokenObtainPairSerializer


class ManagerCreateView(generics.CreateAPIView):
    """POST /api/auth/managers/ - admin only."""

    serializer_class = ManagerCreateSerializer
    permission_classes = [IsAdminRole]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)