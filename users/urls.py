from django.urls import path

from .views import ManagerCreateView, UserListView

urlpatterns = [
    path("", UserListView.as_view(), name="user-list"),
    path("managers/", ManagerCreateView.as_view(),name="create-manager"),
]
