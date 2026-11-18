from django.urls import path

from . import views

app_name = "partnerships"

urlpatterns = [
    path("", views.partner, name="partner"),
    path("csr/<slug:slug>/", views.programme, name="programme"),
    path("manage/", views.manage_list, name="manage_list"),
    path("manage/<int:pk>/", views.manage_detail, name="manage_detail"),
    path("manage/<int:pk>/update/", views.manage_update, name="manage_update"),
]
