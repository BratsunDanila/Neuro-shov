package com.weldingdefect

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.RectF
import org.tensorflow.lite.Interpreter
import java.io.FileInputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.channels.FileChannel
import kotlin.math.exp
import kotlin.math.max
import kotlin.math.min

class YoloSegmenter(context: Context) {

    private val interpreter: Interpreter

    private val inputSize = 640
    private val numPredictions: Int
    private val predLen: Int
    private val numProtoMasks: Int
    private val maskH: Int
    private val maskW: Int

    init {
        val buffer = loadModelFile(context, "welding_seg_float32.tflite")
        val options = Interpreter.Options().apply {
            setNumThreads(4)
        }
        interpreter = Interpreter(buffer, options)

        val out0Shape = interpreter.getOutputTensor(0).shape()
        val out1Shape = interpreter.getOutputTensor(1).shape()

        numPredictions = out0Shape[1]
        predLen = out0Shape[2]
        numProtoMasks = out1Shape[1]
        maskH = out1Shape[2]
        maskW = out1Shape[3]
    }

    fun segment(bitmap: Bitmap, confThreshold: Float): SegmentationResult {
        val srcW = bitmap.width
        val srcH = bitmap.height

        val letterbox = createLetterbox(bitmap, inputSize)
        val inputBuffer = bitmapToBuffer(letterbox.bitmap)

        val output0 = Array(1) { Array(numPredictions) { FloatArray(predLen) } }
        val output1 = Array(1) { Array(numProtoMasks) { Array(maskH) { FloatArray(maskW) } } }

        val outputs: MutableMap<Int, Any> = mutableMapOf(
            0 to output0,
            1 to output1
        )

        interpreter.runForMultipleInputsOutputs(arrayOf(inputBuffer), outputs)

        val predictions = output0[0]
        val protoMasks = output1[0]

        val detections = mutableListOf<Detection>()
        for (i in predictions.indices) {
            val row = predictions[i]
            val confidence = row[4]
            if (confidence < confThreshold) continue

            val classId = Math.round(row[5]).toInt()
            if (classId < 0 || classId >= CLASS_NAMES.size) continue

            val x1 = row[0] * inputSize
            val y1 = row[1] * inputSize
            val x2 = row[2] * inputSize
            val y2 = row[3] * inputSize

            val origX1 = (x1 - letterbox.padX) / letterbox.scale
            val origY1 = (y1 - letterbox.padY) / letterbox.scale
            val origX2 = (x2 - letterbox.padX) / letterbox.scale
            val origY2 = (y2 - letterbox.padY) / letterbox.scale

            val bbox = RectF(origX1, origY1, origX2, origY2)

            val maskCoeffs = row.sliceArray(6 until predLen)

            val mask = decodeMask(maskCoeffs, protoMasks, bbox, srcW, srcH, letterbox)

            detections.add(
                Detection(
                    classId = classId,
                    className = CLASS_NAMES[classId],
                    confidence = confidence,
                    bbox = bbox,
                    mask = mask
                )
            )
        }

        val maskCrop = RectF(
            letterbox.padX * maskW / inputSize,
            letterbox.padY * maskH / inputSize,
            (letterbox.padX + srcW * letterbox.scale) * maskW / inputSize,
            (letterbox.padY + srcH * letterbox.scale) * maskH / inputSize
        )

        letterbox.bitmap.recycle()
        return SegmentationResult(detections, srcW, srcH, maskW, maskH, maskCrop)
    }

