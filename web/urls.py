from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="web-home"),
    path("login/", views.login_view, name="web-login"),
    # old addresses keep working: they forward to the single login page
    path("employee/login/", views.legacy_login),
    path("manager/login/", views.legacy_login),
    path("employee/register/", views.employee_register, name="web-employee-register"),
    path("manager/register/", views.manager_register, name="web-manager-register"),
    path("employee/", views.employee_dashboard, name="web-employee-dashboard"),
    path("manager/", views.manager_dashboard, name="web-manager-dashboard"),
    path("manager/leaves/<int:leave_id>/approve/", views.approve, name="web-approve"),
    path("manager/leaves/<int:leave_id>/reject/", views.reject, name="web-reject"),
    path("notifications/<int:notification_id>/dismiss/", views.dismiss_notification, name="web-dismiss-notification"),
    path("leaves/<int:leave_id>/delete/", views.delete, name="web-delete"),
    path("logout/", views.logout_view, name="web-logout"),
]
