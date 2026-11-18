from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from portal import ops

admin.site.site_header = "NACB Content & System Administration"
admin.site.site_title = "NACB Admin"
admin.site.index_title = "Content management and configuration"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("ops/setup/", ops.setup),
    path("accounts/", include("accounts.urls")),
    path("grants/", include("grants.urls")),
    path("events/", include("events.urls")),
    path("endorsements/", include("endorsements.urls")),
    path("staff/", include("backoffice.urls")),
    path("partner/", include("partnerships.urls")),
    path("", include("portal.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = "portal.views.error_404"
handler500 = "portal.views.error_500"
