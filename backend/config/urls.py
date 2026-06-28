from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path


admin.site.site_header = "Контроль сварных швов"
admin.site.site_title = "Контроль сварных швов"
admin.site.index_title = "Панель администратора"


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("accounts.api_urls")),
    path("api/", include("organizations.urls")),
    path("api/", include("inspections.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
