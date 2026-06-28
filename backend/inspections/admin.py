from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html, format_html_join

from .models import AnalysisRun, AnalysisStage, Detection, Inspection


class DetectionInline(admin.TabularInline):
    model = Detection
    extra = 0
    readonly_fields = ("created_at",)


class AnalysisStageInline(admin.TabularInline):
    model = AnalysisStage
    extra = 0
    readonly_fields = ("created_at",)


class AnalysisRunInline(admin.TabularInline):
    model = AnalysisRun
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Inspection)
class InspectionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "original_image_thumb",
        "annotated_image_thumb",
        "organization",
        "worker_full_name",
        "status",
        "captured_at",
        "detections_count",
        "location_summary",
        "uploaded_at",
    )
    list_filter = ("organization", "status", "site", "area", "captured_at")
    search_fields = ("id", "worker__username", "worker__last_name", "worker__employee_number")
    readonly_fields = (
        "inspection_card",
        "image_comparison",
        "detections_summary",
        "original_image_preview",
        "annotated_image_preview",
        "map_link",
        "created_at",
        "updated_at",
    )
    inlines = [AnalysisRunInline]
    date_hierarchy = "captured_at"

    fieldsets = (
        (None, {"fields": ("inspection_card", "image_comparison", "detections_summary")}),
        ("Проверка", {"fields": ("organization", "worker", "site", "area", "status", "comment")}),
        ("Время", {"fields": ("captured_at", "uploaded_at", "created_at", "updated_at")}),
        (
            "Фотографии",
            {
                "fields": (
                    "original_image",
                    "original_image_preview",
                    "annotated_image",
                    "annotated_image_preview",
                )
            },
        ),
        ("Геолокация", {"fields": ("latitude", "longitude", "location_accuracy_m", "map_link")}),
        ("Клиент", {"fields": ("app_version", "device_id", "device_info_json", "worker_snapshot_json")}),
        ("Сводка", {"fields": ("summary_json",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            detections_total=Count("analysis_runs__stages__detections", distinct=True)
        )

    @admin.display(description="Фото")
    def original_image_thumb(self, obj: Inspection):
        return self._image_tag(obj.original_image, width=90)

    @admin.display(description="Анализ")
    def annotated_image_thumb(self, obj: Inspection):
        return self._image_tag(obj.annotated_image, width=90)

    @admin.display(description="Исходное фото")
    def original_image_preview(self, obj: Inspection):
        return self._image_tag(obj.original_image, width=480)

    @admin.display(description="Фото с анализом")
    def annotated_image_preview(self, obj: Inspection):
        return self._image_tag(obj.annotated_image, width=480)

    @admin.display(ordering="detections_total", description="Обнаружения")
    def detections_count(self, obj: Inspection):
        return getattr(obj, "detections_total", 0)

    @admin.display(ordering="worker__last_name", description="ФИО")
    def worker_full_name(self, obj: Inspection):
        return obj.worker.full_name_with_middle

    @admin.display(description="Карточка проверки")
    def inspection_card(self, obj: Inspection):
        detections_total = self._detections_queryset(obj).count()
        location = "не передана"
        if obj.latitude is not None and obj.longitude is not None:
            location = f"{obj.latitude:.6f}, {obj.longitude:.6f}"
            if obj.location_accuracy_m:
                location += f", ±{obj.location_accuracy_m:.0f} м"

        return format_html(
            """
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:12px;">
              <div style="padding:12px; border:1px solid #ddd; border-radius:8px; background:#fafafa;">
                <div style="font-size:12px; color:#666;">Сотрудник</div>
                <div style="font-size:16px; font-weight:600;">{}</div>
                <div style="margin-top:4px; color:#666;">{}</div>
              </div>
              <div style="padding:12px; border:1px solid #ddd; border-radius:8px; background:#fafafa;">
                <div style="font-size:12px; color:#666;">Время съемки</div>
                <div style="font-size:16px; font-weight:600;">{}</div>
                <div style="margin-top:4px; color:#666;">Статус: {}</div>
              </div>
              <div style="padding:12px; border:1px solid #ddd; border-radius:8px; background:#fafafa;">
                <div style="font-size:12px; color:#666;">Обнаружения</div>
                <div style="font-size:16px; font-weight:600;">{}</div>
                <div style="margin-top:4px; color:#666;">Геолокация: {}</div>
              </div>
              <div style="padding:12px; border:1px solid #ddd; border-radius:8px; background:#fafafa;">
                <div style="font-size:12px; color:#666;">Клиент</div>
                <div style="font-size:16px; font-weight:600;">{}</div>
                <div style="margin-top:4px; color:#666;">{}</div>
              </div>
            </div>
            """,
            obj.worker.full_name_with_middle,
            obj.worker.position or obj.worker.username,
            obj.captured_at.strftime("%d.%m.%Y %H:%M") if obj.captured_at else "-",
            obj.get_status_display(),
            detections_total,
            location,
            obj.app_version or "версия не передана",
            obj.device_info_json.get("model", "устройство не передано") if obj.device_info_json else "устройство не передано",
        )

    @admin.display(description="Фото проверки")
    def image_comparison(self, obj: Inspection):
        return format_html(
            """
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap:16px; align-items:start;">
              <div>
                <div style="font-weight:600; margin-bottom:8px;">Исходное фото</div>
                {}
              </div>
              <div>
                <div style="font-weight:600; margin-bottom:8px;">Фото с анализом</div>
                {}
              </div>
            </div>
            """,
            self._image_tag(obj.original_image, width=560),
            self._image_tag(obj.annotated_image, width=560),
        )

    @admin.display(description="Сводка обнаружений")
    def detections_summary(self, obj: Inspection):
        detections = list(self._detections_queryset(obj).order_by("-confidence")[:12])
        if not detections:
            return "Обнаружения не переданы"

        return format_html(
            """
            <table style="width:100%; max-width:720px; border-collapse:collapse;">
              <thead><tr><th style="text-align:left; padding:6px; border-bottom:1px solid #ddd;">Класс</th><th style="text-align:left; padding:6px; border-bottom:1px solid #ddd;">Уверенность</th><th style="text-align:left; padding:6px; border-bottom:1px solid #ddd;">Площадь, px</th></tr></thead>
              <tbody>{}</tbody>
            </table>
            """,
            format_html_join(
                "",
                '<tr><td style="padding:6px; border-bottom:1px solid #eee;">{}</td><td style="padding:6px; border-bottom:1px solid #eee;">{}</td><td style="padding:6px; border-bottom:1px solid #eee;">{}</td></tr>',
                ((det.class_name, f"{det.confidence:.2f}", det.area_px or "-") for det in detections),
            ),
        )

    @admin.display(description="Геолокация")
    def location_summary(self, obj: Inspection):
        if obj.latitude is None or obj.longitude is None:
            return "-"
        lat = f"{obj.latitude:.6f}"
        lon = f"{obj.longitude:.6f}"
        accuracy = f", ±{obj.location_accuracy_m:.0f} м" if obj.location_accuracy_m else ""
        return format_html(
            '<a href="https://yandex.ru/maps/?pt={},{}&z=17&l=map" target="_blank">{}, {}{}</a>',
            lon,
            lat,
            lat,
            lon,
            accuracy,
        )

    @admin.display(description="Карта")
    def map_link(self, obj: Inspection):
        if obj.latitude is None or obj.longitude is None:
            return "Геолокация не передана"
        lat = f"{obj.latitude:.6f}"
        lon = f"{obj.longitude:.6f}"
        return format_html(
            '<a href="https://yandex.ru/maps/?pt={},{}&z=17&l=map" target="_blank">Открыть на Яндекс Картах</a>',
            lon,
            lat,
        )

    def _image_tag(self, image, width: int):
        if not image:
            return "-"
        return format_html(
            '<a href="{}" target="_blank"><img src="{}" style="max-width:{}px; height:auto; border-radius:6px;" /></a>',
            image.url,
            image.url,
            width,
        )

    def _detections_queryset(self, obj: Inspection):
        return Detection.objects.filter(analysis_stage__analysis_run__inspection=obj)


@admin.register(AnalysisRun)
class AnalysisRunAdmin(admin.ModelAdmin):
    list_display = ("id", "inspection", "pipeline_code", "pipeline_version", "source", "status", "created_at")
    list_filter = ("source", "status", "pipeline_code", "pipeline_version")
    search_fields = ("inspection__id", "pipeline_code", "pipeline_version")
    readonly_fields = ("created_at",)
    inlines = [AnalysisStageInline]


@admin.register(AnalysisStage)
class AnalysisStageAdmin(admin.ModelAdmin):
    list_display = ("id", "analysis_run", "stage_order", "stage_code", "model_version", "status", "confidence")
    list_filter = ("stage_code", "status", "model_version")
    search_fields = ("stage_code", "stage_name", "analysis_run__inspection__id")
    readonly_fields = ("created_at",)
    inlines = [DetectionInline]


@admin.register(Detection)
class DetectionAdmin(admin.ModelAdmin):
    list_display = ("id", "analysis_stage", "class_name", "confidence", "area_px", "created_at")
    list_filter = ("class_name", "analysis_stage__stage_code")
    search_fields = ("class_name", "analysis_stage__analysis_run__inspection__id")
    readonly_fields = ("created_at",)
