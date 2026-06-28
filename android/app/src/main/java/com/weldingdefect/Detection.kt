package com.weldingdefect

import android.graphics.RectF

data class Detection(
    val classId: Int,
    val className: String,
    val confidence: Float,
    val bbox: RectF,
    val mask: Array<FloatArray>
)
