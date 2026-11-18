from django.urls import path

from . import views

app_name = "endorsements"

urlpatterns = [
    path("", views.info, name="info"),
    path("request/", views.create, name="create"),
    path("mine/", views.mine, name="mine"),
    path("verify/", views.verify, name="verify"),
    path("manage/", views.manage_list, name="manage_list"),
    path("manage/<str:ref>/", views.manage_detail, name="manage_detail"),
    path("manage/<str:ref>/action/", views.manage_action, name="manage_action"),
    path("manage/<str:ref>/letter/", views.manage_letter, name="manage_letter"),
    path("<str:ref>/", views.detail, name="detail"),
    path("<str:ref>/letter/", views.letter, name="letter"),
    path("<str:ref>/document/", views.document, name="document"),
]
