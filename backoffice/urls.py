from django.urls import path

from . import users, views

app_name = "backoffice"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("registry/", views.registry, name="registry"),
    path("registry/new/", views.assisted_registration, name="assisted_registration"),
    path("registry/import/", views.registry_import, name="registry_import"),
    path("registry/data-quality/", views.data_quality, name="data_quality"),
    path("registry/<int:pk>/", views.registry_detail, name="registry_detail"),
    path("registry/<int:pk>/edit/", views.registry_edit, name="registry_edit"),
    path("registry/<int:pk>/action/", views.registry_action, name="registry_action"),
    path("reports/", views.reports, name="reports"),
    path("communications/", views.communications, name="communications"),
    path("messages/", views.contact_messages, name="messages"),
    path("messages/<int:pk>/", views.contact_message, name="message_detail"),
    path("audit/", views.audit_log, name="audit"),
    path("users/", users.user_list, name="user_list"),
    path("users/new/", users.user_create, name="user_create"),
    path("users/bulk/", users.user_bulk, name="user_bulk"),
    path("users/<int:pk>/", users.user_detail, name="user_detail"),
    path("users/<int:pk>/action/", users.user_action, name="user_action"),
]
