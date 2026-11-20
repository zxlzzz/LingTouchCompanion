package com.lingtouch.companion

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothStatusCodes
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import java.util.UUID

/**
 * 触觉手柄（旧板，V2.8 固件）BLE 链路。
 *
 * 服务 FFE0：写 FFE1 下发 15 字节点阵帧；FFE3 通知 [类型, 数据]：0x01 刷新完成，0x04 按键扫描请求。
 * 手柄一次刷新约 220 ms，刷新中收到新帧会中止当前刷新，所以一次只发一帧：
 * 收到刷新完成（或超时）后再发最新的待发帧，中间的帧只保留最后一帧。
 * 流程与 9/29 比赛版 hw/phone/.../device/HandleLink.ets 相同。
 */
@SuppressLint("MissingPermission")  // 调用前由界面申请 BLUETOOTH_SCAN / BLUETOOTH_CONNECT；缺权限时抛出的异常在这里接住
class HandleLink(private val context: Context, private val listener: Listener) {
    interface Listener {
        fun onHandleState(state: String)
        fun onFrameDone(frame: ByteArray, shown: Boolean)
        fun onHandleButton()
        fun onHandleLog(message: String)
    }

    companion object {
        val SERVICE: UUID = UUID.fromString("0000FFE0-0000-1000-8000-00805F9B34FB")
        val FRAME: UUID = UUID.fromString("0000FFE1-0000-1000-8000-00805F9B34FB")
        val STATUS: UUID = UUID.fromString("0000FFE3-0000-1000-8000-00805F9B34FB")
        val CCCD: UUID = UUID.fromString("00002902-0000-1000-8000-00805F9B34FB")
        const val EVT_REFRESH_DONE = 0x01
        const val EVT_SCAN_REQUEST = 0x04
        const val SCAN_MS = 8000L
        const val REFRESH_TIMEOUT_MS = 1500L
    }

    private val main = Handler(Looper.getMainLooper())
    private var gatt: BluetoothGatt? = null
    private var frameChar: BluetoothGattCharacteristic? = null  // 订阅 FFE3 成功后才可发帧
    private var discoveredFrameChar: BluetoothGattCharacteristic? = null
    private var inflight: ByteArray? = null
    private var pending: ByteArray? = null
    private val timeout = Runnable { finishInflight(false) }

    @Volatile var state: String = "未连接"
        private set

    private fun setState(s: String) {
        state = s
        listener.onHandleState(s)
    }

