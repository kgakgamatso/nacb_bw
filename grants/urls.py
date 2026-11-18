from django.urls import path

from . import committee, views

app_name = "grants"

urlpatterns = [
    path("", views.call_list, name="call_list"),
    path("my-applications/", views.my_applications, name="my_applications"),
    path("application/<str:ref>/", views.application_detail, name="application_detail"),
    path("application/<str:ref>/step/<int:n>/", views.step, name="step"),
    path("application/<str:ref>/withdraw/", views.withdraw, name="withdraw"),
    path("document/<int:pk>/", views.document, name="document"),
    path("committee/", committee.committee_list, name="committee_list"),
    path("committee/new/", committee.committee_create, name="committee_create"),
    path("committee/<int:pk>/", committee.committee_detail, name="committee_detail"),
    path("committee/<int:pk>/start/", committee.committee_start, name="committee_start"),
    path("committee/<int:pk>/decisions/", committee.committee_decisions, name="committee_decisions"),
    path("committee/<int:pk>/conclude/", committee.committee_conclude, name="committee_conclude"),
    path("committee/<int:pk>/report/", committee.committee_report, name="committee_report"),
    path("committee/<int:pk>/publish/", committee.committee_publish, name="committee_publish"),
    path("committee/<int:pk>/assess/<str:ref>/", committee.committee_assess, name="committee_assess"),
    path("my-grant/<str:ref>/", committee.my_grant, name="my_grant"),
    path("monitoring/", committee.monitor_list, name="monitor_list"),
    path("monitoring/report/<int:pk>/review/", committee.monitor_review_report, name="monitor_review_report"),
    path("monitoring/report/<int:pk>/file/", committee.report_attachment, name="report_attachment"),
    path("monitoring/<str:ref>/", committee.monitor_detail, name="monitor_detail"),
    path("manage/", views.manage_list, name="manage_list"),
    path("manage/<str:ref>/", views.manage_detail, name="manage_detail"),
    path("manage/<str:ref>/assign/", views.manage_assign, name="manage_assign"),
    path("manage/<str:ref>/review/", views.manage_review, name="manage_review"),
    path("manage/<str:ref>/decide/", views.manage_decide, name="manage_decide"),
    path("manage/<str:ref>/comment/", views.manage_comment, name="manage_comment"),
    path("manage/<str:ref>/document/<int:pk>/verify/", views.manage_verify_doc, name="manage_verify_doc"),
    path("<slug:slug>/", views.call_detail, name="call_detail"),
    path("<slug:slug>/apply/", views.apply, name="apply"),
]
