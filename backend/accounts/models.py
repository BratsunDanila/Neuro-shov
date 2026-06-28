from django.contrib.auth.models import AbstractUser
from django.db import models


class UserRole(models.TextChoices):
    SUPERADMIN = "superadmin", "Суперадмин"
    ORG_ADMIN = "org_admin", "Админ предприятия"
    CONTROLLER = "controller", "Контролер"
    WORKER = "worker", "Работник"


class User(AbstractUser):
    organization = models.ForeignKey(
        "organizations.Organization",
        verbose_name="предприятие",
        on_delete=models.PROTECT,
        related_name="users",
        null=True,
        blank=True,
    )
    role = models.CharField("роль", max_length=32, choices=UserRole.choices, default=UserRole.WORKER)
    middle_name = models.CharField("отчество", max_length=150, blank=True)
    position = models.CharField("должность", max_length=150, blank=True)
    employee_number = models.CharField("табельный номер", max_length=64, blank=True)
    phone = models.CharField("телефон", max_length=32, blank=True)
    must_change_password = models.BooleanField("должен сменить пароль", default=True)

    class Meta:
        verbose_name = "пользователь"
        verbose_name_plural = "пользователи"
        ordering = ["organization__name", "last_name", "first_name", "username"]

    @property
    def full_name_with_middle(self) -> str:
        parts = [self.last_name, self.first_name, self.middle_name]
        return " ".join(part for part in parts if part).strip() or self.username