    /** 扫描广播 FFE0 服务的手柄 [SCAN_MS] 毫秒，连接信号最强的一个。 */
    fun scanAndConnect() {
        val adapter = (context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager).adapter
        if (adapter == null || !adapter.isEnabled) {
            setState("蓝牙未开启")
            return
        }
        val scanner = adapter.bluetoothLeScanner ?: run { setState("蓝牙不可用"); return }
        val found = LinkedHashMap<String, ScanResult>()
        val callback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult) {
                found[result.device.address] = result
            }
        }
        try {
            val filter = ScanFilter.Builder().setServiceUuid(ParcelUuid(SERVICE)).build()
            val settings = ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build()
            scanner.startScan(listOf(filter), settings, callback)
            setState("扫描中")
        } catch (e: SecurityException) {
            setState("缺少蓝牙权限")
            return
        }
        main.postDelayed({
            try { scanner.stopScan(callback) } catch (_: SecurityException) { }
            val best = found.values.maxByOrNull { it.rssi }
            if (best == null) setState("没找到手柄") else connect(best.device)
        }, SCAN_MS)
    }

    fun connect(device: BluetoothDevice) {
        disconnect()
        setState("连接中")
        try {
            gatt = device.connectGatt(context, false, callback, BluetoothDevice.TRANSPORT_LE)
        } catch (e: SecurityException) {
            setState("缺少蓝牙权限")
        }
    }

    fun disconnect() {
        main.removeCallbacks(timeout)
        inflight = null
        pending = null
        frameChar = null
        discoveredFrameChar = null
        try {
            gatt?.disconnect()
            gatt?.close()
        } catch (_: SecurityException) { }
        gatt = null
        setState("未连接")
    }

    /** 请求显示一帧；返回 null 表示已发出或已排队，否则是不能发送的原因。 */
    fun show(frame: ByteArray): String? {
        if (frameChar == null) return "手柄未连接"
        main.post {
            if (inflight == null) write(frame) else pending = frame
        }
        return null
    }

    private fun write(frame: ByteArray) {
        val g = gatt ?: return
        val ch = frameChar ?: return
        inflight = frame
        val ok = try {
            if (Build.VERSION.SDK_INT >= 33) {
                g.writeCharacteristic(ch, frame, BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) == BluetoothStatusCodes.SUCCESS
            } else {
                @Suppress("DEPRECATION")
                ch.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
                @Suppress("DEPRECATION")
                ch.value = frame
                @Suppress("DEPRECATION")
                g.writeCharacteristic(ch)
            }
        } catch (e: SecurityException) {
            false
        }
        if (!ok) {
            listener.onHandleLog("写 FFE1 失败")
            finishInflight(false)
            return
        }
        main.postDelayed(timeout, REFRESH_TIMEOUT_MS)
    }

    private fun finishInflight(shown: Boolean) {
        main.removeCallbacks(timeout)
        val done = inflight ?: return
        inflight = null
        listener.onFrameDone(done, shown)
        val next = pending
        pending = null
        if (next != null) write(next)
    }

    private fun onStatus(value: ByteArray) {
        if (value.isEmpty()) return
        when (value[0].toInt() and 0xff) {
            EVT_REFRESH_DONE -> main.post { finishInflight(true) }
            EVT_SCAN_REQUEST -> main.post { listener.onHandleButton() }
        }
    }

    private val callback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
            main.post {
                if (g != gatt) return@post
                if (newState == BluetoothProfile.STATE_CONNECTED) {
                    setState("发现服务中")
                    try { g.discoverServices() } catch (_: SecurityException) { setState("缺少蓝牙权限") }
                } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                    frameChar = null
                    inflight = null
                    pending = null
                    setState("已断开（状态 $status）")
                }
            }
        }

        override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
            main.post {
                val service = g.getService(SERVICE)
                val frame = service?.getCharacteristic(FRAME)
                val statusChar = service?.getCharacteristic(STATUS)
                val cccd = statusChar?.getDescriptor(CCCD)
                if (frame == null || statusChar == null || cccd == null) {
                    setState("手柄上没有 FFE0/FFE1/FFE3")
                    return@post
                }
                try {
                    g.setCharacteristicNotification(statusChar, true)
                    if (Build.VERSION.SDK_INT >= 33) {
                        g.writeDescriptor(cccd, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
                    } else {
                        @Suppress("DEPRECATION")
                        cccd.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                        @Suppress("DEPRECATION")
                        g.writeDescriptor(cccd)
                    }
                } catch (_: SecurityException) {
                    setState("缺少蓝牙权限")
                    return@post
                }
                discoveredFrameChar = frame
            }
        }

        override fun onDescriptorWrite(g: BluetoothGatt, descriptor: BluetoothGattDescriptor, status: Int) {
            main.post {
                if (descriptor.uuid == CCCD && status == BluetoothGatt.GATT_SUCCESS) {
                    frameChar = discoveredFrameChar
                    setState("已连接")
                } else {
                    setState("订阅 FFE3 失败（状态 $status）")
                }
            }
        }

        // API 33 起的回调
        override fun onCharacteristicChanged(g: BluetoothGatt, c: BluetoothGattCharacteristic, value: ByteArray) {
            if (c.uuid == STATUS) onStatus(value)
        }

        // API 32 及以下的回调
        @Deprecated("Deprecated in Java")
        override fun onCharacteristicChanged(g: BluetoothGatt, c: BluetoothGattCharacteristic) {
            @Suppress("DEPRECATION")
            if (Build.VERSION.SDK_INT < 33 && c.uuid == STATUS) onStatus(c.value ?: return)
        }
    }
}
