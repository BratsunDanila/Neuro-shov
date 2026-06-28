package com.weldingdefect

import android.graphics.Bitmap
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.util.Locale
import java.util.concurrent.TimeUnit

data class AuthTokens(
    val access: String,
    val refresh: String
)

data class UserProfile(
    val id: Long,
    val username: String,
    val fullName: String,
    val organizationName: String,
    val role: String
)

class ApiAuthException(message: String) : IOException(message)
class ApiHttpException(message: String, val code: Int) : IOException(message)

class ApiClient {
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    fun login(baseUrl: String, username: String, password: String): AuthTokens {
        val url = AuthStorage.normalizeBaseUrl(baseUrl) + "api/auth/login/"
        val payload = JSONObject()
            .put("username", username)
            .put("password", password)
            .toString()
        val request = Request.Builder()
            .url(url)
            .post(payload.toRequestBody(JSON_MEDIA_TYPE))
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiHttpException(readError(body, "Ошибка входа: ${response.code}"), response.code)
            }
            val json = JSONObject(body)
            return AuthTokens(
                access = json.getString("access"),
                refresh = json.getString("refresh")
            )
        }
    }

    fun me(baseUrl: String, accessToken: String): UserProfile {
        val url = AuthStorage.normalizeBaseUrl(baseUrl) + "api/me/"
        val request = Request.Builder()
            .url(url)
            .header("Authorization", "Bearer $accessToken")
            .get()
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                if (response.code == 401 || response.code == 403) {
                    throw ApiAuthException("Сессия истекла. Войдите снова.")
                }
                throw ApiHttpException(readError(body, "Не удалось получить профиль: ${response.code}"), response.code)
            }
            val json = JSONObject(body)
            return UserProfile(
                id = json.optLong("id"),
                username = json.optString("username"),
                fullName = json.optString("full_name", json.optString("username")),
                organizationName = json.optString("organization_name"),
                role = json.optString("role")
            )
        }
    }

    fun uploadInspection(
        baseUrl: String,
        accessToken: String,
        bitmap: Bitmap,
        annotatedBitmap: Bitmap?,
        capturedAtIso: String,
        analysisJson: JSONObject,
        appVersion: String,
        deviceId: String,
        deviceInfoJson: JSONObject,
        location: ReportLocation?
    ): Long {
        val imageBytes = ByteArrayOutputStream().use { stream ->
            bitmap.compress(Bitmap.CompressFormat.JPEG, 92, stream)
            stream.toByteArray()
        }

        val bodyBuilder = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("captured_at", capturedAtIso)
            .addFormDataPart("app_version", appVersion)
            .addFormDataPart("device_id", deviceId)
            .addFormDataPart("device_info_json", deviceInfoJson.toString())
            .addFormDataPart("analysis_json", analysisJson.toString())
            .addFormDataPart(
                "original_image",
                "welding_${System.currentTimeMillis()}.jpg",
                imageBytes.toRequestBody(JPEG_MEDIA_TYPE)
            )

        if (location != null) {
            bodyBuilder
                .addFormDataPart("latitude", formatCoordinate(location.latitude))
                .addFormDataPart("longitude", formatCoordinate(location.longitude))
            if (location.accuracyMeters != null) {
                bodyBuilder.addFormDataPart(
                    "location_accuracy_m",
                    String.format(Locale.US, "%.2f", location.accuracyMeters)
                )
            }
        }

        if (annotatedBitmap != null) {
            val annotatedBytes = ByteArrayOutputStream().use { stream ->
                annotatedBitmap.compress(Bitmap.CompressFormat.JPEG, 92, stream)
                stream.toByteArray()
            }
            bodyBuilder.addFormDataPart(
                "annotated_image",
                "welding_result_${System.currentTimeMillis()}.jpg",
                annotatedBytes.toRequestBody(JPEG_MEDIA_TYPE)
            )
        }

        val body = bodyBuilder.build()

        val request = Request.Builder()
            .url(AuthStorage.normalizeBaseUrl(baseUrl) + "api/inspections/")
            .header("Authorization", "Bearer $accessToken")
            .post(body)
            .build()

        client.newCall(request).execute().use { response ->
            val responseBody = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                if (response.code == 401 || response.code == 403) {
                    throw ApiAuthException("Сессия истекла. Войдите снова.")
                }
                throw ApiHttpException(readError(responseBody, "Не удалось отправить отчет: ${response.code}"), response.code)
            }
            return JSONObject(responseBody).optLong("id", -1L)
        }
    }

    private fun readError(body: String, fallback: String): String {
        if (body.isBlank()) return fallback
        return try {
            val json = JSONObject(body)
            when {
                json.has("detail") -> json.getString("detail")
                json.has("non_field_errors") -> json.getJSONArray("non_field_errors").join(", ")
                else -> json.keys().asSequence().joinToString("; ") { key ->
                    "$key: ${json.opt(key)}"
                }.ifBlank { fallback }
            }
        } catch (_: Exception) {
            fallback
        }
    }

    private fun formatCoordinate(value: Double): String {
        return String.format(Locale.US, "%.6f", value)
    }

    companion object {
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
        private val JPEG_MEDIA_TYPE = "image/jpeg".toMediaType()
    }
}
