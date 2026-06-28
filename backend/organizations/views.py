from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Area, Site
from .serializers import AreaSerializer, SiteSerializer


class OrganizationScopedMixin:
    permission_classes = [IsAuthenticated]

    def get_organization(self):
        user = self.request.user
        return None if user.is_superuser else user.organization


class SiteViewSet(OrganizationScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = SiteSerializer

    def get_queryset(self):
        queryset = Site.objects.filter(is_active=True).select_related("organization")
        organization = self.get_organization()
        if organization is not None:
            queryset = queryset.filter(organization=organization)
        return queryset


class AreaViewSet(OrganizationScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = AreaSerializer

    def get_queryset(self):
        queryset = Area.objects.filter(is_active=True).select_related("site", "site__organization")
        organization = self.get_organization()
        if organization is not None:
            queryset = queryset.filter(site__organization=organization)
        site_id = self.request.query_params.get("site")
        if site_id:
            queryset = queryset.filter(site_id=site_id)
        return queryset
