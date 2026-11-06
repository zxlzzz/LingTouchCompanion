package com.lingtouch.cs30live

import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong

data class CaptureState(val connected: Boolean = false, val connecting: Boolean = false,
                        val mode: Int = 0, val deviceId: Int? = null,
                        val message: String = "请接入 CS30 并选择设备", val frame: FrameRecord? = null,
                        val delivered: Int = 0, val transportLog: String = "")

/** Single-thread native ownership; epoch changes immediately suppress late UI results. */
class CaptureController(private val backend: CameraBackend, private val listener: (CaptureState) -> Unit) : AutoCloseable {
    private val main = Handler(Looper.getMainLooper())
    private val worker = Executors.newSingleThreadScheduledExecutor()
    private val epoch = AtomicLong()
    @Volatile private var alive = true
    @Volatile var state = CaptureState()
        private set
    private var workerConnected = false
    private var workerMode = 0
    private var workerEpoch = 0L
    private var seenFrame = -1L
    private var waitingSince = 0L

    init { worker.scheduleWithFixedDelay({ poll() }, 0, 60, TimeUnit.MILLISECONDS) }
    private fun update(next: CaptureState) { state = next; listener(next) }
    private fun post(token: Long, change: (CaptureState) -> CaptureState) {
        main.post { if (alive && epoch.get() == token) update(change(state)) }
    }
    private fun failed(token: Long, error: Throwable) {
        workerMode = 0; workerConnected = false
        runCatching { backend.disconnect() }
        val log = backend.diagnostics()
        post(token) { it.copy(connected = false, connecting = false, mode = 0,
            message = "连接或采集失败：${error.message ?: error.javaClass.simpleName}", transportLog = log) }
    }

    fun connect(id: Int) {
        val token = epoch.incrementAndGet()
        update(state.copy(connecting = true, connected = false, mode = 0, deviceId = id, message = "正在连接并读取相机标定…"))
        worker.execute {
            workerEpoch = token; workerMode = 0; workerConnected = false
            try {
                backend.connect(id); workerConnected = true; seenFrame = -1
                val log = backend.diagnostics()
                post(token) { it.copy(connecting = false, connected = true, mode = 0, message = "已连接，等待采集", transportLog = log) }
            } catch (e: Throwable) { failed(token, e) }
        }
    }

    fun start(mode: Int) {
        require(mode == 1 || mode == 2)
        if (!state.connected || state.connecting || state.mode != 0) return
        val token = epoch.incrementAndGet()
        update(state.copy(mode = mode, message = if (mode == 1) "正在获取一张新深度帧…" else "自动采集中 · 2 次/秒"))
        worker.execute {
            workerEpoch = token
            try {
                backend.acquire(mode); workerMode = mode; seenFrame = -1
                waitingSince = SystemClock.elapsedRealtime()
            } catch (e: Throwable) { failed(token, e) }
        }
    }

    fun stop(message: String = "已停止，保留最后一次处理结果") {
        if (state.connecting) { disconnect("已取消连接"); return }
        if (state.mode == 0) return
        val token = epoch.incrementAndGet()
        update(state.copy(mode = 0, message = message))
        worker.execute {
            workerEpoch = token; workerMode = 0
            if (workerConnected) try { backend.acquire(0) } catch (e: Throwable) { failed(token, e) }
        }
    }

    fun disconnect(message: String = "已断开，保留最后一次处理结果") {
        val token = epoch.incrementAndGet()
        update(state.copy(connected = false, connecting = false, mode = 0, deviceId = null, message = message))
        worker.execute {
            workerEpoch = token; workerMode = 0; workerConnected = false
            runCatching { backend.disconnect() }.onFailure { failed(token, it) }
        }
    }

    private fun poll() {
        if (!alive || !workerConnected) return
        val token = workerEpoch
        try {
            val json = JSONObject(backend.poll())
            if (!json.optBoolean("connected")) {
                val reason = if (json.optInt("usb_last_transfer_status", -1) == 5) "USB 句柄已失效（NO_DEVICE）" else "USB 数据流已停止"
                failed(token, IllegalStateException("$reason，请重新连接并查看诊断日志")); return
            }
            if (workerMode == 0) return
            val frame = FrameRecord.parse(json)
            if (frame != null && frame.id != seenFrame) {
                seenFrame = frame.id; waitingSince = SystemClock.elapsedRealtime()
                val wasManual = workerMode == 1
                if (wasManual) workerMode = 0
                post(token) {
                    it.copy(frame = frame, delivered = it.delivered + 1, mode = if (wasManual) 0 else 2,
                        message = if (!frame.valid) "当前帧地面参考不可用：${frame.failure}"
                            else if (wasManual) "单次采集完成" else "自动采集中 · 2 次/秒")
                }
            } else if (SystemClock.elapsedRealtime() - waitingSince > 5000) {
                backend.acquire(0); workerMode = 0
                post(token) { it.copy(mode = 0, message = "5 秒内未取得新结果，采集已暂停；请检查相机和供电") }
            }
        } catch (e: Throwable) { failed(token, e) }
    }

    override fun close() {
        alive = false; epoch.incrementAndGet()
        worker.execute { workerConnected = false; workerMode = 0; backend.close() }
        worker.shutdown()
    }
    fun collectDiagnostics(callback: (String) -> Unit) {
        if (!alive) return
        worker.execute {
            val text = runCatching { backend.diagnostics() }.getOrElse { "读取诊断失败：${it.message}" }
            main.post { if (alive) callback(text) }
        }
    }
}