    private fun createLetterbox(bitmap: Bitmap, targetSize: Int): LetterboxResult {
        val srcW = bitmap.width
        val srcH = bitmap.height
        val scale = minOf(targetSize.toFloat() / srcW, targetSize.toFloat() / srcH)
        val newW = (srcW * scale).toInt()
        val newH = (srcH * scale).toInt()
        val padX = (targetSize - newW) / 2f
        val padY = (targetSize - newH) / 2f

        val resized = Bitmap.createScaledBitmap(bitmap, newW, newH, true)
        val canvasBitmap = Bitmap.createBitmap(targetSize, targetSize, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(canvasBitmap)
        canvas.drawColor(Color.rgb(114, 114, 114))
        canvas.drawBitmap(resized, padX, padY, null)
        resized.recycle()

        return LetterboxResult(canvasBitmap, scale, padX, padY)
    }

    private fun decodeMask(
        maskCoeffs: FloatArray,
        protoMasks: Array<Array<FloatArray>>,
        bbox: RectF,
        srcW: Int,
        srcH: Int,
        letterbox: LetterboxResult
    ): Array<FloatArray> {
        val result = Array(maskH) { FloatArray(maskW) }

        for (y in 0 until maskH) {
            for (x in 0 until maskW) {
                var sum = 0f
                for (m in 0 until minOf(maskCoeffs.size, numProtoMasks)) {
                    sum += maskCoeffs[m] * protoMasks[m][y][x]
                }
                result[y][x] = sigmoid(sum)
            }
        }

        val bboxInMaskX1 = (bbox.left * letterbox.scale + letterbox.padX) * maskW / inputSize
        val bboxInMaskY1 = (bbox.top * letterbox.scale + letterbox.padY) * maskH / inputSize
        val bboxInMaskX2 = (bbox.right * letterbox.scale + letterbox.padX) * maskW / inputSize
        val bboxInMaskY2 = (bbox.bottom * letterbox.scale + letterbox.padY) * maskH / inputSize

        val bx1 = max(0f, bboxInMaskX1).toInt()
        val by1 = max(0f, bboxInMaskY1).toInt()
        val bx2 = min(maskW.toFloat(), bboxInMaskX2).toInt()
        val by2 = min(maskH.toFloat(), bboxInMaskY2).toInt()

        for (y in 0 until maskH) {
            for (x in 0 until maskW) {
                if (y < by1 || y >= by2 || x < bx1 || x >= bx2) {
                    result[y][x] = 0f
                }
            }
        }

        return result
    }

    private fun sigmoid(x: Float): Float {
        return if (x >= 0f) {
            1f / (1f + exp(-x))
        } else {
            val ex = exp(x)
            ex / (1f + ex)
        }
    }

    private fun bitmapToBuffer(bitmap: Bitmap): ByteBuffer {
        val buffer = ByteBuffer.allocateDirect(4 * inputSize * inputSize * 3)
        buffer.order(ByteOrder.nativeOrder())

        val intValues = IntArray(inputSize * inputSize)
        bitmap.getPixels(intValues, 0, inputSize, 0, 0, inputSize, inputSize)

        for (pixel in intValues) {
            buffer.putFloat(((pixel shr 16) and 0xFF) / 255f)
            buffer.putFloat(((pixel shr 8) and 0xFF) / 255f)
            buffer.putFloat((pixel and 0xFF) / 255f)
        }

        buffer.rewind()
        return buffer
    }

    private fun loadModelFile(context: Context, filename: String): ByteBuffer {
        val fd = context.assets.openFd(filename)
        val inputStream = FileInputStream(fd.fileDescriptor)
        val channel = inputStream.channel
        val buffer = channel.map(FileChannel.MapMode.READ_ONLY, fd.startOffset, fd.declaredLength)
        inputStream.close()
        return buffer
    }

    fun close() {
        interpreter.close()
    }

    private data class LetterboxResult(
        val bitmap: Bitmap,
        val scale: Float,
        val padX: Float,
        val padY: Float
    )

    data class SegmentationResult(
        val detections: List<Detection>,
        val imageWidth: Int,
        val imageHeight: Int,
        val maskWidth: Int,
        val maskHeight: Int,
        val maskCrop: RectF
    )

    companion object {
        val CLASS_NAMES = arrayOf(
            "Плохой шов",
            "Трещина",
            "Избыточное усиление",
            "Хороший шов",
            "Пористость",
            "Брызги"
        )
    }
}
