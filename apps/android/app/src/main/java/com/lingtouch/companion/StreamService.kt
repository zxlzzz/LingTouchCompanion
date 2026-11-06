package com.lingtouch.companion

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbDeviceConnection
import android.hardware.usb.UsbManager
import android.os.Binder
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager

/**
 * 前台服务（connectedDevice 类型）：持有核心、CS30 的 USB 连接和手柄 BLE 链路，切到后台或息屏后继续
 * 取流、计算、发蓝牙。息屏后 CPU 可能休眠，所以开流期间持有一个 PARTIAL_WAKE_LOCK。
 * 能否在息屏下持续运行只能真机测（docs/device_tests.md 第 4 条）。
 */
class StreamService : Service(), HandleLink.Listener {
    inner class LocalBinder : Binder() {
        fun service(): StreamService = this@StreamService
    }

    companion object {
        const val RECONNECT_WAIT_MS = 2000L
        const val CHANNEL_ID = "stream"
        const val NOTIFICATION_ID = 1
        const val CONTINUOUS_GAP_MS = 50L
    }

    private val binder = LocalBinder()
    private val cameraLock = Any()
    @Volatile private var destroyed = false
    private val main = Handler(Looper.getMainLooper())
    private var connection: UsbDeviceConnection? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var foreground = false

    @Volatile var handle: Long = 0
        private set
    lateinit var handleLink: HandleLink
        private set

    @Volatile var cameraStatus = "未连接"
        private set
    @Volatile var lastLog = ""
        private set

    /** 状态 2 在触点上的表示：0 = 还没选（不能发帧），1 = 平，2 = 凸。 */
    @Volatile var policy = NativeCore.POLICY_UNSET
    @Volatile var continuousSend = false
        set(value) {
            field = value
            main.removeCallbacks(continuousTick)
            if (value) main.post(continuousTick)
        }

    // 持续发送：每收到一次刷新完成（或超时）就发最新一帧；发不出去时 0.5 s 后重试
    private val continuousTick = object : Runnable {
        override fun run() {
            if (!continuousSend) return
            val error = sendLatest()
            if (error != null) {
                lastLog = "持续发送暂停：$error"
                main.postDelayed(this, 500)
            }
        }
    }

    @Volatile var framesSent = 0
        private set
    @Volatile var framesShown = 0
        private set
    @Volatile var lastFrameHex = ""
        private set

    override fun onCreate() {
        super.onCreate()
        handle = NativeCore.nativeCreate()
        if (handle == 0L) cameraStatus = "核心初始化失败：" + NativeCore.nativeCreateError()
        else policy = NativeCore.nativeConfigUnknownPolicy(handle)
        handleLink = HandleLink(this, this)
    }

