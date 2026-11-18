from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = "accounts"

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("login/", views.login_view, name="login"),
    path("login/verify/", views.mfa_verify, name="mfa_verify"),
    path("logout/", views.logout_view, name="logout"),
    path("verify-email/<str:token>/", views.verify_email, name="verify_email"),
    path("verify-email-resend/", views.resend_verification, name="resend_verification"),
    path("settings/", views.account_settings, name="settings"),
    path("mfa/setup/", views.mfa_setup, name="mfa_setup"),
    path("mfa/disable/", views.mfa_disable, name="mfa_disable"),
    path("profile/", views.profile_edit, name="profile_edit"),
    path("profile/privacy/", views.privacy, name="privacy"),
    path("profile/portfolio/", views.portfolio, name="portfolio"),
    path("profile/portfolio/<int:pk>/delete/", views.portfolio_delete, name="portfolio_delete"),
    path("files/portfolio/<int:pk>/", views.portfolio_file, name="portfolio_file"),
    path("files/id-document/<int:pk>/", views.id_document, name="id_document"),
    # Password recovery (FR-2.4)
    path("password-reset/", auth_views.PasswordResetView.as_view(
        template_name="accounts/password_reset.html",
        email_template_name="emails/password_reset.txt",
        subject_template_name="emails/password_reset_subject.txt",
        success_url=reverse_lazy("accounts:password_reset_done")), name="password_reset"),
    path("password-reset/sent/", auth_views.PasswordResetDoneView.as_view(
        template_name="accounts/password_reset_done.html"), name="password_reset_done"),
    path("password-reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="accounts/password_reset_confirm.html",
        success_url=reverse_lazy("accounts:password_reset_complete")), name="password_reset_confirm"),
    path("password-reset/complete/", auth_views.PasswordResetCompleteView.as_view(
        template_name="accounts/password_reset_complete.html"), name="password_reset_complete"),
]
