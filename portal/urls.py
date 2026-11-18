from django.urls import path

from . import views, views_extra

app_name = "portal"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("services/", views.services, name="services"),
    path("news/", views.news_list, name="news_list"),
    path("news/<slug:slug>/", views.news_detail, name="news_detail"),
    path("gallery/", views.gallery, name="gallery"),
    path("gallery/<slug:slug>/", views.album, name="album"),
    path("resources/", views.resources, name="resources"),
    path("resources/<int:pk>/download/", views.resource_download, name="resource_download"),
    path("faqs/", views.faqs, name="faqs"),
    path("contact/", views.contact, name="contact"),
    path("newsletter/subscribe/", views.subscribe, name="subscribe"),
    path("newsletter/unsubscribe/<str:token>/", views.unsubscribe, name="unsubscribe"),
    path("search/", views.search, name="search"),
    path("directory/", views.directory, name="directory"),
    path("directory/<int:pk>/", views.artist_detail, name="artist_detail"),
    path("language/", views.set_language, name="set_language"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/<int:pk>/", views.notification_open, name="notification_open"),
    path("notifications/read-all/", views.notifications_read_all, name="notifications_read_all"),
    path("jobs/", views_extra.vacancies, name="vacancies"),
    path("jobs/<slug:slug>/", views_extra.vacancy_detail, name="vacancy_detail"),
    path("tenders/", views_extra.tenders, name="tenders"),
    path("tenders/<slug:slug>/", views_extra.tender_detail, name="tender_detail"),
    path("data-protection/", views_extra.data_protection, name="data_protection"),
    path("data-protection/my-data.json", views_extra.my_data_export, name="my_data_export"),
    path("p/<slug:slug>/", views.page, name="page"),
]
