from django.db import models


class Organization(models.Model):
    name = models.CharField("название", max_length=255, unique=True)
    short_name = models.CharField("краткое название", max_length=120, blank=True)
    inn = models.CharField("ИНН", max_length=32, blank=True)
    is_active = models.BooleanField("активно", default=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        verbose_name = "предприятие"
        verbose_name_plural = "предприятия"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.short_name or self.name


class Site(models.Model):
    organization = models.ForeignKey(Organization, verbose_name="предприятие", on_delete=models.PROTECT, related_name="sites")
    name = models.CharField("название", max_length=255)
    address = models.TextField("адрес", blank=True)
    is_active = models.BooleanField("активно", default=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)

    class Meta:
        verbose_name = "объект"
        verbose_name_plural = "объекты"
        ordering = ["organization__name", "name"]
        unique_together = [("organization", "name")]

    def __str__(self) -> str:
        return f"{self.organization}: {self.name}"


class Area(models.Model):
    site = models.ForeignKey(Site, verbose_name="объект", on_delete=models.PROTECT, related_name="areas")
    name = models.CharField("название", max_length=255)
    description = models.TextField("описание", blank=True)
    is_active = models.BooleanField("активно", default=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)

    class Meta:
        verbose_name = "участок"
        verbose_name_plural = "участки"
        ordering = ["site__organization__name", "site__name", "name"]
        unique_together = [("site", "name")]

    def __str__(self) -> str:
        return f"{self.site}: {self.name}"
