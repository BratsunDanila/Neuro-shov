from django.contrib import admin

from .models import Area, Organization, Site


class SiteInline(admin.TabularInline):
    model = Site
    extra = 0


class AreaInline(admin.TabularInline):
    model = Area
    extra = 0


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "short_name", "inn", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "short_name", "inn")
    inlines = [SiteInline]


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "is_active", "created_at")
    list_filter = ("organization", "is_active")
    search_fields = ("name", "address", "organization__name")
    inlines = [AreaInline]


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("name", "site", "organization", "is_active", "created_at")
    list_filter = ("site__organization", "site", "is_active")
    search_fields = ("name", "site__name", "site__organization__name")

    @admin.display(ordering="site__organization", description="Предприятие")
    def organization(self, obj: Area):
        return obj.site.organization
