package com.lingtouch.companion

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.BluetoothLeScanner
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import java.util.UUID

/** 维特 IMU 的 BLE 会话，状态与 native 会话都在主线程上管理。 */
@SuppressLint("MissingPermission")
class WitImuLink(
    private val context: Context,
    private val startInput: () -> String?,
    private val stopInput: () -> Unit,
    private val pushInput: (ByteArray, Long) -> Unit,
) {
    companion object {
        private val SERVICE = UUID.fromString("0000ffe5-0000-1000-8000-00805f9a34fb")
        private val NOTIFY = UUID.fromString("0000ffe4-0000-1000-8000-00805f9a34fb")
        private val CCCD = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
        private const val SCAN_MS = 8000L
        private const val CONNECT_MS = 15000L
    }

    private val main = Handler(Looper.getMainLooper())
    private var gatt: BluetoothGatt? = null
    private var scanner: BluetoothLeScanner? = null
    private var scan: ScanCallback? = null
    private var best: ScanResult? = null
    private var bestIs901 = false
    private var inputStarted = false
    private val scanDone = Runnable {
        val result = best
        stopScan()
        if (result == null) state = "没找到维特 IMU" else connect(result.device)
    }
    private val connectTimeout = Runnable { disconnect("连接或订阅超时") }

    var state = "未连接"
        private set

    fun scanAndConnect() {
        disconnect()
        try {
            val adapter = context.getSystemService(BluetoothManager::class.java)?.adapter
            val activeScanner = adapter?.bluetoothLeScanner
            if (activeScanner == null) {
                state = "蓝牙不可用或未开启"
                return
            }
            val callback = object : ScanCallback() {
                override fun onScanResult(callbackType: Int, result: ScanResult) {
                    main.post {
                        if (scan !== this || !result.isConnectable) return@post
                        val record = result.scanRecord
                        val name = record?.deviceName ?: ""
                        val is901 = record?.serviceUuids?.contains(ParcelUuid(SERVICE)) == true ||
                            name.startsWith("WT901BLE", ignoreCase = true) ||
                            name.startsWith("BWT901BLE", ignoreCase = true)
                        val matches = is901 || name.startsWith("WT", ignoreCase = true)
                        if (matches && (best == null || (is901 && !bestIs901) ||
                                (is901 == bestIs901 && result.rssi > (best?.rssi ?: Int.MIN_VALUE)))) {
                            best = result
                            bestIs901 = is901
                        }
                    }
                }

                override fun onScanFailed(errorCode: Int) {
                    main.post { if (scan === this) disconnect("扫描失败（$errorCode）") }
                }
            }
            scanner = activeScanner
            scan = callback
            val settings = ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build()
            activeScanner.startScan(null, settings, callback)
            state = "扫描中"
            main.postDelayed(scanDone, SCAN_MS)
        } catch (_: SecurityException) {
            disconnect("缺少蓝牙权限")
        }
    }

    fun disconnect(reason: String = "未连接") {
        stopScan()
        main.removeCallbacks(connectTimeout)
        val oldGatt = gatt
        gatt = null
        inputStarted = false
        stopInput()
        try { oldGatt?.disconnect() } catch (_: SecurityException) { }
        try { oldGatt?.close() } catch (_: SecurityException) { }
        state = reason
    }

    private fun stopScan() {
        main.removeCallbacks(scanDone)
        val callback = scan
        scan = null
        best = null
        bestIs901 = false
        try { if (callback != null) scanner?.stopScan(callback) } catch (_: SecurityException) { }
        scanner = null
    }

    private fun connect(device: BluetoothDevice) {
        state = "连接中"
        try {
            gatt = device.connectGatt(context, false, gattCallback, BluetoothDevice.TRANSPORT_LE)
            if (gatt == null) disconnect("无法建立 BLE 连接")
            else main.postDelayed(connectTimeout, CONNECT_MS)
        } catch (_: SecurityException) {
            disconnect("缺少蓝牙权限")
        }
    }

    private fun subscribe(g: BluetoothGatt) {
        try {
            val notify = g.getService(SERVICE)?.getCharacteristic(NOTIFY)
            val descriptor = notify?.getDescriptor(CCCD)
            if (notify == null || descriptor == null ||
                notify.properties and BluetoothGattCharacteristic.PROPERTY_NOTIFY == 0) {
                disconnect("设备没有 FFE5/FFE4 通知特征")
                return
            }
            val error = startInput()
            if (error != null) {
                disconnect(error)
                return
            }
            inputStarted = true
            if (!g.setCharacteristicNotification(notify, true)) {
                disconnect("启用 FFE4 通知失败")
                return
            }
            val enabled = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
            val queued = if (Build.VERSION.SDK_INT >= 33) {
                g.writeDescriptor(descriptor, enabled) == BluetoothGatt.GATT_SUCCESS
            } else {
                @Suppress("DEPRECATION")
                descriptor.value = enabled
                @Suppress("DEPRECATION")
                g.writeDescriptor(descriptor)
            }
            if (!queued) disconnect("写入 FFE4 通知描述符失败")
        } catch (_: SecurityException) {
            disconnect("缺少蓝牙权限")
        }
    }

    private fun forward(g: BluetoothGatt, value: ByteArray) {
        // 在 BLE 回调线程取时，排队后的延迟不计入接收时刻。
        val receivedNs = NativeCore.nativeImuTimeNs()
        val bytes = value.copyOf()
        main.post {
            if (g === gatt && inputStarted) pushInput(bytes, receivedNs)
        }
    }

    private val gattCallback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
            main.post {
                if (g !== gatt) return@post
                if (status != BluetoothGatt.GATT_SUCCESS || newState == BluetoothProfile.STATE_DISCONNECTED) {
                    disconnect("连接断开（状态 $status）")
                } else if (newState == BluetoothProfile.STATE_CONNECTED) {
                    try {
                        if (!g.discoverServices()) disconnect("发现 IMU 服务失败")
                    } catch (_: SecurityException) {
                        disconnect("缺少蓝牙权限")
                    }
                }
            }
        }

        override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
            main.post {
                if (g !== gatt) return@post
                if (status == BluetoothGatt.GATT_SUCCESS) subscribe(g)
                else disconnect("发现 IMU 服务失败（状态 $status）")
            }
        }

        override fun onDescriptorWrite(g: BluetoothGatt, descriptor: BluetoothGattDescriptor, status: Int) {
            main.post {
                if (g !== gatt || descriptor.uuid != CCCD || descriptor.characteristic.uuid != NOTIFY) return@post
                if (status == BluetoothGatt.GATT_SUCCESS) {
                    main.removeCallbacks(connectTimeout)
                    state = "已订阅 FFE4"
                } else {
                    disconnect("订阅 FFE4 失败（状态 $status）")
                }
            }
        }

        override fun onCharacteristicChanged(g: BluetoothGatt, c: BluetoothGattCharacteristic, value: ByteArray) {
            if (c.uuid == NOTIFY) forward(g, value)
        }

        @Deprecated("Deprecated in Java")
        override fun onCharacteristicChanged(g: BluetoothGatt, c: BluetoothGattCharacteristic) {
            @Suppress("DEPRECATION")
            if (Build.VERSION.SDK_INT < 33 && c.uuid == NOTIFY) forward(g, c.value ?: return)
        }
    }
}
