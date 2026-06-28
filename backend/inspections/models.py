from django.conf import settings
from django.db import models


def inspection_upload_path(instance: "Inspection", filename: str) -> str:
    organization_id = instance.organization_id or "unknown-org"
    return f"inspections/{organization_id}/{instance.id or 'new'}/{filename}"


class InspectionStatus(models.TextChoices):
    DRAFT = "draft", "Черновик"
    ANALYZED = "analyzed", "Проанализировано"
    QUEUED = "queued", "В очереди"
    UPLOADED = "uploaded", "Загружено"
    INVALID_PHOTO = "invalid_photo", "Некорректное фото"
    NO_WELD_DETECTED = "no_weld_detected", "Шов не обнаружен"
    NEEDS_REVIEW = "needs_review", "Требует проверки"
    REVIEWED = "reviewed", "Проверено"


class AnalysisStatus(models.TextChoices):
    PENDING = "pending", "Ожидает"
    RUNNING = "running", "Выполняется"
    SUCCESS = "success", "Успешно"
    FAILED = "failed", "Ошибка"
    SKIPPED = "skipped", "Пропущено"


class AnalysisSource(models.TextChoices):
    MOBILE = "mobile", "Телефон"
    SERVER = "server", "Сервер"
    MANUAL = "manual", "Вручную"


class Inspection(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization",
        verbose_name="предприятие",
        on_delete=models.PROTECT,
        related_name="inspections",
    )
    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="работник",
        on_delete=models.PROTECT,
        related_name="inspections",
    )
    site = models.ForeignKey(
        "organizations.Site",
        verbose_name="объект",
        on_delete=models.PROTECT,
        related_name="inspections",
        null=True,
        blank=True,
    )
    area = models.ForeignKey(
        "organizations.Area",
        verbose_name="участок",
        on_delete=models.PROTECT,
        related_name="inspections",
        null=True,
        blank=True,
    )
    captured_at = models.DateTimeField("время съемки")
    uploaded_at = models.DateTimeField("время загрузки", null=True, blank=True)
    original_image = models.ImageField("исходное фото", upload_to=inspection_upload_path)
    annotated_image = models.ImageField("фото с анализом", upload_to=inspection_upload_path, blank=True)
    latitude = models.FloatField("широта", null=True, blank=True)
    longitude = models.FloatField("долгота", null=True, blank=True)
    location_accuracy_m = models.FloatField("точность геолокации, м", null=True, blank=True)
    status = models.CharField("статус", max_length=32, choices=InspectionStatus.choices, default=InspectionStatus.DRAFT)
    summary_json = models.JSONField("сводка анализа", default=dict, blank=True)
    worker_snapshot_json = models.JSONField("снимок данных работника", default=dict, blank=True)
    app_version = models.CharField("версия приложения", max_length=64, blank=True)
    device_id = models.CharField("ID устройства", max_length=128, blank=True)
    device_info_json = models.JSONField("данные устройства", default=dict, blank=True)
    comment = models.TextField("комментарий", blank=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)
    updated_at = models.DateTimeField("обновлено", auto_now=True)

    class Meta:
        verbose_name = "проверка"
        verbose_name_plural = "проверки"
        ordering = ["-captured_at"]
        indexes = [
            models.Index(fields=["organization", "-captured_at"]),
            models.Index(fields=["worker", "-captured_at"]),
            models.Index(fields=["status", "-captured_at"]),
        ]

    def __str__(self) -> str:
        return f"Inspection #{self.pk} by {self.worker} at {self.captured_at:%Y-%m-%d %H:%M}"


class AnalysisRun(models.Model):
    inspection = models.ForeignKey(Inspection, verbose_name="проверка", on_delete=models.CASCADE, related_name="analysis_runs")
    pipeline_code = models.SlugField("код pipeline", max_length=80)
    pipeline_version = models.CharField("версия pipeline", max_length=120)
    source = models.CharField("источник", max_length=32, choices=AnalysisSource.choices, default=AnalysisSource.MOBILE)
    status = models.CharField("статус", max_length=32, choices=AnalysisStatus.choices, default=AnalysisStatus.PENDING)
    started_at = models.DateTimeField("начато", null=True, blank=True)
    finished_at = models.DateTimeField("завершено", null=True, blank=True)
    latency_ms = models.PositiveIntegerField("время выполнения, мс", null=True, blank=True)
    summary_json = models.JSONField("сводка", default=dict, blank=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)

    class Meta:
        verbose_name = "запуск анализа"
        verbose_name_plural = "запуски анализа"
        ordering = ["inspection", "-created_at"]
        indexes = [models.Index(fields=["pipeline_code", "pipeline_version"])]

    def __str__(self) -> str:
        return f"{self.pipeline_code}:{self.pipeline_version} for inspection #{self.inspection_id}"


class AnalysisStage(models.Model):
    analysis_run = models.ForeignKey(AnalysisRun, verbose_name="запуск анализа", on_delete=models.CASCADE, related_name="stages")
    stage_code = models.SlugField("код этапа", max_length=80)
    stage_name = models.CharField("название этапа", max_length=255, blank=True)
    stage_order = models.PositiveSmallIntegerField("порядок", default=1)
    model_version = models.ForeignKey(
        "ml.MlModelVersion",
        verbose_name="версия модели",
        on_delete=models.PROTECT,
        related_name="analysis_stages",
        null=True,
        blank=True,
    )
    status = models.CharField("статус", max_length=32, choices=AnalysisStatus.choices, default=AnalysisStatus.PENDING)
    confidence = models.FloatField("уверенность", null=True, blank=True)
    result_json = models.JSONField("результат", default=dict, blank=True)
    latency_ms = models.PositiveIntegerField("время выполнения, мс", null=True, blank=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)

    class Meta:
        verbose_name = "этап анализа"
        verbose_name_plural = "этапы анализа"
        ordering = ["analysis_run", "stage_order", "id"]
        unique_together = [("analysis_run", "stage_code", "stage_order")]

    def __str__(self) -> str:
        return f"{self.stage_order}. {self.stage_code} ({self.status})"


class Detection(models.Model):
    analysis_stage = models.ForeignKey(AnalysisStage, verbose_name="этап анализа", on_delete=models.CASCADE, related_name="detections")
    class_id = models.IntegerField("ID класса")
    class_name = models.CharField("класс", max_length=120)
    confidence = models.FloatField("уверенность")
    bbox_json = models.JSONField("рамка bbox", default=list, blank=True)
    mask_json = models.JSONField("маска", default=dict, blank=True)
    area_px = models.PositiveIntegerField("площадь, px", null=True, blank=True)
    metadata_json = models.JSONField("метаданные", default=dict, blank=True)
    created_at = models.DateTimeField("создано", auto_now_add=True)

    class Meta:
        verbose_name = "обнаружение"
        verbose_name_plural = "обнаружения"
        ordering = ["analysis_stage", "-confidence"]
        indexes = [models.Index(fields=["class_name", "-confidence"])]

    def __str__(self) -> str:
        return f"{self.class_name} {self.confidence:.2f}"
