package com.lingtouch.cs30live

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbDeviceConnection
import android.hardware.usb.UsbManager
import android.os.SystemClock
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger

data class DeviceChoice(val id: Int, val label: String, val supported: Boolean) {
    override fun toString() = label
}

interface CameraBackend : AutoCloseable {
    val needsCameraPermission: Boolean
    fun devices(): List<DeviceChoice>
    fun hasPermission(id: Int): Boolean
    fun requestPermission(id: Int)
    fun connect(id: Int)
    fun disconnect()
    fun acquire(mode: Int)
    fun poll(): String
    fun diagnostics(): String = ""
    fun noteUsbEvent(message: String) {}
    fun usbDetached(id: Int) {}
    fun usbAttached(id: Int) {}
}

/** Instrumentation can inject a backend in-process. No Intent enables simulation. */
object AppDependencies {
    var factory: (Context) -> CameraBackend = { UsbCameraBackend(it) }
}

object NativeCamera {
    const val RECOVERY_REOPEN = 1
    const val RECOVERY_REDISCOVER = 2
    init { System.loadLibrary("cs30_live") }
    @JvmStatic external fun create(): Long
    @JvmStatic external fun open(handle: Long, fd: Int, restoreStreamIdle: Boolean): String?
    @JvmStatic external fun resetAfterStartupError(handle: Long): Int
    @JvmStatic external fun disconnect(handle: Long): String?
    @JvmStatic external fun destroy(handle: Long)
    @JvmStatic external fun acquire(handle: Long, mode: Int): String?
    @JvmStatic external fun poll(handle: Long): String
    @JvmStatic external fun interfaceInfo(fd: Int, interfaceId: Int): String
    @JvmStatic external fun cleanupStatus(): String?
}

class UsbCameraBackend(context: Context) : CameraBackend {
    companion object {
        const val ACTION_PERMISSION = "com.lingtouch.cs30live.USB_PERMISSION"
        const val REQUESTED_DEVICE = "requested_device_id"
        private val transportLock = Any()
        private var activeOwner: UsbCameraBackend? = null
    }
    private val context = context.applicationContext
    private val usb = context.getSystemService(Context.USB_SERVICE) as UsbManager
    private var connection: UsbDeviceConnection? = null
    private var handle = 0L
    private val knownDevices = ConcurrentHashMap<Int, UsbDevice>()
    private val detachedIds = ConcurrentHashMap.newKeySet<Int>()
    private val replugCount = AtomicInteger()
    private var preparedReplug = 0
    private val usbLog = mutableListOf<String>()
    private fun log(value: String) = synchronized(usbLog) {
        if (usbLog.size >= 40) usbLog.removeAt(0)
        usbLog.add(value)
    }
    override val needsCameraPermission = true
    private fun device(id: Int): UsbDevice {
        check(id !in detachedIds) { "原 USB 连接已断开，请选择重新出现的 CS30" }
        val current = runCatching { usb.deviceList.values.firstOrNull { it.deviceId == id } }
            .onFailure { log("USB enumeration failed while resolving id=$id: ${it.message}") }.getOrNull()
        if (current != null) { knownDevices[id] = current; return current }
        knownDevices[id]?.let {
            log("USB enumeration omitted selected id=$id; using selected device snapshot ${it.deviceName}")
            return it
        }
        error("所选 USB 设备不在当前列表中（id=$id），请刷新后重新选择")
    }

    override fun devices(): List<DeviceChoice> {
        val current = usb.deviceList.values
        val presentIds = current.map { it.deviceId }.toSet()
        // A confirmed absence also lets a later attachment reuse this USB address.
        detachedIds.removeIf { it !in presentIds }
        return current.filter { it.deviceId !in detachedIds }.map {
            knownDevices[it.deviceId] = it
            val supported = it.vendorId == 0x2207 && it.productId == 0x0016
            val name = if (supported) "CS30" else runCatching { it.productName }.getOrNull() ?: "USB 设备"
            DeviceChoice(it.deviceId, "%s · %04X:%04X · #%d".format(name, it.vendorId, it.productId, it.deviceId), supported)
        }.sortedWith(compareByDescending<DeviceChoice> { it.supported }.thenBy { it.id })
    }

