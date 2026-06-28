from django.db import models


class MlTaskType(models.TextChoices):
    CLASSIFICATION = "classification", "Классификация"
    DETECTION = "detection", "Детекция"
    SEGMENTATION = "segmentation", "Сегментация"
    PIPELINE = "pipeline", "Pipeline"
    OTHER = "other", "Другое"


class MlModel(models.Model):
    code = models.SlugField("код", max_length=80, unique=True)
    name = models.CharField("название", max_length=255)
    task_type = models.CharField("тип задачи", max_length=32, choices=MlTaskType.choices)
    description = models.TextField("описание", blank=True)
    is_active = models.BooleanField("активно", default=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        verbose_name = "ML-модель"
        verbose_name_plural = "ML-модели"
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} ({self.get_task_type_display()})"


class MlModelVersion(models.Model):
    model = models.ForeignKey(MlModel, verbose_name="модель", on_delete=models.PROTECT, related_name="versions")
    version = models.CharField("версия", max_length=120)
    format = models.CharField("формат", max_length=32, blank=True)
    file_hash = models.CharField("hash файла", max_length=128, blank=True)
    input_size = models.CharField("размер входа", max_length=64, blank=True)
    classes_json = models.JSONField("классы", default=dict, blank=True)
    metadata_json = models.JSONField("метаданные", default=dict, blank=True)
    is_active = models.BooleanField("активно", default=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)

    class Meta:
        verbose_name = "версия ML-модели"
        verbose_name_plural = "версии ML-моделей"
        ordering = ["model__code", "-created_at"]
        unique_together = [("model", "version")]

    def __str__(self) -> str:
        return f"{self.model.code}:{self.version}"
