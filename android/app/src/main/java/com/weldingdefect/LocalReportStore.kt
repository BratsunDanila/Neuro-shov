package com.weldingdefect

import android.content.Context
import android.graphics.Bitmap
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

data class LocalReport(
    val id: String,
    val capturedAtIso: String,
    val createdAtMillis: Long,
    val updatedAtMillis: Long,
    val status: String,
    val detectionsCount: Int,
    val inspectionId: Long?,
    val originalImagePath: String,
    val annotatedImagePath: String?,
    val analysisJson: String,
    val appVersion: String,
    val deviceId: String,
    val deviceInfoJson: String,
    val latitude: Double?,
    val longitude: Double?,
    val accuracyMeters: Float?,
    val errorMessage: String?
)

class LocalReportStore(private val context: Context) {
    private val prefs = context.getSharedPreferences("local_reports", Context.MODE_PRIVATE)

    fun saveReport(
        bitmap: Bitmap,
        annotatedBitmap: Bitmap?,
        capturedAtIso: String,
        analysisJson: JSONObject,
        appVersion: String,
        deviceId: String,
        deviceInfoJson: JSONObject,
        location: ReportLocation?,
        detectionsCount: Int,
        status: String,
        inspectionId: Long?,
        errorMessage: String?
    ): LocalReport {
        val now = System.currentTimeMillis()
        val id = now.toString()
        val reportDir = File(context.filesDir, "report_history/$id").apply { mkdirs() }
        val originalFile = File(reportDir, "original.jpg")
        val annotatedFile = if (annotatedBitmap != null) File(reportDir, "annotated.jpg") else null

        originalFile.outputStream().use { stream ->
            bitmap.compress(Bitmap.CompressFormat.JPEG, 92, stream)
        }
        if (annotatedBitmap != null && annotatedFile != null) {
            annotatedFile.outputStream().use { stream ->
                annotatedBitmap.compress(Bitmap.CompressFormat.JPEG, 92, stream)
            }
        }

        val json = JSONObject()
            .put("id", id)
            .put("captured_at_iso", capturedAtIso)
            .put("created_at_millis", now)
            .put("updated_at_millis", now)
            .put("status", status)
            .put("detections_count", detectionsCount)
            .put("inspection_id", inspectionId ?: JSONObject.NULL)
            .put("original_image_path", originalFile.absolutePath)
            .put("annotated_image_path", annotatedFile?.absolutePath ?: JSONObject.NULL)
            .put("analysis_json", analysisJson.toString())
            .put("app_version", appVersion)
            .put("device_id", deviceId)
            .put("device_info_json", deviceInfoJson.toString())
            .put("latitude", location?.latitude ?: JSONObject.NULL)
            .put("longitude", location?.longitude ?: JSONObject.NULL)
            .put("accuracy_meters", location?.accuracyMeters ?: JSONObject.NULL)
            .put("error_message", errorMessage ?: JSONObject.NULL)

        val reports = readArray()
        reports.put(json)
        writeArray(reports)
        return json.toLocalReport()
    }

    fun listReports(): List<LocalReport> {
        val reports = readArray()
        return (0 until reports.length())
            .mapNotNull { index -> reports.optJSONObject(index)?.toLocalReport() }
            .sortedByDescending { it.createdAtMillis }
    }

    fun getReport(id: String): LocalReport? {
        return listReports().firstOrNull { it.id == id }
    }

    fun updateStatus(id: String, status: String, inspectionId: Long?, errorMessage: String?) {
        val reports = readArray()
        for (index in 0 until reports.length()) {
            val report = reports.optJSONObject(index) ?: continue
            if (report.optString("id") == id) {
                report
                    .put("status", status)
                    .put("inspection_id", inspectionId ?: JSONObject.NULL)
                    .put("error_message", errorMessage ?: JSONObject.NULL)
                    .put("updated_at_millis", System.currentTimeMillis())
                break
            }
        }
        writeArray(reports)
    }

    private fun readArray(): JSONArray {
        val raw = prefs.getString(KEY_REPORTS, "[]") ?: "[]"
        return try {
            JSONArray(raw)
        } catch (_: Exception) {
            JSONArray()
        }
    }

    private fun writeArray(array: JSONArray) {
        prefs.edit().putString(KEY_REPORTS, array.toString()).apply()
    }

    private fun JSONObject.toLocalReport(): LocalReport {
        return LocalReport(
            id = getString("id"),
            capturedAtIso = optString("captured_at_iso"),
            createdAtMillis = optLong("created_at_millis"),
            updatedAtMillis = optLong("updated_at_millis"),
            status = optString("status", STATUS_PENDING),
            detectionsCount = optInt("detections_count"),
            inspectionId = optNullableLong("inspection_id"),
            originalImagePath = optString("original_image_path"),
            annotatedImagePath = optNullableString("annotated_image_path"),
            analysisJson = optString("analysis_json", "{}"),
            appVersion = optString("app_version"),
            deviceId = optString("device_id"),
            deviceInfoJson = optString("device_info_json", "{}"),
            latitude = optNullableDouble("latitude"),
            longitude = optNullableDouble("longitude"),
            accuracyMeters = optNullableDouble("accuracy_meters")?.toFloat(),
            errorMessage = optNullableString("error_message")
        )
    }

    private fun JSONObject.optNullableString(key: String): String? {
        return if (has(key) && !isNull(key)) optString(key) else null
    }

    private fun JSONObject.optNullableLong(key: String): Long? {
        return if (has(key) && !isNull(key)) optLong(key) else null
    }

    private fun JSONObject.optNullableDouble(key: String): Double? {
        return if (has(key) && !isNull(key)) optDouble(key) else null
    }

    companion object {
        const val STATUS_SENT = "sent"
        const val STATUS_PENDING = "pending"
        const val STATUS_ERROR = "error"
        private const val KEY_REPORTS = "reports"
    }
}
