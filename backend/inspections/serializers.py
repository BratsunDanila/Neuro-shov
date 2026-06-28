import json
from typing import Any

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.models import UserRole
from ml.models import MlModelVersion
from organizations.models import Area, Site

from .models import (
    AnalysisRun,
    AnalysisSource,
    AnalysisStage,
    AnalysisStatus,
    Detection,
    Inspection,
    InspectionStatus,
)


def parse_json_value(value: Any, default: Any):
    if value in (None, ""):
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise serializers.ValidationError(f"Invalid JSON: {exc}") from exc
    return value


class DetectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Detection
        fields = (
            "id",
            "class_id",
            "class_name",
            "confidence",
            "bbox_json",
            "mask_json",
            "area_px",
            "metadata_json",
        )
        read_only_fields = fields


class AnalysisStageSerializer(serializers.ModelSerializer):
    detections = DetectionSerializer(many=True, read_only=True)
    model_version_label = serializers.SerializerMethodField()

    class Meta:
        model = AnalysisStage
        fields = (
            "id",
            "stage_code",
            "stage_name",
            "stage_order",
            "model_version",
            "model_version_label",
            "status",
            "confidence",
            "result_json",
            "latency_ms",
            "detections",
        )
        read_only_fields = fields

    def get_model_version_label(self, obj):
        return str(obj.model_version) if obj.model_version else ""


class AnalysisRunSerializer(serializers.ModelSerializer):
    stages = AnalysisStageSerializer(many=True, read_only=True)

    class Meta:
        model = AnalysisRun
        fields = (
            "id",
            "pipeline_code",
            "pipeline_version",
            "source",
            "status",
            "started_at",
            "finished_at",
            "latency_ms",
            "summary_json",
            "stages",
        )
        read_only_fields = fields


class InspectionSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source="worker.full_name_with_middle", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    site_name = serializers.CharField(source="site.name", read_only=True)
    area_name = serializers.CharField(source="area.name", read_only=True)
    analysis_runs = AnalysisRunSerializer(many=True, read_only=True)

    class Meta:
        model = Inspection
        fields = (
            "id",
            "organization",
            "organization_name",
            "worker",
            "worker_name",
            "site",
            "site_name",
            "area",
            "area_name",
            "captured_at",
            "uploaded_at",
            "original_image",
            "annotated_image",
            "latitude",
            "longitude",
            "location_accuracy_m",
            "status",
            "summary_json",
            "app_version",
            "device_id",
            "device_info_json",
            "comment",
            "analysis_runs",
            "created_at",
        )
        read_only_fields = fields


class InspectionCreateSerializer(serializers.ModelSerializer):
    site_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    area_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    analysis_json = serializers.JSONField(required=False, write_only=True)
    device_info_json = serializers.JSONField(required=False)

    class Meta:
        model = Inspection
        fields = (
            "id",
            "site_id",
            "area_id",
            "captured_at",
            "original_image",
            "annotated_image",
            "latitude",
            "longitude",
            "location_accuracy_m",
            "app_version",
            "device_id",
            "device_info_json",
            "comment",
            "analysis_json",
        )
        read_only_fields = ("id",)

    def validate(self, attrs):
        request = self.context["request"]
        if not request.user.organization and not request.user.is_superuser:
            raise serializers.ValidationError("User is not attached to an organization.")

        attrs["device_info_json"] = parse_json_value(attrs.get("device_info_json"), {})
        attrs["analysis_json"] = parse_json_value(attrs.get("analysis_json"), {})

        site_id = attrs.get("site_id")
        area_id = attrs.get("area_id")
        organization = request.user.organization
        if site_id and organization and not Site.objects.filter(id=site_id, organization=organization).exists():
            raise serializers.ValidationError({"site_id": "Site does not belong to user's organization."})
        if area_id and organization and not Area.objects.filter(id=area_id, site__organization=organization).exists():
            raise serializers.ValidationError({"area_id": "Area does not belong to user's organization."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        user = request.user
        analysis_data = validated_data.pop("analysis_json", {})
        site_id = validated_data.pop("site_id", None)
        area_id = validated_data.pop("area_id", None)

        organization = user.organization
        if organization is None:
            raise serializers.ValidationError("Superuser uploads must be implemented with explicit organization_id.")

        inspection = Inspection.objects.create(
            organization=organization,
            worker=user,
            site_id=site_id,
            area_id=area_id,
            uploaded_at=timezone.now(),
            status=InspectionStatus.ANALYZED if analysis_data else InspectionStatus.UPLOADED,
            worker_snapshot_json={
                "id": user.id,
                "username": user.username,
                "full_name": user.full_name_with_middle,
                "role": user.role,
                "employee_number": user.employee_number,
                "position": user.position,
            },
            summary_json=analysis_data.get("summary", {}) if isinstance(analysis_data, dict) else {},
            **validated_data,
        )

        if analysis_data:
            self._create_analysis(inspection, analysis_data)

        return inspection

    def _create_analysis(self, inspection: Inspection, analysis_data: dict):
        run = AnalysisRun.objects.create(
            inspection=inspection,
            pipeline_code=analysis_data.get("pipeline_code", "mobile_welding_analysis"),
            pipeline_version=analysis_data.get("pipeline_version", "1.0.0"),
            source=analysis_data.get("source", AnalysisSource.MOBILE),
            status=analysis_data.get("status", AnalysisStatus.SUCCESS),
            started_at=analysis_data.get("started_at"),
            finished_at=analysis_data.get("finished_at"),
            latency_ms=analysis_data.get("latency_ms"),
            summary_json=analysis_data.get("summary", {}),
        )

        for index, stage_data in enumerate(analysis_data.get("stages", []), start=1):
            stage = AnalysisStage.objects.create(
                analysis_run=run,
                stage_code=stage_data.get("stage_code", f"stage_{index}"),
                stage_name=stage_data.get("stage_name", ""),
                stage_order=stage_data.get("stage_order", index),
                model_version=self._resolve_model_version(stage_data),
                status=stage_data.get("status", AnalysisStatus.SUCCESS),
                confidence=stage_data.get("confidence"),
                result_json=stage_data.get("result", {}),
                latency_ms=stage_data.get("latency_ms"),
            )
            for detection_data in stage_data.get("detections", []):
                Detection.objects.create(
                    analysis_stage=stage,
                    class_id=detection_data.get("class_id", -1),
                    class_name=detection_data.get("class_name", "unknown"),
                    confidence=detection_data.get("confidence", 0.0),
                    bbox_json=detection_data.get("bbox", detection_data.get("bbox_json", [])),
                    mask_json=detection_data.get("mask", detection_data.get("mask_json", {})),
                    area_px=detection_data.get("area_px"),
                    metadata_json=detection_data.get("metadata", {}),
                )

    def _resolve_model_version(self, stage_data: dict):
        model_version_id = stage_data.get("model_version_id")
        if model_version_id:
            return MlModelVersion.objects.filter(id=model_version_id).first()

        version = stage_data.get("model_version")
        if not version:
            return None
        return MlModelVersion.objects.filter(version=version).first()
