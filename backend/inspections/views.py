from django.db.models import Prefetch
from rest_framework import mixins, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated

from accounts.models import UserRole

from .models import AnalysisRun, AnalysisStage, Inspection
from .serializers import InspectionCreateSerializer, InspectionSerializer


class InspectionViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.action == "create":
            return InspectionCreateSerializer
        return InspectionSerializer

    def get_queryset(self):
        queryset = (
            Inspection.objects.select_related("organization", "worker", "site", "area")
            .prefetch_related(
                Prefetch(
                    "analysis_runs",
                    queryset=AnalysisRun.objects.prefetch_related(
                        Prefetch(
                            "stages",
                            queryset=AnalysisStage.objects.select_related("model_version", "model_version__model")
                            .prefetch_related("detections"),
                        )
                    ),
                )
            )
        )
        user = self.request.user
        if user.is_superuser:
            return queryset
        if user.role in {UserRole.ORG_ADMIN, UserRole.CONTROLLER}:
            return queryset.filter(organization=user.organization)
        return queryset.filter(worker=user)
