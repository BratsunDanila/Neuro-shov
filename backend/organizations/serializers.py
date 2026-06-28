from rest_framework import serializers

from .models import Area, Site


class SiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Site
        fields = ("id", "name", "address", "is_active")
        read_only_fields = fields


class AreaSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source="site.name", read_only=True)

    class Meta:
        model = Area
        fields = ("id", "site", "site_name", "name", "description", "is_active")
        read_only_fields = fields
