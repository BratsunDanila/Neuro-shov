from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "username",
        "full_name_with_middle",
        "organization",
        "role",
        "employee_number",
        "is_active",
    )
    list_filter = ("role", "organization", "is_active", "is_staff")
    search_fields = ("username", "first_name", "last_name", "middle_name", "employee_number")
    fieldsets = UserAdmin.fieldsets + (
        (
            "Профиль предприятия",
            {
                "fields": (
                    "organization",
                    "role",
                    "middle_name",
                    "position",
                    "employee_number",
                    "phone",
                    "must_change_password",
                )
            },
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Профиль предприятия",
            {"fields": ("organization", "role", "employee_number")},
        ),
    )
