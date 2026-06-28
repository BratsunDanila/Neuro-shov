package com.weldingdefect

import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.os.Bundle
import android.view.View
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.WindowCompat
import com.google.android.material.button.MaterialButton
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter

class HistoryActivity : AppCompatActivity() {
    private lateinit var store: LocalReportStore
    private lateinit var reportsContainer: LinearLayout
    private lateinit var tvEmpty: TextView
    private lateinit var btnRetryAll: MaterialButton

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        configureSystemBars()
        setContentView(R.layout.activity_history)

        store = LocalReportStore(this)
        reportsContainer = findViewById(R.id.reportsContainer)
        tvEmpty = findViewById(R.id.tvHistoryEmpty)
        btnRetryAll = findViewById(R.id.btnRetryAll)

        findViewById<MaterialButton>(R.id.btnHistoryBack).setOnClickListener { finish() }
        btnRetryAll.setOnClickListener { retryPendingReports() }
        renderReports()
    }

    private fun renderReports() {
        val reports = store.listReports()
        reportsContainer.removeAllViews()
        tvEmpty.visibility = if (reports.isEmpty()) View.VISIBLE else View.GONE
        btnRetryAll.isEnabled = reports.any { it.status != LocalReportStore.STATUS_SENT }

        reports.forEach { report -> reportsContainer.addView(createReportCard(report)) }
    }

    private fun createReportCard(report: LocalReport): View {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(14), dp(14), dp(14))
            setBackgroundColor(Color.WHITE)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(0, 0, 0, dp(12)) }
        }

        decodeThumbnail(report.annotatedImagePath ?: report.originalImagePath)?.let { bitmap ->
            card.addView(ImageView(this).apply {
                setImageBitmap(bitmap)
                adjustViewBounds = true
                scaleType = ImageView.ScaleType.CENTER_CROP
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    dp(180)
                )
            })
        }

        card.addView(TextView(this).apply {
            text = statusText(report)
            setTextColor(statusColor(report.status))
            textSize = 16f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setPadding(0, dp(10), 0, dp(2))
        })
        card.addView(TextView(this).apply {
            text = "Съемка: ${formatCapturedAt(report.capturedAtIso)}\nОбнаружения: ${report.detectionsCount}"
            setTextColor(Color.rgb(31, 41, 55))
            textSize = 14f
        })
        if (!report.errorMessage.isNullOrBlank()) {
            card.addView(TextView(this).apply {
                text = report.errorMessage
                setTextColor(Color.rgb(127, 29, 29))
                textSize = 13f
                setPadding(0, dp(6), 0, 0)
            })
        }

        if (report.status != LocalReportStore.STATUS_SENT) {
            card.addView(MaterialButton(this).apply {
                text = getString(R.string.retry_send)
                isAllCaps = false
                setTextColor(Color.WHITE)
                setPadding(0, dp(4), 0, dp(4))
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    dp(48)
                ).apply { setMargins(0, dp(10), 0, 0) }
                setOnClickListener { retryReport(report.id) }
            })
        }

        return card
    }

    private fun retryPendingReports() {
        val ids = store.listReports()
            .filter { it.status != LocalReportStore.STATUS_SENT }
            .map { it.id }
        if (ids.isEmpty()) return
        retryNext(ids, 0)
    }

    private fun retryNext(ids: List<String>, index: Int) {
        if (index >= ids.size) {
            renderReports()
            return
        }
        retryReport(ids[index]) { retryNext(ids, index + 1) }
    }

    private fun retryReport(reportId: String, onDone: (() -> Unit)? = null) {
        val report = store.getReport(reportId) ?: return
        setRetryEnabled(false)
        Thread {
            try {
                val originalBitmap = BitmapFactory.decodeFile(report.originalImagePath)
                    ?: throw IllegalStateException("Не удалось прочитать исходное фото")
                val annotatedBitmap = report.annotatedImagePath?.let { BitmapFactory.decodeFile(it) }
                val storage = AuthStorage(this)
                val accessToken = storage.accessToken
                    ?: throw ApiAuthException("Сессия истекла. Войдите снова.")

                val inspectionId = ApiClient().uploadInspection(
                    baseUrl = storage.baseUrl,
                    accessToken = accessToken,
                    bitmap = originalBitmap,
                    annotatedBitmap = annotatedBitmap,
                    capturedAtIso = report.capturedAtIso,
                    analysisJson = JSONObject(report.analysisJson),
                    appVersion = report.appVersion,
                    deviceId = report.deviceId,
                    deviceInfoJson = JSONObject(report.deviceInfoJson),
                    location = report.toLocation()
                )
                store.updateStatus(report.id, LocalReportStore.STATUS_SENT, inspectionId, null)
                runOnUiThread {
                    Toast.makeText(this, R.string.status_uploaded, Toast.LENGTH_SHORT).show()
                    setRetryEnabled(true)
                    renderReports()
                    onDone?.invoke()
                }
            } catch (e: ApiAuthException) {
                runOnUiThread { clearAuthAndOpenLogin(e.message) }
            } catch (e: ApiHttpException) {
                store.updateStatus(report.id, LocalReportStore.STATUS_ERROR, null, e.message)
                runOnUiThread {
                    Toast.makeText(this, R.string.status_upload_error, Toast.LENGTH_SHORT).show()
                    setRetryEnabled(true)
                    renderReports()
                    onDone?.invoke()
                }
            } catch (e: IOException) {
                store.updateStatus(report.id, LocalReportStore.STATUS_PENDING, null, e.message)
                runOnUiThread {
                    Toast.makeText(this, R.string.status_saved_for_retry, Toast.LENGTH_SHORT).show()
                    setRetryEnabled(true)
                    renderReports()
                    onDone?.invoke()
                }
            } catch (e: Exception) {
                store.updateStatus(report.id, LocalReportStore.STATUS_ERROR, null, e.message)
                runOnUiThread {
                    Toast.makeText(this, R.string.status_upload_error, Toast.LENGTH_SHORT).show()
                    setRetryEnabled(true)
                    renderReports()
                    onDone?.invoke()
                }
            }
        }.start()
    }

    private fun setRetryEnabled(enabled: Boolean) {
        btnRetryAll.isEnabled = enabled
        for (index in 0 until reportsContainer.childCount) {
            reportsContainer.getChildAt(index).isEnabled = enabled
        }
    }

    private fun clearAuthAndOpenLogin(message: String?) {
        AuthStorage(this).clear()
        if (!message.isNullOrBlank()) Toast.makeText(this, message, Toast.LENGTH_LONG).show()
        startActivity(
            Intent(this, LoginActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
        )
        finish()
    }

    private fun statusText(report: LocalReport): String {
        return when (report.status) {
            LocalReportStore.STATUS_SENT -> {
                if (report.inspectionId != null && report.inspectionId > 0) {
                    "Отправлен #${report.inspectionId}"
                } else {
                    "Отправлен"
                }
            }
            LocalReportStore.STATUS_ERROR -> "Ошибка отправки"
            else -> "Ожидает отправки"
        }
    }

    private fun statusColor(status: String): Int {
        return when (status) {
            LocalReportStore.STATUS_SENT -> Color.rgb(22, 101, 52)
            LocalReportStore.STATUS_ERROR -> Color.rgb(153, 27, 27)
            else -> Color.rgb(146, 64, 14)
        }
    }

    private fun LocalReport.toLocation(): ReportLocation? {
        val lat = latitude ?: return null
        val lon = longitude ?: return null
        return ReportLocation(lat, lon, accuracyMeters)
    }

    private fun decodeThumbnail(path: String): Bitmap? {
        if (!File(path).exists()) return null
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(path, bounds)
        val maxSize = 600
        var sampleSize = 1
        while (bounds.outWidth / sampleSize > maxSize || bounds.outHeight / sampleSize > maxSize) {
            sampleSize *= 2
        }
        return BitmapFactory.decodeFile(path, BitmapFactory.Options().apply { inSampleSize = sampleSize })
    }

    private fun formatCapturedAt(value: String): String {
        if (value.isBlank()) return "-"
        return try {
            OffsetDateTime.parse(value).format(DateTimeFormatter.ofPattern("dd.MM.yyyy HH:mm"))
        } catch (_: Exception) {
            value
        }
    }

    private fun configureSystemBars() {
        window.statusBarColor = Color.rgb(246, 247, 249)
        window.navigationBarColor = Color.rgb(246, 247, 249)
        WindowCompat.getInsetsController(window, window.decorView).apply {
            isAppearanceLightStatusBars = true
            isAppearanceLightNavigationBars = true
        }
    }

    private fun dp(value: Int): Int {
        return (value * resources.displayMetrics.density).toInt()
    }
}
