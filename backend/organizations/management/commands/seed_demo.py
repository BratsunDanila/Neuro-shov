from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import UserRole
from ml.models import MlModel, MlModelVersion, MlTaskType
from organizations.models import Area, Organization, Site


class Command(BaseCommand):
    help = "Create demo organization, users, site, area, and ML model metadata."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="demo12345", help="Password for created demo users.")

    @transaction.atomic
    def handle(self, *args, **options):
        password = options["password"]
        user_model = get_user_model()

        organization, _ = Organization.objects.get_or_create(
            name="Демо предприятие сварочного контроля",
            defaults={"short_name": "Демо сварка", "inn": "0000000000"},
        )
        site, _ = Site.objects.get_or_create(
            organization=organization,
            name="Цех 1",
            defaults={"address": "Тестовая площадка"},
        )
        area, _ = Area.objects.get_or_create(
            site=site,
            name="Пост сварки A",
            defaults={"description": "Демо-участок для проверки мобильного приложения"},
        )

        superadmin_user = self._upsert_user(
            user_model=user_model,
            username="demo_superadmin",
            password=password,
            organization=None,
            role=UserRole.SUPERADMIN,
            first_name="Системный",
            last_name="Администратор",
            employee_number="SYS-001",
            is_staff=True,
            is_superuser=True,
        )
        admin_user = self._upsert_user(
            user_model=user_model,
            username="demo_admin",
            password=password,
            organization=organization,
            role=UserRole.ORG_ADMIN,
            first_name="Иван",
            last_name="Администратор",
            employee_number="ADM-001",
            is_staff=True,
            is_superuser=False,
        )
        worker_user = self._upsert_user(
            user_model=user_model,
            username="demo_worker",
            password=password,
            organization=organization,
            role=UserRole.WORKER,
            first_name="Петр",
            last_name="Сварщик",
            employee_number="WRK-001",
            position="Сварщик",
            is_staff=False,
            is_superuser=False,
        )

        defect_model, _ = MlModel.objects.get_or_create(
            code="defect_segmentation",
            defaults={
                "name": "Сегментация дефектов сварного шва",
                "task_type": MlTaskType.SEGMENTATION,
                "description": "YOLO segmentation model for welding defect masks.",
            },
        )
        MlModelVersion.objects.get_or_create(
            model=defect_model,
            version="yolo26s-clean-ft40-tflite",
            defaults={
                "format": "tflite",
                "input_size": "640",
                "classes_json": {
                    "0": "Bad Welding",
                    "1": "Crack",
                    "2": "Excess Reinforcement",
                    "3": "Good Welding",
                    "4": "Porosity",
                    "5": "Spatters",
                },
                "metadata_json": {"pipeline_stage": "defect_segmentation"},
            },
        )

        self.stdout.write(self.style.SUCCESS("Demo data created/updated."))
        self.stdout.write(f"Organization: {organization}")
        self.stdout.write(f"Site: {site.name}; Area: {area.name}")
        self.stdout.write(f"Superadmin: {superadmin_user.username} / {password}")
        self.stdout.write(f"Admin: {admin_user.username} / {password}")
        self.stdout.write(f"Worker: {worker_user.username} / {password}")

    def _upsert_user(
        self,
        user_model,
        username,
        password,
        organization,
        role,
        first_name,
        last_name,
        employee_number,
        is_staff,
        is_superuser,
        position="",
    ):
        user, _ = user_model.objects.get_or_create(username=username)
        user.organization = organization
        user.role = role
        user.first_name = first_name
        user.last_name = last_name
        user.employee_number = employee_number
        user.position = position
        user.is_staff = is_staff
        user.is_superuser = is_superuser
        user.is_active = True
        user.must_change_password = False
        user.set_password(password)
        user.save()
        return user
