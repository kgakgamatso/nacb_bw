from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    path("", views.event_list, name="list"),
    path("manage/", views.manage_list, name="manage_list"),
    path("manage/<slug:slug>/", views.manage_detail, name="manage_detail"),
    path("manage/<slug:slug>/attendance/", views.manage_attendance, name="manage_attendance"),
    path("<slug:slug>/", views.event_detail, name="detail"),
    path("<slug:slug>/register/", views.register, name="register"),
    path("<slug:slug>/cancel/", views.cancel, name="cancel"),
    path("<slug:slug>/calendar.ics", views.ics, name="ics"),
]
