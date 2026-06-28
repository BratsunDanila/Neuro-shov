package com.weldingdefect

import android.annotation.SuppressLint
import android.Manifest
import android.content.pm.PackageManager
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Matrix
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.ScaleGestureDetector
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.core.TorchState
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import androidx.exifinterface.media.ExifInterface
import com.google.android.material.button.MaterialButton
import com.weldingdefect.YoloSegmenter.SegmentationResult
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {

    private lateinit var segmenter: YoloSegmenter
    private lateinit var previewView: PreviewView
    private lateinit var maskOverlay: MaskOverlayView
    private lateinit var resultPanel: View
    private lateinit var tvStatus: TextView
    private lateinit var tvDetails: TextView
    private lateinit var tvZoom: TextView
    private lateinit var tvResultHeadline: TextView
    private lateinit var captureButtonContainer: View
    private lateinit var btnClose: MaterialButton
    private lateinit var btnTorch: MaterialButton
    private lateinit var btnRun: MaterialButton
    private lateinit var btnTakePhoto: MaterialButton
    private lateinit var btnPickGallery: MaterialButton

    private var cameraProvider: ProcessCameraProvider? = null
    private var camera: Camera? = null
    private var imageCapture: ImageCapture? = null
    private var cameraExecutor: ExecutorService = Executors.newSingleThreadExecutor()
    private var currentBitmap: Bitmap? = null
    private var currentCapturedAtIso: String = nowIso()
    private var isCameraActive = false
    private var currentZoomRatio = 1f
    private var minZoomRatio = 1f
    private var maxZoomRatio = 1f
    private var isTorchOn = false
    private var isShowingResult = false
    private var isResultExpanded = false
    private var currentResult: SegmentationResult? = null
    private var currentLocalReportId: String? = null
    private var isUploadInProgress = false
    private var isReportSent = false
    private var resultCollapsedText = ""
    private var resultExpandedText = ""
    private lateinit var zoomGestureDetector: ScaleGestureDetector

    private val galleryLauncher = registerForActivityResult(
        ActivityResultContracts.PickVisualMedia()
    ) { uri: Uri? ->
        if (uri != null) loadImageFromUri(uri) else startCamera()
    }

    private val cameraPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            requestLocationPermissionIfNeeded()
            startCamera()
        }
        else Toast.makeText(this, R.string.camera_permission_required, Toast.LENGTH_SHORT).show()
    }

    private val locationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { }

    @SuppressLint("ClickableViewAccessibility")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!AuthStorage(this).isLoggedIn()) {
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
            return
        }
        configureSystemBars()
        setContentView(R.layout.activity_main)

        previewView = findViewById(R.id.previewView)
        maskOverlay = findViewById(R.id.maskOverlay)
        resultPanel = findViewById(R.id.resultPanel)
        tvStatus = findViewById(R.id.tvStatus)
        tvDetails = findViewById(R.id.tvDetails)
        tvZoom = findViewById(R.id.tvZoom)
        tvResultHeadline = findViewById(R.id.tvResultHeadline)
        captureButtonContainer = findViewById(R.id.captureButtonContainer)
        btnClose = findViewById(R.id.btnClose)
        btnTorch = findViewById(R.id.btnTorch)
        btnRun = findViewById(R.id.btnRun)
        btnTakePhoto = findViewById(R.id.btnTakePhoto)
        btnPickGallery = findViewById(R.id.btnPickGallery)

        segmenter = YoloSegmenter(this)
        setupZoomGesture()
        previewView.setOnTouchListener { _, event ->
            zoomGestureDetector.onTouchEvent(event)
            true
        }
        showIdleUi()

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            == PackageManager.PERMISSION_GRANTED
        ) {
            requestLocationPermissionIfNeeded()
            startCamera()
        } else {
            cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
        }

        resultPanel.setOnClickListener { toggleResultPanel() }
        btnRun.setOnClickListener {
            when {
                isShowingResult -> uploadCurrentInspectionReport()
                currentBitmap == null -> startActivity(Intent(this, HistoryActivity::class.java))
                else -> runSegmentation()
            }
        }
        btnTakePhoto.setOnClickListener { onTakePhotoClicked() }
        btnClose.setOnClickListener { resetToCamera() }
        btnTorch.setOnClickListener { toggleTorch() }
        btnPickGallery.setOnClickListener {
            if (isShowingResult) {
                resetToCamera()
            } else {
                stopCamera()
                galleryLauncher.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
            }
        }
        validateStoredSession()
    }

    private fun validateStoredSession() {
        val storage = AuthStorage(this)
        val accessToken = storage.accessToken ?: return
        Thread {
            try {
                ApiClient().me(storage.baseUrl, accessToken)
            } catch (e: ApiAuthException) {
                runOnUiThread { clearAuthAndOpenLogin(e.message) }
            } catch (_: IOException) {
                runOnUiThread {
                    if (!isShowingResult && currentBitmap == null) {
                        tvStatus.text = getString(R.string.status_offline_mode)
                    }
                }
            }
        }.start()
    }

    private fun onTakePhotoClicked() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            == PackageManager.PERMISSION_GRANTED
        ) {
            requestLocationPermissionIfNeeded()
            if (isCameraActive) capturePhoto() else startCamera()
        } else {
            cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    private fun requestLocationPermissionIfNeeded() {
        val provider = LocationProvider(this)
        if (provider.hasLocationPermission()) return
        locationPermissionLauncher.launch(
            arrayOf(
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION
            )
        )
    }

    private fun startCamera() {
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({
            cameraProvider = future.get()
            try {
                cameraProvider?.unbindAll()
                val preview = Preview.Builder().build()
                preview.setSurfaceProvider(previewView.surfaceProvider)
                imageCapture = ImageCapture.Builder()
                    .setCaptureMode(ImageCapture.CAPTURE_MODE_MAXIMIZE_QUALITY)
                    .build()

                camera = cameraProvider?.bindToLifecycle(
                    this,
                    CameraSelector.DEFAULT_BACK_CAMERA,
                    preview,
                    imageCapture
                )
                setupCameraZoom(camera)
                setupCameraTorch(camera)

                isCameraActive = true
                showCameraUi()
            } catch (e: Exception) {
                tvStatus.text = "Ошибка камеры: ${e.message}"
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun stopCamera() {
        cameraProvider?.unbindAll()
        camera = null
        imageCapture = null
        isTorchOn = false
        isCameraActive = false
        previewView.visibility = View.GONE
        maskOverlay.visibility = View.VISIBLE
        tvZoom.visibility = View.GONE
        btnTorch.visibility = View.GONE
        btnTakePhoto.text = getString(R.string.take_photo)
    }

    private fun capturePhoto() {
        val capture = imageCapture ?: return
        val file = File(cacheDir, "camera_capture.jpg")
        val outputOptions = ImageCapture.OutputFileOptions.Builder(file).build()

        capture.takePicture(outputOptions, cameraExecutor,
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    val bitmap = decodeBitmapFileWithOrientation(file)
                    runOnUiThread {
                        stopCamera()
                        currentBitmap = bitmap
                        currentResult = null
                        currentLocalReportId = null
                        isReportSent = false
                        currentCapturedAtIso = nowIso()
                        maskOverlay.setImage(bitmap)
                        showPhotoReadyUi(getString(R.string.status_photo_ready))
                    }
                }

                override fun onError(exc: ImageCaptureException) {
                    runOnUiThread { tvStatus.text = "Ошибка съемки: ${exc.message}" }
                }
            }
        )
    }

    private fun loadImageFromUri(uri: Uri) {
        try {
            val bitmap = contentResolver.openInputStream(uri)?.use { stream ->
                BitmapFactory.decodeStream(stream)
            }
            if (bitmap != null) {
                val rotated = rotateBitmap(bitmap, readUriOrientation(uri))
                currentBitmap = rotated
                currentResult = null
                currentLocalReportId = null
                isReportSent = false
                currentCapturedAtIso = nowIso()
                previewView.visibility = View.GONE
                maskOverlay.visibility = View.VISIBLE
                maskOverlay.setImage(rotated)
                showPhotoReadyUi(getString(R.string.status_image_ready))
            }
        } catch (e: Exception) {
            tvStatus.text = "Ошибка загрузки: ${e.message}"
        }
    }

    private fun runSegmentation() {
        val bitmap = currentBitmap
        if (bitmap == null) {
            Toast.makeText(this, R.string.no_image, Toast.LENGTH_SHORT).show()
            return
        }

        showAnalyzingUi()
        Thread {
            try {
                val result: SegmentationResult = segmenter.segment(bitmap, DEFAULT_CONFIDENCE)
                runOnUiThread { handleResult(result) }
            } catch (e: Exception) {
                runOnUiThread {
                    tvStatus.text = getString(R.string.status_error)
                    tvResultHeadline.text = getString(R.string.status_error)
                    tvDetails.text = e.message
                    isShowingResult = false
                    btnRun.text = getString(R.string.run_segmentation)
                    btnRun.isEnabled = true
                    btnRun.visibility = View.VISIBLE
                    setRunButtonCentered(true)
                    resultPanel.visibility = View.VISIBLE
                }
            }
        }.start()
    }

    private fun handleResult(result: SegmentationResult) {
        val bitmap = currentBitmap ?: return
        currentResult = result
        isReportSent = false
        previewView.visibility = View.GONE
        maskOverlay.visibility = View.VISIBLE
        maskOverlay.setResult(
            bitmap,
            result.detections,
            result.maskWidth,
            result.maskHeight,
            result.maskCrop
        )

        val det = result.detections
        tvResultHeadline.text = if (det.isEmpty()) {
            "Дефекты не найдены"
        } else {
            "Найдено дефектов: ${det.size}"
        }

        if (det.isEmpty()) {
            resultCollapsedText = "Снимок не содержит объектов выше порога уверенности."
            resultExpandedText = resultCollapsedText
        } else {
            val counts = StringBuilder()
            det.groupBy { it.className }
                .map { (name, list) -> name to list.size }
                .sortedByDescending { it.second }
                .forEach { (name, count) -> counts.append("• $name: $count\n") }

            val top = StringBuilder()
            top.append("Самые уверенные:\n")
            det.sortedByDescending { it.confidence }
                .take(4)
                .forEach { d -> top.append("${d.className}  ${"%.2f".format(d.confidence)}\n") }

            resultCollapsedText = counts.toString().trimEnd() + "\nНажмите, чтобы раскрыть подробности."
            resultExpandedText = counts.toString().trimEnd() + "\n\n" + top.toString().trimEnd()
        }

        isResultExpanded = false
        tvDetails.text = resultCollapsedText
        showResultUi()
    }

    private fun uploadCurrentInspectionReport() {
        if (isUploadInProgress || isReportSent) return
        val bitmap = currentBitmap ?: return
        val result = currentResult ?: return
        uploadInspectionReport(bitmap, result)
    }

    private fun uploadInspectionReport(bitmap: Bitmap, result: SegmentationResult) {
        val storage = AuthStorage(this)
        val accessToken = storage.accessToken
        if (accessToken.isNullOrBlank()) {
            clearAuthAndOpenLogin()
            return
        }

        isUploadInProgress = true
        val annotatedBitmap = maskOverlay.createAnnotatedBitmap()
        val analysisJson = buildAnalysisJson(result)
        val deviceInfoJson = buildDeviceInfoJson()
        val deviceId = getAndroidDeviceId()
        val location = LocationProvider(this).getLastKnownLocation()
        tvStatus.text = getString(R.string.status_uploading)
        btnRun.isEnabled = false
        btnPickGallery.isEnabled = false
        btnClose.isEnabled = false
        Thread {
            try {
                val inspectionId = ApiClient().uploadInspection(
                    baseUrl = storage.baseUrl,
                    accessToken = accessToken,
                    bitmap = bitmap,
                    annotatedBitmap = annotatedBitmap,
                    capturedAtIso = currentCapturedAtIso,
                    analysisJson = analysisJson,
                    appVersion = BuildConfig.VERSION_NAME,
                    deviceId = deviceId,
                    deviceInfoJson = deviceInfoJson,
                    location = location
                )
                val localReportId = currentLocalReportId
                if (localReportId == null) {
                    val savedReport = LocalReportStore(this).saveReport(
                        bitmap = bitmap,
                        annotatedBitmap = annotatedBitmap,
                        capturedAtIso = currentCapturedAtIso,
                        analysisJson = analysisJson,
                        appVersion = BuildConfig.VERSION_NAME,
                        deviceId = deviceId,
                        deviceInfoJson = deviceInfoJson,
                        location = location,
                        detectionsCount = result.detections.size,
                        status = LocalReportStore.STATUS_SENT,
                        inspectionId = inspectionId,
                        errorMessage = null
                    )
                    currentLocalReportId = savedReport.id
                } else {
                    LocalReportStore(this).updateStatus(localReportId, LocalReportStore.STATUS_SENT, inspectionId, null)
                }
                runOnUiThread {
                    isUploadInProgress = false
                    isReportSent = true
                    tvStatus.text = if (inspectionId > 0) {
                        "${getString(R.string.status_uploaded)} #$inspectionId"
                    } else {
                        getString(R.string.status_uploaded)
                    }
                    btnRun.text = getString(R.string.report_sent_button)
                    btnRun.isEnabled = false
                    btnPickGallery.isEnabled = true
                    btnClose.isEnabled = true
                }
            } catch (e: ApiAuthException) {
                runOnUiThread { clearAuthAndOpenLogin(e.message) }
            } catch (e: Exception) {
                val localReportId = currentLocalReportId
                if (localReportId == null) {
                    val savedReport = LocalReportStore(this).saveReport(
                        bitmap = bitmap,
                        annotatedBitmap = annotatedBitmap,
                        capturedAtIso = currentCapturedAtIso,
                        analysisJson = analysisJson,
                        appVersion = BuildConfig.VERSION_NAME,
                        deviceId = deviceId,
                        deviceInfoJson = deviceInfoJson,
                        location = location,
                        detectionsCount = result.detections.size,
                        status = LocalReportStore.STATUS_PENDING,
                        inspectionId = null,
                        errorMessage = e.message
                    )
                    currentLocalReportId = savedReport.id
                } else {
                    LocalReportStore(this).updateStatus(localReportId, LocalReportStore.STATUS_PENDING, null, e.message)
                }
                runOnUiThread {
                    isUploadInProgress = false
                    tvStatus.text = getString(R.string.status_saved_for_retry)
                    btnRun.text = getString(R.string.send_report)
                    btnRun.isEnabled = true
                    btnPickGallery.isEnabled = true
                    btnClose.isEnabled = true
                }
            }
        }.start()
    }

    private fun buildAnalysisJson(result: SegmentationResult): JSONObject {
        val detections = JSONArray()
        for (det in result.detections) {
            detections.put(
                JSONObject()
                    .put("class_id", det.classId)
                    .put("class_name", det.className)
                    .put("confidence", det.confidence.toDouble())
                    .put(
                        "bbox",
                        JSONArray()
                            .put(det.bbox.left.toDouble())
                            .put(det.bbox.top.toDouble())
                            .put(det.bbox.right.toDouble())
                            .put(det.bbox.bottom.toDouble())
                    )
            )
        }

        val stage = JSONObject()
            .put("stage_code", "defect_segmentation")
            .put("stage_name", "Сегментация дефектов")
            .put("stage_order", 1)
            .put("model_version", MODEL_VERSION)
            .put("status", "success")
            .put("result", JSONObject().put("detections_count", result.detections.size))
            .put("detections", detections)

        return JSONObject()
            .put("pipeline_code", "mobile_welding_analysis")
            .put("pipeline_version", PIPELINE_VERSION)
            .put("source", "mobile")
            .put("status", "success")
            .put("summary", JSONObject().put("detections_count", result.detections.size))
            .put("stages", JSONArray().put(stage))
    }

    private fun buildDeviceInfoJson(): JSONObject {
        return JSONObject()
            .put("manufacturer", Build.MANUFACTURER)
            .put("model", Build.MODEL)
            .put("android_sdk", Build.VERSION.SDK_INT)
            .put("android_release", Build.VERSION.RELEASE)
    }

    private fun getAndroidDeviceId(): String {
        return Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID) ?: "unknown"
    }

    private fun showIdleUi() {
        previewView.visibility = View.GONE
        maskOverlay.visibility = View.VISIBLE
        resultPanel.visibility = View.GONE
        btnClose.visibility = View.GONE
        btnTorch.visibility = View.GONE
        captureButtonContainer.visibility = View.VISIBLE
        btnRun.visibility = View.VISIBLE
        btnRun.text = getString(R.string.history)
        btnPickGallery.visibility = View.VISIBLE
        btnPickGallery.text = getString(R.string.pick_gallery)
        setRunButtonCentered(false)
        isShowingResult = false
        currentResult = null
        currentLocalReportId = null
        isUploadInProgress = false
        isReportSent = false
        btnRun.isEnabled = true
        btnClose.isEnabled = true
        btnPickGallery.isEnabled = true
        btnTakePhoto.isEnabled = true
        btnTakePhoto.text = getString(R.string.capture_photo)
        tvZoom.visibility = View.GONE
        tvStatus.text = getString(R.string.status_ready)
    }

    private fun showCameraUi() {
        previewView.visibility = View.VISIBLE
        maskOverlay.visibility = View.GONE
        resultPanel.visibility = View.GONE
        btnClose.visibility = View.GONE
        btnTorch.visibility = if (camera?.cameraInfo?.hasFlashUnit() == true) View.VISIBLE else View.GONE
        captureButtonContainer.visibility = View.VISIBLE
        btnRun.visibility = View.VISIBLE
        btnRun.text = getString(R.string.history)
        btnPickGallery.visibility = View.VISIBLE
        btnPickGallery.text = getString(R.string.pick_gallery)
        setRunButtonCentered(false)
        isShowingResult = false
        currentResult = null
        currentLocalReportId = null
        isUploadInProgress = false
        isReportSent = false
        btnRun.isEnabled = true
        btnClose.isEnabled = true
        btnPickGallery.isEnabled = true
        btnTakePhoto.isEnabled = true
        btnTakePhoto.text = getString(R.string.capture_photo)
        tvZoom.visibility = View.VISIBLE
        tvStatus.text = getString(R.string.status_camera_ready)
    }

    private fun showPhotoReadyUi(status: String) {
        resultPanel.visibility = View.GONE
        btnClose.visibility = View.VISIBLE
        btnTorch.visibility = View.GONE
        captureButtonContainer.visibility = View.GONE
        btnPickGallery.visibility = View.GONE
        btnRun.visibility = View.VISIBLE
        btnRun.text = getString(R.string.run_segmentation)
        setRunButtonCentered(true)
        isShowingResult = false
        isUploadInProgress = false
        isReportSent = false
        btnRun.isEnabled = true
        btnClose.isEnabled = true
        btnPickGallery.isEnabled = true
        btnTakePhoto.isEnabled = true
        btnTakePhoto.text = getString(R.string.take_photo)
        tvZoom.visibility = View.GONE
        tvStatus.text = status
    }

    private fun showAnalyzingUi() {
        resultPanel.visibility = View.GONE
        btnClose.visibility = View.VISIBLE
        btnTorch.visibility = View.GONE
        captureButtonContainer.visibility = View.GONE
        btnPickGallery.visibility = View.GONE
        btnRun.visibility = View.VISIBLE
        btnRun.text = getString(R.string.analyzing_button)
        setRunButtonCentered(true)
        isShowingResult = false
        btnRun.isEnabled = false
        btnClose.isEnabled = false
        btnPickGallery.isEnabled = false
        btnTakePhoto.isEnabled = false
        tvZoom.visibility = View.GONE
        tvStatus.text = getString(R.string.status_processing)
    }

    private fun showResultUi() {
        resultPanel.visibility = View.VISIBLE
        btnClose.visibility = View.VISIBLE
        btnTorch.visibility = View.GONE
        captureButtonContainer.visibility = View.GONE
        btnPickGallery.visibility = View.VISIBLE
        btnPickGallery.text = getString(R.string.retake_photo)
        btnRun.visibility = View.VISIBLE
        btnRun.text = if (isReportSent) getString(R.string.report_sent_button) else getString(R.string.send_report)
        setRunButtonCentered(false)
        isShowingResult = true
        btnRun.isEnabled = !isReportSent && !isUploadInProgress
        btnClose.isEnabled = true
        btnPickGallery.isEnabled = true
        btnTakePhoto.isEnabled = true
        btnTakePhoto.text = getString(R.string.take_photo)
        tvZoom.visibility = View.GONE
        tvStatus.text = getString(R.string.status_done)
        applyResultPanelSize()
    }

    private fun resetToCamera() {
        currentBitmap = null
        currentResult = null
        currentLocalReportId = null
        isUploadInProgress = false
        isReportSent = false
        tvDetails.text = ""
        tvResultHeadline.text = getString(R.string.result_title)
        maskOverlay.clear()
        startCamera()
    }

    private fun clearAuthAndOpenLogin(message: String? = null) {
        AuthStorage(this).clear()
        stopCamera()
        if (!message.isNullOrBlank()) {
            Toast.makeText(this, message, Toast.LENGTH_LONG).show()
        }
        startActivity(
            Intent(this, LoginActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
        )
        finish()
    }

    private fun toggleResultPanel() {
        if (!isShowingResult) return
        isResultExpanded = !isResultExpanded
        tvDetails.text = if (isResultExpanded) resultExpandedText else resultCollapsedText
        applyResultPanelSize()
    }

    private fun applyResultPanelSize() {
        val params = resultPanel.layoutParams
        params.height = dp(if (isResultExpanded) 300 else 112)
        resultPanel.layoutParams = params
    }

    private fun setRunButtonCentered(centered: Boolean) {
        val parent = btnRun.parent as? LinearLayout
        val params = btnRun.layoutParams as LinearLayout.LayoutParams
        if (parent?.orientation == LinearLayout.VERTICAL) {
            params.width = LinearLayout.LayoutParams.MATCH_PARENT
            params.height = dp(48)
            params.weight = 0f
        } else {
            if (centered) {
                params.width = dp(190)
                params.weight = 0f
            } else {
                params.width = 0
                params.weight = 1f
            }
        }
        btnRun.layoutParams = params
    }

    private fun dp(value: Int): Int {
        return (value * resources.displayMetrics.density).toInt()
    }

    private fun configureSystemBars() {
        window.statusBarColor = Color.BLACK
        window.navigationBarColor = Color.BLACK
        WindowCompat.getInsetsController(window, window.decorView).apply {
            isAppearanceLightStatusBars = false
            isAppearanceLightNavigationBars = false
        }
    }

    private fun setupZoomGesture() {
        zoomGestureDetector = ScaleGestureDetector(this,
            object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
                override fun onScale(detector: ScaleGestureDetector): Boolean {
                    val activeCamera = camera ?: return false
                    val nextZoom = (currentZoomRatio * detector.scaleFactor)
                        .coerceIn(minZoomRatio, maxZoomRatio)
                    activeCamera.cameraControl.setZoomRatio(nextZoom)
                    currentZoomRatio = nextZoom
                    updateZoomLabel()
                    return true
                }
            }
        )
    }

    private fun setupCameraZoom(activeCamera: Camera?) {
        val camera = activeCamera ?: return
        camera.cameraInfo.zoomState.observe(this) { state ->
            minZoomRatio = state.minZoomRatio
            maxZoomRatio = state.maxZoomRatio
            currentZoomRatio = state.zoomRatio.coerceIn(minZoomRatio, maxZoomRatio)
            updateZoomLabel()
        }
    }

    private fun setupCameraTorch(activeCamera: Camera?) {
        val camera = activeCamera ?: return
        if (!camera.cameraInfo.hasFlashUnit()) {
            btnTorch.visibility = View.GONE
            return
        }

        camera.cameraInfo.torchState.observe(this) { state ->
            isTorchOn = state == TorchState.ON
            btnTorch.alpha = if (isTorchOn) 1f else 0.72f
        }
    }

    private fun toggleTorch() {
        val camera = camera ?: return
        if (!camera.cameraInfo.hasFlashUnit()) return
        camera.cameraControl.enableTorch(!isTorchOn)
    }

    private fun updateZoomLabel() {
        tvZoom.text = "${"%.1f".format(currentZoomRatio)}x"
    }

    private fun decodeBitmapFileWithOrientation(file: File): Bitmap {
        val bitmap = BitmapFactory.decodeFile(file.absolutePath)
            ?: throw IllegalStateException("Не удалось прочитать снимок")
        val exif = ExifInterface(file.absolutePath)
        return rotateBitmap(bitmap, exif.getAttributeInt(
            ExifInterface.TAG_ORIENTATION,
            ExifInterface.ORIENTATION_NORMAL
        ))
    }

    private fun readUriOrientation(uri: Uri): Int {
        return try {
            contentResolver.openInputStream(uri)?.use { stream ->
                ExifInterface(stream).getAttributeInt(
                    ExifInterface.TAG_ORIENTATION,
                    ExifInterface.ORIENTATION_NORMAL
                )
            } ?: ExifInterface.ORIENTATION_NORMAL
        } catch (e: Exception) {
            ExifInterface.ORIENTATION_NORMAL
        }
    }

    private fun rotateBitmap(bitmap: Bitmap, orientation: Int): Bitmap {
        val degrees = when (orientation) {
            ExifInterface.ORIENTATION_ROTATE_90 -> 90f
            ExifInterface.ORIENTATION_ROTATE_180 -> 180f
            ExifInterface.ORIENTATION_ROTATE_270 -> 270f
            else -> 0f
        }
        if (degrees == 0f) return bitmap

        val matrix = Matrix().apply { postRotate(degrees) }
        val rotated = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
        if (rotated != bitmap) bitmap.recycle()
        return rotated
    }

    override fun onDestroy() {
        super.onDestroy()
        segmenter.close()
        cameraExecutor.shutdown()
    }

    companion object {
        private const val DEFAULT_CONFIDENCE = 0.25f
        private const val MODEL_VERSION = "yolo26s-clean-ft40-tflite"
        private const val PIPELINE_VERSION = "1.0.0"

        private fun nowIso(): String {
            return OffsetDateTime.now().format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
        }
    }
}
