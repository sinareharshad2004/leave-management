from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import EmployeeLoginView, ManagerLoginView, MeView, RegisterView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", TokenObtainPairView.as_view(), name="auth-login"),
    path("employee/login/", EmployeeLoginView.as_view(), name="auth-employee-login"),
    path("manager/login/", ManagerLoginView.as_view(), name="auth-manager-login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="auth-token-refresh"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("managers/", ManagerLoginView.as_view(), name="auth-manager-login"),
]
