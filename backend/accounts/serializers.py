from rest_framework import serializers

from .models import User


class UserMeSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="full_name_with_middle", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "middle_name",
            "full_name",
            "organization",
            "organization_name",
            "role",
            "position",
            "employee_number",
            "phone",
            "must_change_password",
        )
        read_only_fields = fields
