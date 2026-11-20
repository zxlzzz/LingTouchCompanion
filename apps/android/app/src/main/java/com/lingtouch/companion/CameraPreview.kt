package com.lingtouch.companion

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Handler
import android.os.Looper
import android.widget.ImageView
import android.widget.TextView
import java.util.concurrent.Executors

// Constructor signature is also used by jni_bridge.cpp.
data class CameraPreviewFrame(
    val epoch: Long,
    val frameId: Long,
    val colorJpeg: ByteArray,
    val depthArgb: IntArray,
    val depthWidth: Int,
    val depthHeight: Int,
)

/** One preview decode in flight; stopping/reconnecting invalidates old results. */
class CameraPreview(
    private val colorView: ImageView,
    private val depthView: ImageView,
    private val status: TextView,
) {
    private val main = Handler(Looper.getMainLooper())
    private val decoder = Executors.newSingleThreadExecutor()
    private var active = false
    private var busy = false
    private var generation = 0L
    private var epoch: Long? = null
    private var lastFrame = 0L

    fun start() { active = true }

    fun stop() {
        active = false
        clear("预览已暂停")
    }

    fun destroy() {
        stop()
        // Let the one in-flight task finish and discard its result on main.
        decoder.shutdown()
    }

    fun clear(message: String = "尚无相机画面") {
        generation++
        lastFrame = 0
        colorView.setImageDrawable(null)
        depthView.setImageDrawable(null)
        status.text = message
        // Displayed Bitmaps are reference counted/GC-managed by Android. Only
        // recycle a discarded decode that has never been bound to an ImageView.
    }

    fun update(service: StreamService) {
        if (!active) return
        val currentEpoch = service.currentPreviewEpoch()
        if (epoch != currentEpoch) {
            epoch = currentEpoch
            clear()
        }
        if (currentEpoch == null || busy) return
        busy = true
        val token = generation
        service.requestPreview(lastFrame) { frame ->
            if (frame == null || !active || token != generation) {
                busy = false
                return@requestPreview
            }
            decoder.execute {
                val errors = mutableListOf<String>()
                val color = runCatching {
                    if (frame.colorJpeg.isEmpty()) null else BitmapFactory.decodeByteArray(
                        frame.colorJpeg, 0, frame.colorJpeg.size,
                        BitmapFactory.Options().apply { inSampleSize = 2 },
                    )
                }.getOrNull()
                if (color == null) errors += "彩色预览解码失败或无彩色图像"
                val depth = runCatching {
                    Bitmap.createBitmap(frame.depthArgb, frame.depthWidth, frame.depthHeight, Bitmap.Config.ARGB_8888)
                }.getOrNull()
                if (depth == null) errors += "深度预览生成失败"
                main.post {
                    busy = false
                    if (!active || token != generation || service.currentPreviewEpoch() != frame.epoch) {
                        color?.recycle()
                        depth?.recycle()
                        return@post
                    }
                    lastFrame = frame.frameId
                    colorView.setImageBitmap(color)
                    depthView.setImageBitmap(depth)
                    status.text = if (errors.isEmpty()) "相机实时画面；深度 0.1～5 m，近亮远暗，黑色为无效"
                        else errors.joinToString("；")
                }
            }
        }
    }
}