    override fun onBind(intent: Intent): IBinder = binder

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        enterForeground()
        return START_NOT_STICKY
    }

    private fun enterForeground() {
        if (foreground) return
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.createNotificationChannel(NotificationChannel(CHANNEL_ID, "取流与触觉输出", NotificationManager.IMPORTANCE_LOW))
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE
        )
        val notification = Notification.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentTitle("灵触")
            .setContentText("正在取流和发送点阵")
            .setContentIntent(open)
            .setOngoing(true)
            .build()
        startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
        foreground = true
    }

    /** 返回 null 表示已开流。会阻塞约 3 秒（Commit 约 2.36 s），不要在主线程调用。 */
    fun openCamera(device: UsbDevice): String? { synchronized(cameraLock) {
        if (destroyed) return "服务已销毁"
        val h = handle
        if (h == 0L) return cameraStatus
        closeCamera()?.let { return it }
        cameraStatus = "启动中（Commit 约需 2–3 秒）"
        var error = openOnce(device, h)
        if (error != null && error.contains("NO_DEVICE") && !destroyed) {
            Thread.sleep(RECONNECT_WAIT_MS)
            val usb = getSystemService(Context.USB_SERVICE) as UsbManager
            val next = usb.deviceList.values.firstOrNull { it.vendorId == device.vendorId && it.productId == device.productId }
            error = when {
                destroyed -> "服务已销毁"
                next == null -> "$error（相机重新枚举后尚未返回）"
                !usb.hasPermission(next) -> "$error（请重新选择设备并授权）"
                else -> openOnce(next, h)
            }
        }
        if (error != null) { cameraStatus = "开流失败：$error"; return error }
        acquireWakeLock(); cameraStatus = "已开流"; return null
    } }

    private fun openOnce(device: UsbDevice, h: Long): String? {
        closeCamera()?.let { return it }
        if (destroyed) return "服务已销毁"
        val usb = getSystemService(Context.USB_SERVICE) as UsbManager
        val conn = usb.openDevice(device) ?: return "openDevice 失败（无权限或设备当前不可用）"
        val claimed = mutableListOf<android.hardware.usb.UsbInterface>()
        try {
            for (iface in (0 until device.interfaceCount).map { device.getInterface(it) }.sortedBy { it.alternateSetting }.distinctBy { it.id }) {
                val before = NativeCore.nativeInterfaceInfo(conn.fileDescriptor, iface.id)
                lastLog = "Java force claim: $before"
                if (!conn.claimInterface(iface, true)) {
                    claimed.asReversed().forEach { conn.releaseInterface(it) }
                    conn.close(); return "Java force claim 接口 ${iface.id} 失败；$before"
                }
                claimed.add(iface)
            }
            connection = conn
            val error = NativeCore.nativeOpenCamera(h, conn.fileDescriptor)
            if (error != null) {
                val cleanup = NativeCore.nativeCloseCamera(h)
                if (cleanup == null) { conn.close(); connection = null }
                return error + (cleanup?.let { "; cleanup pending: $it" } ?: "")
            }
            return null
        } catch (e: Exception) {
            val cleanup = NativeCore.nativeCloseCamera(h)
            if (cleanup == null) { conn.close(); connection = null }
            return (e.message ?: "USB 连接失败") + (cleanup?.let { "; cleanup pending: $it" } ?: "")
        }
    }

    fun closeCamera(): String? { synchronized(cameraLock) {
        val engineHandle = handle
        if (engineHandle != 0L) NativeCore.nativeCloseCamera(engineHandle)?.let { cameraStatus = it; return it }
        connection?.close()
        connection = null
        releaseWakeLock()
        cameraStatus = "未连接"
        return null
    } }

    fun resetCamera(): String? = synchronized(cameraLock) { val h = handle; if (h == 0L) cameraStatus else NativeCore.nativeResetCamera(h) }

    /** 把最新栅格编码成旧板帧发给手柄。返回 null 表示已发出或排队。 */
    fun sendLatest(): String? {
        if (handle == 0L) return cameraStatus
        if (policy == NativeCore.POLICY_UNSET) return "状态 2 的触点表示还没选（平或凸），不能发帧"
        val frame = NativeCore.nativeEncodeLatest(handle, policy) ?: return NativeCore.nativeLastError(handle)
        val error = handleLink.show(frame)
        if (error == null) {
            framesSent++
            lastFrameHex = frame.joinToString("") { "%02x".format(it.toInt() and 0xff) }
        }
        return error
    }

    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "LingTouch:stream").apply { acquire() }
    }

    private fun releaseWakeLock() {
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
    }

    override fun onHandleState(state: String) {
        lastLog = "手柄：$state"
    }

    override fun onFrameDone(frame: ByteArray, shown: Boolean) {
        if (shown) framesShown++
        if (continuousSend) main.postDelayed(continuousTick, CONTINUOUS_GAP_MS)
    }

    override fun onHandleButton() {
        lastLog = "手柄：按键扫描请求（0x04）"
    }

    override fun onHandleLog(message: String) {
        lastLog = message
    }

    override fun onDestroy() {
        continuousSend = false
        destroyed = true
        val engineHandle = handle
        handle = 0 // Main-thread readers observe invalidation before async destruction.
        Thread { synchronized(cameraLock) {
            if (engineHandle != 0L) {
                NativeCore.nativeCloseCamera(engineHandle)
                NativeCore.nativeDestroy(engineHandle)
            }
            connection?.close()
            connection = null
            releaseWakeLock()
        } }.start()
        handleLink.disconnect()
        super.onDestroy()
    }
}
