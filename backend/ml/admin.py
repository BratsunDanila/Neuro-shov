from django.contrib import admin

from .models import MlModel, MlModelVersion


class MlModelVersionInline(admin.TabularInline):
    model = MlModelVersion
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(MlModel)
class MlModelAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "task_type", "is_active", "updated_at")
    list_filter = ("task_type", "is_active")
    search_fields = ("code", "name", "description")
    inlines = [MlModelVersionInline]


@admin.register(MlModelVersion)
class MlModelVersionAdmin(admin.ModelAdmin):
    list_display = ("model", "version", "format", "input_size", "is_active", "created_at")
    list_filter = ("model", "format", "is_active")
    search_fields = ("model__code", "version", "file_hash")
    readonly_fields = ("created_at",)