    override fun hasPermission(id: Int) = runCatching { usb.hasPermission(device(id)) }.getOrDefault(false)
    override fun requestPermission(id: Int) {
        val intent = Intent(ACTION_PERMISSION).setPackage(context.packageName).putExtra(REQUESTED_DEVICE, id)
        val pending = PendingIntent.getBroadcast(context, id, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        usb.requestPermission(device(id), pending)
    }

    // Also serializes separate Activity/controller instances during rapid reopen.
    override fun connect(id: Int) { synchronized(transportLock) {
        activeOwner?.takeIf { it !== this }?.disconnect()
        disconnect()
        NativeCamera.cleanupStatus()?.let { error(it) }
        val selected = device(id)
        require(selected.vendorId == 0x2207 && selected.productId == 0x0016) { "请选择 CS30（2207:0016）" }
        val replug = replugCount.get()
        if (openDevice(selected, allowReset = true, restoreStreamIdle = replug != preparedReplug)) {
            val reopened = findDeviceAfterReset(selected)
            openDevice(reopened, allowReset = false, restoreStreamIdle = true)
        }
        preparedReplug = replug
    } }

    private fun findDeviceAfterReset(selected: UsbDevice): UsbDevice {
        val deadline = SystemClock.elapsedRealtime() + 1500
        do {
            check(selected.deviceId !in detachedIds) { "USB 复位后原连接已断开，请选择重新出现的 CS30" }
            val current = runCatching { usb.deviceList[selected.deviceName] }.getOrNull()
            if (current != null && current.deviceId == selected.deviceId &&
                current.vendorId == selected.vendorId && current.productId == selected.productId) {
                check(usb.hasPermission(current)) { "USB 复位后需要重新授权，请点“连接设备”" }
                knownDevices[current.deviceId] = current
                return current
            }
            SystemClock.sleep(75)
        } while (SystemClock.elapsedRealtime() < deadline)
        error("USB 复位后所选 CS30 已重新枚举或暂不可见，请刷新设备列表后重新连接")
    }

    /** Returns true when the reset succeeded and this connection was closed for a fresh open. */
    private fun openDevice(device: UsbDevice, allowReset: Boolean, restoreStreamIdle: Boolean): Boolean {
        check(device.deviceId !in detachedIds) { "原 USB 连接已断开，请选择重新出现的 CS30" }
        check(usb.hasPermission(device)) { "尚未获得 USB 权限" }
        val conn = usb.openDevice(device) ?: error("无法打开 USB 设备，请确认授权和连接")
        activeOwner = this
        var handedToNative = false
        try {
            log("Java connect selected id=${device.deviceId}, name=${device.deviceName}, recoveryAllowed=$allowReset")
            val interfaces = (0 until device.interfaceCount).map { device.getInterface(it) }
                .sortedBy { it.alternateSetting }.distinctBy { it.id }.associateBy { it.id }
            UsbClaims.forceAll(interfaces.keys.toList(),
                { id -> conn.claimInterface(checkNotNull(interfaces[id]), true) },
                { id -> conn.releaseInterface(checkNotNull(interfaces[id])) },
                { id -> NativeCamera.interfaceInfo(conn.fileDescriptor, id) }, ::log)
            if (handle == 0L) handle = NativeCamera.create()
            check(handle != 0L) { "视觉处理器初始化失败" }
            handedToNative = true
            connection = conn
            val startupError = NativeCamera.open(handle, conn.fileDescriptor, restoreStreamIdle)
            if (startupError != null) {
                val recovery = if (allowReset && device.deviceId !in detachedIds)
                    NativeCamera.resetAfterStartupError(handle) else 0
                when (recovery) {
                    NativeCamera.RECOVERY_REOPEN -> {
                        log("Retrying once with a fresh USB connection after: $startupError")
                        disconnect()
                        return true
                    }
                    NativeCamera.RECOVERY_REDISCOVER -> {
                        usbDetached(device.deviceId)
                        error("USB 复位后原连接已断开，等待 CS30 重新出现后再选择连接")
                    }
                }
                error(startupError)
            }
            log("Native open OK; Java fd=${conn.fileDescriptor}")
            return false
        } catch (error: Throwable) {
            log("Connect failed: ${error.message}")
            val cleanup = if (handedToNative && handle != 0L) NativeCamera.disconnect(handle) else null
            if (cleanup == null) { conn.close(); connection = null; if(activeOwner === this)activeOwner=null }
            else log("Cleanup pending; retaining Java connection: $cleanup")
            throw IllegalStateException((error.message ?: error.javaClass.simpleName) +
                (cleanup?.let { "\nUSB 清理尚未完成：$it" } ?: ""), error)
        }
    }
    override fun acquire(mode: Int) { synchronized(transportLock) {
        check(handle != 0L) { "相机尚未连接" }
        NativeCamera.acquire(handle, mode)?.let { error(it) }
    } }
    override fun poll(): String = synchronized(transportLock) { if (handle == 0L) "{}" else NativeCamera.poll(handle) }
    override fun disconnect() { synchronized(transportLock) {
        if (handle != 0L) NativeCamera.disconnect(handle)?.let { log(it); error(it) }
        connection?.close()
        connection = null
        if(activeOwner === this)activeOwner=null
    } }
    override fun diagnostics(): String { synchronized(transportLock) {
        val local = synchronized(usbLog) { usbLog.joinToString("\n") }
        val native = if (handle == 0L) "" else runCatching { org.json.JSONObject(NativeCamera.poll(handle)).optString("usb_log") }.getOrDefault("")
        return local + if (native.isEmpty()) "" else "\n$native"
    } }
    override fun noteUsbEvent(message: String) { log(message) }
    override fun usbDetached(id: Int) {
        if (detachedIds.add(id)) replugCount.incrementAndGet()
        knownDevices.remove(id)
    }
    override fun usbAttached(id: Int) { detachedIds.remove(id) }
    override fun close() { synchronized(transportLock) {
        // destroy() moves a timed-out camera + Engine to a safe native cleanup owner.
        // The native-owned dup keeps the same file description alive if Java closes.
        runCatching { disconnect() }.onFailure { log("Deferred close: ${it.message}") }
        if (handle != 0L) NativeCamera.destroy(handle)
        handle = 0L
        connection?.close()
        connection = null
        if(activeOwner === this)activeOwner=null
    } }
}
