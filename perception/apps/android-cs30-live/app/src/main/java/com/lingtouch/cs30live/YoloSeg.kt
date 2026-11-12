package com.lingtouch.cs30live

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.content.Context
import android.graphics.Bitmap
import org.json.JSONObject
import java.nio.FloatBuffer
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min

internal const val RGB_WIDTH = 960
internal const val RGB_HEIGHT = 540
internal const val RGBD_PIXELS = RGB_WIDTH * RGB_HEIGHT
internal const val RGBD_BYTES = RGBD_PIXELS * 2

internal class YoloSeg(context: Context) : AutoCloseable {
    private val assets = context.applicationContext.assets
    private val env = OrtEnvironment.getEnvironment()
    private val labels = JSONObject(assets.open("yolo_model.json").bufferedReader().use { it.readText() })
        .getJSONObject("classes")
    private var session: OrtSession? = null

    internal data class Prediction(val masks: Array<ByteArray>, val names: List<String>)
    private data class Box(val anchor: Int, val cls: Int, val score: Float,
                           val left: Float, val top: Float, val right: Float, val bottom: Float) {
        fun area() = (right - left) * (bottom - top)
        fun overlap(other: Box): Float {
            val width = max(0f, min(right, other.right) - max(left, other.left))
            val height = max(0f, min(bottom, other.bottom) - max(top, other.top))
            val intersection = width * height
            return intersection / (area() + other.area() - intersection)
        }
    }

    private fun getSession(): OrtSession {
        session?.let { return it }
        val bytes = assets.open("yolov8s-seg.onnx").use { it.readBytes() }
        return OrtSession.SessionOptions().use { opts ->
            opts.setIntraOpNumThreads(3)
            opts.setInterOpNumThreads(1)
            env.createSession(bytes, opts).also { session = it }
        }
    }

    fun predict(bitmap: Bitmap): Prediction {
        require(bitmap.width == RGB_WIDTH && bitmap.height == RGB_HEIGHT)
        val scaled = Bitmap.createScaledBitmap(bitmap, 640, 360, true)
        val argb = IntArray(640 * 360)
        scaled.getPixels(argb, 0, 640, 0, 0, 640, 360)
        scaled.recycle()
        val plane = 640 * 384
        val input = FloatArray(3 * plane) { 114f / 255 }
        for (i in argb.indices) {
            val pixel = argb[i]
            val at = i + 12 * 640
            input[at] = ((pixel ushr 16) and 255) / 255f
            input[plane + at] = ((pixel ushr 8) and 255) / 255f
            input[2 * plane + at] = (pixel and 255) / 255f
        }
        val model = getSession()
        OnnxTensor.createTensor(env, FloatBuffer.wrap(input), longArrayOf(1, 3, 384, 640)).use { tensor ->
            model.run(mapOf(model.inputNames.single() to tensor)).use { output ->
                val boxesBuffer = (output[0] as OnnxTensor).floatBuffer
                val boxes = FloatArray(boxesBuffer.remaining())
                boxesBuffer.get(boxes)
                val protoBuffer = (output[1] as OnnxTensor).floatBuffer
                val protos = FloatArray(protoBuffer.remaining())
                protoBuffer.get(protos)
                require(boxes.size == 116 * 5040 && protos.size == 32 * 96 * 160)
                return decode(boxes, protos)
            }
        }
    }

    private fun decode(output: FloatArray, protos: FloatArray): Prediction {
        val anchors = 5040
        val candidates = ArrayList<Box>()
        for (a in 0 until anchors) {
            var score = .25f
            var cls = -1
            for (c in 0 until 80) {
                val value = output[(4 + c) * anchors + a]
                if (value > score) { score = value; cls = c }
            }
            if (cls < 0) continue
            val x = output[a]
            val y = output[anchors + a]
            val w = output[2 * anchors + a]
            val h = output[3 * anchors + a]
            val left = ((x - w / 2) * 1.5f).coerceIn(0f, 960f)
            val top = ((y - h / 2 - 12) * 1.5f).coerceIn(0f, 540f)
            val right = ((x + w / 2) * 1.5f).coerceIn(0f, 960f)
            val bottom = ((y + h / 2 - 12) * 1.5f).coerceIn(0f, 540f)
            if (right > left && bottom > top) candidates.add(Box(a, cls, score, left, top, right, bottom))
        }
        val selected = ArrayList<Box>()
        for (candidate in candidates.sortedByDescending { it.score }) {
            if (selected.none { it.cls == candidate.cls && it.overlap(candidate) > .70f }) selected.add(candidate)
            if (selected.size == 32) break
        }
        val masks = Array(selected.size) { i ->
            val box = selected[i]
            val small = FloatArray(96 * 160)
            for (c in 0 until 32) {
                val factor = output[(84 + c) * anchors + box.anchor]
                val base = c * small.size
                for (p in small.indices) small[p] += factor * protos[base + p]
            }
            val mask = ByteArray(RGBD_PIXELS)
            // The original 960x540 image letterboxes to 640x360 plus 12 rows on each side.
            // Crop the equivalent three rows of mask padding before bilinear upsampling.
            for (y in ceil(box.top).toInt() until ceil(box.bottom).toInt()) {
                val fy = (y + .5f) / 6f - .5f
                val sy = floor(fy).toInt()
                val y0 = sy.coerceIn(0, 89) + 3
                val y1 = (sy + 1).coerceIn(0, 89) + 3
                val wy = fy - sy
                for (x in ceil(box.left).toInt() until ceil(box.right).toInt()) {
                    val fx = (x + .5f) / 6f - .5f
                    val sx = floor(fx).toInt()
                    val x0 = sx.coerceIn(0, 159)
                    val x1 = (sx + 1).coerceIn(0, 159)
                    val wx = fx - sx
                    val a = small[y0 * 160 + x0] * (1 - wx) + small[y0 * 160 + x1] * wx
                    val b = small[y1 * 160 + x0] * (1 - wx) + small[y1 * 160 + x1] * wx
                    if (a * (1 - wy) + b * wy > 0) mask[y * RGB_WIDTH + x] = 1
                }
            }
            mask
        }
        return Prediction(masks, selected.map { labels.optString(it.cls.toString(), it.cls.toString()) })
    }

    override fun close() {
        session?.close()
        session = null
    }
}
