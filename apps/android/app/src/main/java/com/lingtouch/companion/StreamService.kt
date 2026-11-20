package com.lingtouch.companion

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.BroadcastReceiver
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbDeviceConnection
import android.hardware.usb.UsbManager
import android.os.Binder
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

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
        const val CHANNEL_ID = "stream"
        const val NOTIFICATION_ID = 1
        const val CONTINUOUS_GAP_MS = 50L
    }

    private val binder = LocalBinder()
    private val main = Handler(Looper.getMainLooper())
    private var connection: UsbDeviceConnection? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var foreground = false
    private val cameraWorker = Executors.newSingleThreadScheduledExecutor()
    // Owned by the camera worker after onCreate. UI handle is cleared early on
    // destroy; in-flight work must keep using this handle until native teardown.
    private var cameraHandle = 0L
    private var cameraPoll: ScheduledFuture<*>? = null
    @Volatile private var wantCamera = false
    @Volatile private var destroying = false
    private var cameraDeviceName = ""
    private var retryCount = 0
    private var retryAt = Long.MAX_VALUE
    private var healthySince = 0L

    private val usbEvents = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            @Suppress("DEPRECATION")
            val device = intent.getParcelableExtra<UsbDevice>(UsbManager.EXTRA_DEVICE) ?: return
            if (device.vendorId != MainActivity.CS30_VENDOR_ID || device.productId != MainActivity.CS30_PRODUCT_ID) return
            cameraWorker.execute {
                if (destroying) return@execute
                if (intent.action == UsbManager.ACTION_USB_DEVICE_DETACHED && device.deviceName == cameraDeviceName) {
                    closeCameraOnWorker()
                    cameraStatus = "相机已断开，等待重新插入"
                    retryAt = Long.MAX_VALUE
                } else if (intent.action == UsbManager.ACTION_USB_DEVICE_ATTACHED && wantCamera) {
                    retryCount = 0
                    retryAt = 0
                }
            }
        }
    }

    @Volatile var handle: Long = 0
        private set
    lateinit var handleLink: HandleLink
        private set

    lateinit var imuLink: WitImuLink
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
        cameraHandle = handle
        if (handle == 0L) cameraStatus = "核心初始化失败：" + NativeCore.nativeCreateError()
        else policy = NativeCore.nativeConfigUnknownPolicy(handle)
        handleLink = HandleLink(this, this)
        imuLink = WitImuLink(
            this,
            startInput = { if (handle == 0L) "核心未初始化" else NativeCore.nativeStartImu(handle) },
            stopInput = { if (handle != 0L) NativeCore.nativeStopImu(handle) },
            pushInput = { bytes, receivedNs ->
                if (handle != 0L) NativeCore.nativePushImuNotify(handle, bytes, receivedNs)
            },
        )
        val filter = IntentFilter(UsbManager.ACTION_USB_DEVICE_ATTACHED).apply {
            addAction(UsbManager.ACTION_USB_DEVICE_DETACHED)
        }
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(usbEvents, filter, Context.RECEIVER_NOT_EXPORTED)
        else registerReceiver(usbEvents, filter)
        cameraPoll = cameraWorker.scheduleWithFixedDelay({ pollCamera() }, 200, 200, TimeUnit.MILLISECONDS)
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

    /** All connection changes are serialized on the service's camera worker. */
    fun openCamera(device: UsbDevice, completed: (String?) -> Unit = {}) {
        wantCamera = true
        cameraWorker.execute {
            if (destroying || !wantCamera || cameraHandle == 0L) return@execute
            retryCount = 0
            retryAt = Long.MAX_VALUE
            closeCameraOnWorker()
            val error = openOnce(device)
            if (error != null) scheduleRecovery()
            main.post { if (!destroying) completed(error) }
        }
    }

    private fun openOnce(device: UsbDevice): String? {
        val activeHandle = cameraHandle
        if (activeHandle == 0L || destroying) return "采集服务正在关闭"
        cameraDeviceName = device.deviceName
        cameraStatus = "正在启动深度和彩色取流"
        acquireWakeLock()
        val error = try {
            NativeCore.nativeOpenCamera(activeHandle, this, device.deviceName, true)
        } catch (e: Exception) {
            "相机启动异常：${e.message}"
        }
        if (error != null) {
            cameraStatus = "开流失败：$error"
            releaseWakeLock()
        } else {
            cameraStatus = NativeCore.nativeCameraStatus(activeHandle)
        }
        healthySince = 0
        return error
    }

    // Called by JNI on the camera worker. These methods must remain available
    // if code shrinking is enabled in a future release build.
    fun usbDeviceIds(): Array<String> {
        val usb = getSystemService(Context.USB_SERVICE) as UsbManager
        return usb.deviceList.values.filter {
            it.vendorId == MainActivity.CS30_VENDOR_ID && it.productId == MainActivity.CS30_PRODUCT_ID
        }.map { it.deviceName }.toTypedArray()
    }

    fun usbAuthorized(id: String): Boolean {
        val usb = getSystemService(Context.USB_SERVICE) as UsbManager
        return usb.deviceList[id]?.let { usb.hasPermission(it) } ?: false
    }

    fun usbOpenFd(id: String): Int {
        usbCloseFd()
        val usb = getSystemService(Context.USB_SERVICE) as UsbManager
        val device = usb.deviceList[id] ?: return -3
        if (!usb.hasPermission(device)) return -2
        val conn = usb.openDevice(device) ?: return -1
        val interfaces = (0 until device.interfaceCount).map { device.getInterface(it) }
            .sortedBy { it.alternateSetting }.distinctBy { it.id }
        for (iface in interfaces.filter { it.id == 0 || it.id == 1 }) {
            if (!conn.claimInterface(iface, true)) {
                conn.close()
                return -1
            }
        }
        connection = conn
        return conn.fileDescriptor
    }

    fun usbCloseFd() {
        connection?.close()
        connection = null
    }

    fun closeCamera() {
        wantCamera = false
        cameraWorker.execute { if (!destroying) closeCameraOnWorker() }
    }

    private fun closeCameraOnWorker() {
        if (cameraHandle != 0L) NativeCore.nativeCloseCamera(cameraHandle)
        usbCloseFd()
        releaseWakeLock()
        cameraStatus = "未连接"
        healthySince = 0
    }

    private fun scheduleRecovery() {
        retryAt = Long.MAX_VALUE
        if (cameraHandle == 0L || !wantCamera || destroying) return
        val code = NativeCore.nativeCameraCode(cameraHandle)
        if (!recoverable(code)) return
        if (retryCount >= 3) {
            cameraStatus += "；自动重试已结束，请检查连接后重新连接"
            return
        }
        retryAt = android.os.SystemClock.elapsedRealtime() + (1000L shl retryCount)
        retryCount++
    }

    private fun recoverable(code: Int): Boolean = code == NativeCore.CAMERA_OPEN_FAILED || code == NativeCore.CAMERA_DISCONNECTED ||
        code == NativeCore.CAMERA_INTERRUPTED || code == NativeCore.CAMERA_IO_ERROR ||
        code == NativeCore.CAMERA_START_FAILED

    private fun pollCamera() {
        if (destroying || cameraHandle == 0L || !wantCamera) return
        val activeHandle = cameraHandle
        try {
            val now = android.os.SystemClock.elapsedRealtime()
            if (connection != null) {
                cameraStatus = NativeCore.nativeCameraStatus(activeHandle)
                val code = NativeCore.nativeCameraCode(activeHandle)
                if (recoverable(code)) {
                    scheduleRecovery()
                    val message = cameraStatus
                    closeCameraOnWorker()
                    cameraStatus = message
                } else if (NativeCore.nativeCameraStreaming(activeHandle)) {
                    if (healthySince == 0L) healthySince = now
                    if (now - healthySince >= 10000) retryCount = 0
                }
                return
            }
            if (now < retryAt) return
            val usb = getSystemService(Context.USB_SERVICE) as UsbManager
            val device = usb.deviceList.values.firstOrNull {
                it.vendorId == MainActivity.CS30_VENDOR_ID && it.productId == MainActivity.CS30_PRODUCT_ID
            } ?: run { retryAt = Long.MAX_VALUE; return }
            if (!usb.hasPermission(device)) {
                cameraStatus = "相机已重新插入，请在前台点击连接并授权"
                retryAt = Long.MAX_VALUE
                return
            }
            retryAt = Long.MAX_VALUE
            val error = openOnce(device)
            if (error != null) scheduleRecovery()
        } catch (e: Exception) {
            lastLog = "检查相机连接失败：${e.message}"
        }
    }

    fun resetCamera(): String? {
        if (handle == 0L) return cameraStatus
        cameraWorker.execute {
            if (destroying || cameraHandle == 0L) return@execute
            cameraStatus = "正在重新启动取流"
            val error = NativeCore.nativeResetCamera(cameraHandle)
            if (error != null) cameraStatus = error
        }
        return null
    }

    // Keep JNI access serialized with open/close/destroy. JPEG decoding belongs
    // to a separate preview worker and never stalls USB callbacks or this queue.
    fun requestPreview(afterFrameId: Long, completed: (CameraPreviewFrame?) -> Unit) {
        try {
            cameraWorker.execute {
                val frame = runCatching {
                    if (!destroying && cameraHandle != 0L)
                        NativeCore.nativeCameraPreview(cameraHandle, afterFrameId) else null
                }.getOrElse { lastLog = "读取预览失败：${it.message}"; null }
                main.post { completed(frame) }
            }
        } catch (_: java.util.concurrent.RejectedExecutionException) {
            main.post { completed(null) }
        }
    }

    // UI-thread only: onDestroy clears handle on this same thread before the
    // native object is destroyed by cameraWorker.
    fun currentPreviewEpoch(): Long? {
        val activeHandle = handle
        return if (wantCamera && !destroying && activeHandle != 0L && NativeCore.nativeCameraStreaming(activeHandle))
            NativeCore.nativeCameraEpoch(activeHandle) else null
    }

    fun requestPlaneCheck(completed: (String) -> Unit) {
        cameraWorker.execute {
            if (destroying || cameraHandle == 0L) return@execute
            val report = NativeCore.nativePlaneCheck(cameraHandle)
            main.post { if (!destroying) completed(report) }
        }
    }

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
        destroying = true
        wantCamera = false
        cameraPoll?.cancel(false)
        unregisterReceiver(usbEvents)
        continuousSend = false
        handleLink.disconnect()
        imuLink.disconnect()
        val closingHandle = handle
        handle = 0
        cameraWorker.execute {
            if (closingHandle != 0L) {
                NativeCore.nativeCloseCamera(closingHandle)
                NativeCore.nativeDestroy(closingHandle)
            }
            cameraHandle = 0L
            usbCloseFd()
            releaseWakeLock()
        }
        cameraWorker.shutdown()
        super.onDestroy()
    }
}
