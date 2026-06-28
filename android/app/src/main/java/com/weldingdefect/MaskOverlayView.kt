package com.weldingdefect

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import kotlin.math.max

class MaskOverlayView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    private var originalBitmap: Bitmap? = null
    private var detections: List<Detection> = emptyList()
    private var maskWidth: Int = 0
    private var maskHeight: Int = 0
    private var maskCrop: RectF = RectF()
    private var renderScale: Float = 1f
    private var offsetX: Float = 0f
    private var offsetY: Float = 0f
    private var userScale: Float = 1f
    private var panX: Float = 0f
    private var panY: Float = 0f
    private var lastTouchX: Float = 0f
    private var lastTouchY: Float = 0f
    private val scaleDetector = ScaleGestureDetector(
        context,
        object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
            override fun onScale(detector: ScaleGestureDetector): Boolean {
                val previousScale = userScale
                userScale = (userScale * detector.scaleFactor).coerceIn(1f, 5f)
                val scaleChange = userScale / previousScale
                panX = detector.focusX - (detector.focusX - panX) * scaleChange
                panY = detector.focusY - (detector.focusY - panY) * scaleChange
                clampPan()
                invalidate()
                return true
            }
        }
    )

    private val maskPaint = Paint().apply {
        isAntiAlias = true
        isFilterBitmap = true
    }

    private val labelBgPaint = Paint().apply {
        style = Paint.Style.FILL
        color = Color.argb(232, 255, 255, 255)
        isAntiAlias = true
    }

    private val labelBorderPaint = Paint().apply {
        style = Paint.Style.STROKE
        strokeWidth = 2f
        isAntiAlias = true
    }

    private val labelTextPaint = Paint().apply {
        color = Color.rgb(17, 24, 39)
        textSize = 24f
        isAntiAlias = true
    }

    fun setResult(
        bitmap: Bitmap,
        detections: List<Detection>,
        maskW: Int,
        maskH: Int,
        crop: RectF
    ) {
        originalBitmap = bitmap
        this.detections = detections
        maskWidth = maskW
        maskHeight = maskH
        maskCrop = RectF(crop)
        resetUserTransform()
        invalidate()
    }

    fun setImage(bitmap: Bitmap) {
        originalBitmap = bitmap
        detections = emptyList()
        maskWidth = 0
        maskHeight = 0
        maskCrop = RectF()
        resetUserTransform()
        invalidate()
    }

    fun clear() {
        originalBitmap = null
        detections = emptyList()
        maskCrop = RectF()
        resetUserTransform()
        invalidate()
    }

    fun createAnnotatedBitmap(): Bitmap? {
        val source = originalBitmap ?: return null
        if (maskWidth <= 0 || maskHeight <= 0) return source.copy(Bitmap.Config.ARGB_8888, false)

        val result = source.copy(Bitmap.Config.ARGB_8888, true)
        val canvas = Canvas(result)
        for (det in detections) {
            drawMask(canvas, det)
            drawLabel(canvas, det)
        }
        return result
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (originalBitmap == null) return false
        scaleDetector.onTouchEvent(event)

        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                lastTouchX = event.x
                lastTouchY = event.y
            }
            MotionEvent.ACTION_MOVE -> {
                if (!scaleDetector.isInProgress && event.pointerCount == 1 && canPan()) {
                    panX += event.x - lastTouchX
                    panY += event.y - lastTouchY
                    clampPan()
                    invalidate()
                }
                lastTouchX = event.x
                lastTouchY = event.y
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                if (userScale <= 1.01f) userScale = 1f
                clampPan()
            }
        }

        return true
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val bmp = originalBitmap ?: return

        computeTransform(bmp.width, bmp.height)
        canvas.save()
        canvas.translate(offsetX + panX, offsetY + panY)
        canvas.scale(renderScale * userScale, renderScale * userScale)
        canvas.drawBitmap(bmp, 0f, 0f, null)

        for (det in detections) {
            drawMask(canvas, det)
            drawLabel(canvas, det)
        }
        canvas.restore()
    }

    private fun computeTransform(bmpW: Int, bmpH: Int) {
        val viewW = width.toFloat()
        val viewH = height.toFloat()
        if (viewW <= 0f || viewH <= 0f) return
        val scaleW = viewW / bmpW
        val scaleH = viewH / bmpH
        renderScale = maxOf(scaleW, scaleH)
        offsetX = (viewW - bmpW * renderScale) / 2f
        offsetY = (viewH - bmpH * renderScale) / 2f
        clampPan()
    }

    private fun resetUserTransform() {
        userScale = 1f
        panX = 0f
        panY = 0f
    }

    private fun canPan(): Boolean {
        val bmp = originalBitmap ?: return false
        return bmp.width * renderScale * userScale > width + 1f ||
            bmp.height * renderScale * userScale > height + 1f
    }

    private fun clampPan() {
        val bmp = originalBitmap ?: return
        val viewW = width.toFloat()
        val viewH = height.toFloat()
        if (viewW <= 0f || viewH <= 0f) return

        val scaledW = bmp.width * renderScale * userScale
        val scaledH = bmp.height * renderScale * userScale

        panX = if (scaledW <= viewW) {
            -offsetX + (viewW - scaledW) / 2f
        } else {
            panX.coerceIn(viewW - scaledW - offsetX, -offsetX)
        }

        panY = if (scaledH <= viewH) {
            -offsetY + (viewH - scaledH) / 2f
        } else {
            panY.coerceIn(viewH - scaledH - offsetY, -offsetY)
        }
    }

    private fun drawMask(canvas: Canvas, det: Detection) {
        val bmpW = originalBitmap?.width ?: return
        val bmpH = originalBitmap?.height ?: return
        val mask = det.mask
        if (mask.isEmpty()) return

        val color = CLASS_COLORS[det.classId % CLASS_COLORS.size]
        val r = Color.red(color)
        val g = Color.green(color)
        val b = Color.blue(color)

        val maskBmp = Bitmap.createBitmap(maskWidth, maskHeight, Bitmap.Config.ARGB_8888)
        for (y in 0 until maskHeight) {
            val row = mask[y]
            for (x in 0 until maskWidth) {
                if (row[x] >= 0.5f) {
                    maskBmp.setPixel(x, y, Color.argb(120, r, g, b))
                }
            }
        }

        val src = Rect(
            maskCrop.left.toInt().coerceIn(0, maskWidth - 1),
            maskCrop.top.toInt().coerceIn(0, maskHeight - 1),
            maskCrop.right.toInt().coerceIn(1, maskWidth),
            maskCrop.bottom.toInt().coerceIn(1, maskHeight)
        )
        val dst = RectF(0f, 0f, bmpW.toFloat(), bmpH.toFloat())
        canvas.drawBitmap(maskBmp, src, dst, maskPaint)
        maskBmp.recycle()
    }

    private fun drawLabel(canvas: Canvas, det: Detection) {
        val label = "${det.className} ${"%.2f".format(det.confidence)}"
        val bbox = det.bbox

        val anchorX = max(0f, bbox.left)
        val anchorY = max(0f, bbox.top - 36f)

        val tw = labelTextPaint.measureText(label)
        val bgRect = RectF(anchorX - 8, anchorY - 6, anchorX + tw + 8, anchorY + 26 + 6)

        val color = CLASS_COLORS[det.classId % CLASS_COLORS.size]
        labelBorderPaint.color = color

        canvas.drawRoundRect(bgRect, 12f, 12f, labelBgPaint)
        canvas.drawRoundRect(bgRect, 12f, 12f, labelBorderPaint)
        canvas.drawText(label, anchorX, anchorY + 20f, labelTextPaint)
    }

    companion object {
        private val CLASS_COLORS = intArrayOf(
            Color.parseColor("#c0392b"),
            Color.parseColor("#d35400"),
            Color.parseColor("#2980b9"),
            Color.parseColor("#27ae60"),
            Color.parseColor("#16a085"),
            Color.parseColor("#8e44ad")
        )
    }
}
