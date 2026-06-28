# Welding Control Backend

Django backend for welding inspection reports, user accounts, organizations, and flexible ML analysis pipelines.

## Stack

- Django + Django REST Framework
- PostgreSQL
- JWT auth via SimpleJWT
- Local media in development
- MinIO/S3-compatible storage planned via `django-storages`

## Quick Start

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

For a quick local check without PostgreSQL, set `DB_ENGINE=sqlite` in `.env`.

## Demo Data

For local UI/API checks, create demo data:

```powershell
python manage.py seed_demo
```

This creates:

- organization: `Демо предприятие сварочного контроля`
- site: `Цех 1`
- area: `Пост сварки A`
- superadmin user: `demo_superadmin / demo12345`
- admin user: `demo_admin / demo12345`
- worker user: `demo_worker / demo12345`
- model version: `yolo26s-clean-ft40-tflite`

Use `demo_superadmin` for Django Admin during development. `demo_admin` is an organization admin account for future role-scoped admin/API flows.

## Android Login During Development

For the Android emulator, use this server URL on the login screen:

```text
http://10.0.2.2:8000/
```

For a real phone on the same Wi-Fi network:

1. Set `DJANGO_ALLOWED_HOSTS=*` in `.env` for local development.
2. Run Django on all interfaces:

```powershell
python manage.py runserver 0.0.0.0:8000
```

3. Find the PC LAN IP, for example `192.168.1.25`.
4. Use this URL in Android:

```text
http://192.168.1.25:8000/
```

If the phone cannot connect, check Windows Firewall for Python/Django.

## Mobile Report Upload Test

After Android login, take a photo and run analysis. The app uploads the report automatically to:

```text
POST /api/inspections/
```

In Django Admin, uploaded reports appear at:

```text
/admin/inspections/inspection/
```

The mobile app runs segmentation locally on-device, then uploads the original image, annotated image, GPS coordinates when available, and pipeline JSON.

## Architecture Note

Inspections are not tied to one fixed model. Results are stored as analysis runs and stages:

- `Inspection` stores the fact of a worker photo/report.
- `AnalysisRun` stores one execution of an analysis pipeline.
- `AnalysisStage` stores one model/stage result in that pipeline.
- `Detection` stores defects produced by a specific stage.
- `MlModel` and `MlModelVersion` track model identity and versions.

This allows replacing the current model or adding more models later without redesigning reports.

## MVP API

- `POST /api/auth/login/` - JWT login.
- `POST /api/auth/refresh/` - refresh JWT token.
- `GET /api/me/` - current user profile.
- `GET /api/sites/` - active sites for the user's organization.
- `GET /api/areas/?site=<id>` - active areas.
- `GET /api/inspections/` - inspection list scoped by role.
- `GET /api/inspections/<id>/` - inspection details.
- `POST /api/inspections/` - upload one mobile inspection report.

`POST /api/inspections/` accepts multipart form data:

- `original_image` - required image file.
- `annotated_image` - optional image with masks.
- `captured_at` - ISO datetime.
- `latitude`, `longitude`, `location_accuracy_m` - optional location.
- `site_id`, `area_id` - optional organization-scoped identifiers.
- `app_version`, `device_id`, `device_info_json` - optional client metadata.
- `analysis_json` - pipeline result JSON.

Example `analysis_json`:

```json
{
  "pipeline_code": "mobile_welding_analysis",
  "pipeline_version": "1.0.0",
  "source": "mobile",
  "status": "success",
  "summary": { "detections_count": 2 },
  "stages": [
    {
      "stage_code": "defect_segmentation",
      "stage_name": "Сегментация дефектов",
      "stage_order": 1,
      "model_version": "yolo26s-clean-ft40-tflite",
      "status": "success",
      "result": { "detections_count": 2 },
      "detections": [
        {
          "class_id": 4,
          "class_name": "Porosity",
          "confidence": 0.86,
          "bbox": [10, 20, 100, 150],
          "area_px": 1234
        }
      ]
    }
  ]
}
```
