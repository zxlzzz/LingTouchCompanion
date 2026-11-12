package com.lingtouch.cs30live

import android.Manifest
import android.app.Activity
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.graphics.Color
import android.hardware.usb.UsbManager
import android.hardware.usb.UsbDevice
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.WindowManager
import android.widget.*
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : Activity() {
    companion object {
        const val ID_DEVICES = 1001
        const val ID_CONNECT = 1002
        const val ID_DISCONNECT = 1003
        const val ID_MANUAL = 1004
        const val ID_AUTO = 1005
        const val ID_SAMPLE = 1006
        const val ID_START = 1007
        const val ID_STOP = 1008
        const val ID_K = 1009
        const val ID_EXPORT = 1010
        const val ID_GRID = 1011
        const val ID_STATUS = 1012
        const val ID_RGBD_REPLAY = 1016
        private const val CAMERA_PERMISSION = 41
        private const val SAVE_JSON = 42
    }
    lateinit var backend: CameraBackend
        private set
    lateinit var controller: CaptureController
        private set
    private lateinit var devices: Spinner
    private lateinit var connect: Button
    private lateinit var disconnect: Button
    private lateinit var manual: RadioButton
    private lateinit var automatic: RadioButton
    private lateinit var sample: Button
    private lateinit var start: Button
    private lateinit var stop: Button
    private lateinit var export: Button
    private lateinit var status: TextView
    private lateinit var record: TextView
    private lateinit var kLabel: TextView
    private lateinit var diagnostics: TextView
    private lateinit var grid: DotGridView
    private var choices = emptyList<DeviceChoice>()
    private var lastDiscoveryLog: String? = null
    private var selectedSnapshot: DeviceChoice? = null
    private var pendingPermission: Int? = null
    private var pendingJson: String? = null
    private var autoMode = false
    var kValue = 3
        private set
    private var permissionMessage: String? = null
    private val clockFormat = SimpleDateFormat("HH:mm:ss.SSS", Locale.CHINA)
    private val discoveryHandler = Handler(Looper.getMainLooper())
    private val scanForCamera = object : Runnable {
        override fun run() {
            val state = controller.state
            if (!state.connected && !state.connecting && pendingPermission == null) {
                refreshDevices()
            }
            discoveryHandler.postDelayed(this, 1000L)
        }
    }

    private val usbReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            when (intent.action) {
                UsbCameraBackend.ACTION_PERMISSION -> {
                    val id = pendingPermission ?: return
                    if (intent.getIntExtra(UsbCameraBackend.REQUESTED_DEVICE, -1) != id) return
                    pendingPermission = null
                    if (backend.hasPermission(id)) { permissionMessage = null; controller.connect(id) }
                    else { permissionMessage = "未获得 USB 权限，请点“连接设备”重试"; render(controller.state) }
                }
                UsbManager.ACTION_USB_DEVICE_ATTACHED, UsbManager.ACTION_USB_DEVICE_DETACHED -> {
                    val changed = broadcastDevice(intent)
                    backend.noteUsbEvent("Android USB event=${intent.action}, eventDevice=${changed?.deviceId}, activeDevice=${controller.state.deviceId}")
                    if (changed != null && changed.vendorId == 0x2207 && changed.productId == 0x0016) {
                        if (intent.action == UsbManager.ACTION_USB_DEVICE_DETACHED) {
                            handleCs30Detached(changed.deviceId)
                            return
                        }
                        backend.usbAttached(changed.deviceId)
                    }
                    refreshDevices()
                }
            }
        }
    }

    @Suppress("DEPRECATION")
    private fun broadcastDevice(intent: Intent): UsbDevice? = if (Build.VERSION.SDK_INT >= 33)
        intent.getParcelableExtra(UsbManager.EXTRA_DEVICE, UsbDevice::class.java)
    else intent.getParcelableExtra(UsbManager.EXTRA_DEVICE)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        kValue = savedInstanceState?.getInt("k")?.coerceIn(1,16) ?: 3
        pendingJson = savedInstanceState?.getString("pending_json")
        backend = AppDependencies.factory(applicationContext)
        controller = CaptureController(backend) { render(it) }
        setContentView(buildUi())
        val permission = IntentFilter(UsbCameraBackend.ACTION_PERMISSION)
        val changes = IntentFilter().apply { addAction(UsbManager.ACTION_USB_DEVICE_ATTACHED); addAction(UsbManager.ACTION_USB_DEVICE_DETACHED) }
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(usbReceiver, permission, Context.RECEIVER_NOT_EXPORTED)
            registerReceiver(usbReceiver, changes, Context.RECEIVER_EXPORTED)
        } else {
            registerReceiver(usbReceiver, permission)
            registerReceiver(usbReceiver, changes)
        }
        refreshDevices()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        if (intent.action == UsbManager.ACTION_USB_DEVICE_ATTACHED) {
            broadcastDevice(intent)?.let { backend.usbAttached(it.deviceId) }
        }
        refreshDevices()
    }
    override fun onResume() {
        super.onResume()
        refreshDevices()
        discoveryHandler.postDelayed(scanForCamera, 1000L)
    }
    override fun onPause() {
        discoveryHandler.removeCallbacks(scanForCamera)
        super.onPause()
    }
    override fun onStop() {
        controller.stop("已暂停（应用进入后台），保留最后结果")
        super.onStop()
    }
    override fun onDestroy() {
        pendingPermission = null
        unregisterReceiver(usbReceiver)
        controller.close()
        super.onDestroy()
    }

    internal fun handleCs30Detached(id: Int) {
        backend.usbDetached(id)
        choices = choices.filterNot { it.id == id }
        if (selectedSnapshot?.id == id) selectedSnapshot = null
        if (pendingPermission == id) {
            pendingPermission = null
            permissionMessage = "CS30 已拔出，重新插入后请选择设备"
        }
        val state = controller.state
        if (state.deviceId == id && (state.connected || state.connecting)) {
            controller.disconnect("CS30 已拔出，重新插入后请选择设备")
        }
        refreshDevices()
    }

    fun refreshDevices() {
        val result = runCatching { backend.devices() }
        val discovery = if (result.isSuccess) {
            choices = result.getOrThrow()
            "Android USB device list: " + choices.joinToString { it.label }.ifEmpty { "empty" }
        } else {
            "Android USB device-list query failed: ${result.exceptionOrNull()?.message}"
        }
        if (discovery != lastDiscoveryLog) {
            backend.noteUsbEvent(discovery)
            lastDiscoveryLog = discovery
        }
        val state = controller.state
        val activeId = state.deviceId?.takeIf { state.connected || state.connecting } ?: pendingPermission
        if (activeId != null && choices.none { it.id == activeId })
            backend.noteUsbEvent("USB device-list omitted active id=$activeId, connecting=${state.connecting}; native stream remains authoritative")
        // Discovery is not connection liveness. Keep native polling authoritative.
        render(state)
    }

    private fun syncDeviceChoices(state: CaptureState) {
        val previous = (devices.selectedItem as? DeviceChoice)?.id
        val activeId = state.deviceId?.takeIf { state.connected || state.connecting } ?: pendingPermission
        val pinned = selectedSnapshot?.takeIf { it.id == activeId && choices.none { item -> item.id == activeId } }
        val available = choices + listOfNotNull(pinned)
        val options = if (available.isEmpty()) listOf(DeviceChoice(-1, "未发现 USB 设备 · 正在查找", false)) else available
        val existing = (0 until devices.count).map { devices.getItemAtPosition(it) as? DeviceChoice }
        if (existing != options) devices.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, options)
        val selected = options.indexOfFirst { it.id == (activeId ?: previous) }
        val index = if (selected >= 0) selected else 0
        if (devices.selectedItemPosition != index) devices.setSelection(index)
    }

    private fun requestConnection() {
        val choice = devices.selectedItem as? DeviceChoice ?: return
        if (choice.id < 0) { permissionMessage = "未发现设备，请检查 CS30 接线或 OTG"; render(controller.state); return }
        if (!choice.supported) { permissionMessage = "所选设备不是 CS30，请选择 2207:0016 的设备"; render(controller.state); return }
        selectedSnapshot = choice
        pendingPermission = choice.id
        permissionMessage = null
        if (backend.needsCameraPermission && checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.CAMERA), CAMERA_PERMISSION)
        } else requestUsb(choice.id)
    }

    private fun requestUsb(id: Int) {
        if (backend.hasPermission(id)) {
            pendingPermission = null; permissionMessage = null; controller.connect(id)
        } else {
            permissionMessage = "请在系统弹窗中允许访问所选 CS30"
            try { backend.requestPermission(id) } catch (e: Exception) { pendingPermission = null; permissionMessage = e.message }
            render(controller.state)
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != CAMERA_PERMISSION) return
        val id = pendingPermission ?: return
        if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) requestUsb(id)
        else { pendingPermission = null; permissionMessage = "CS30 视频设备需要相机权限，请允许后重试"; render(controller.state) }
    }

    private fun begin(mode: Int) { permissionMessage = null; controller.start(mode) }

    private fun saveJson() {
        val frame = controller.state.frame ?: return
        if (!frame.valid) return
        pendingJson = frame.json(kValue)
        val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "application/json"
            putExtra(Intent.EXTRA_TITLE, "cs30_${SimpleDateFormat("yyyyMMdd_HHmmss", Locale.ROOT).format(Date(frame.capturedAtMs))}_frame${frame.id}_k${kValue}.json")
        }
        startActivityForResult(intent, SAVE_JSON)
    }

    private fun saveDiagnostics() {
        val state = controller.state
        controller.collectDiagnostics { fresh ->
            pendingJson = "CS30 Fusion 2.0\n${Build.MANUFACTURER} ${Build.MODEL}; Android ${Build.VERSION.RELEASE}\n" +
                "${state.message}\n$fresh\n${state.frame?.diagnostics ?: ""}"
            startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE); type="text/plain"
                putExtra(Intent.EXTRA_TITLE,"cs30_usb_diagnostics.txt")
            }, SAVE_JSON)
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putInt("k", kValue); outState.putString("pending_json", pendingJson)
        super.onSaveInstanceState(outState)
    }
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != SAVE_JSON) return
        val frozen = pendingJson; pendingJson = null
        if (resultCode != RESULT_OK || frozen == null || data?.data == null) return
        try {
            checkNotNull(contentResolver.openOutputStream(data.data!!, "wt")).use { it.write(frozen.toByteArray(Charsets.UTF_8)) }
            Toast.makeText(this, "已保存", Toast.LENGTH_SHORT).show()
        } catch (e: Exception) { Toast.makeText(this, "保存失败：${e.message}", Toast.LENGTH_LONG).show() }
    }

    private fun render(state: CaptureState) {
        if (!::grid.isInitialized || isFinishing) return
        syncDeviceChoices(state)
        status.text = permissionMessage ?: state.message
        devices.isEnabled = !state.connecting && !state.connected && pendingPermission == null
        (devices.selectedView as? TextView)?.setTextColor(Color.BLACK)
        connect.isEnabled = choices.isNotEmpty() && !state.connecting && !state.connected && pendingPermission == null
        disconnect.isEnabled = state.connected || state.connecting
        manual.isEnabled = !state.connecting
        automatic.isEnabled = !state.connecting
        sample.visibility = if (autoMode) View.GONE else View.VISIBLE
        start.visibility = if (autoMode) View.VISIBLE else View.GONE
        stop.visibility = if (autoMode) View.VISIBLE else View.GONE
        sample.isEnabled = state.connected && state.mode == 0
        start.isEnabled = state.connected && state.mode == 0
        stop.isEnabled = state.mode != 0
        val frame = state.frame
        grid.show(frame, kValue)
        kLabel.text = "K = $kValue / 16"
        export.isEnabled = frame?.valid == true
        record.text = if (frame == null) "尚未采集 · 上远下近，左至右" else {
            val lit = frame.bits(kValue).sum()
            "第 ${frame.id} 帧 · ${clockFormat.format(Date(frame.capturedAtMs))} · %.1f ms\n".format(frame.processMs) +
                if (frame.valid) "$lit / 54 点亮 · ${if (state.mode == 2) "实时更新" else "保留当前结果"}" else "当前帧无有效点阵，不能导出"
        }
        diagnostics.text = listOf(state.transportLog, frame?.diagnostics ?: "暂无帧数据。首次连接需要读取相机标定，通常等待几秒。")
            .filter { it.isNotEmpty() }.joinToString("\n")
        if (state.mode == 2) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }

    private fun buildUi(): View {
        val dp = resources.displayMetrics.density
        fun dip(v: Int) = (v*dp).toInt()
        val column = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dip(20),dip(16),dip(20),dip(24)); setBackgroundColor(Color.WHITE) }
        fun label(value: String = "", size: Float = 15f): TextView = TextView(this).apply {
            text = value; textSize = size; setTextColor(Color.BLACK); setPadding(0,dip(4),0,dip(4)); column.addView(this)
        }
        fun row() = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; column.addView(this) }
        fun button(parent: LinearLayout, title: String, identifier: Int, action: () -> Unit) = Button(this).apply {
            id = identifier; text = title; isAllCaps = false
            setOnClickListener { action() }; parent.addView(this, LinearLayout.LayoutParams(0,dip(48),1f))
        }
        label("CS30 实时深度点阵", 25f)
        button(row(), "RGB-D 回放", ID_RGBD_REPLAY) {
            startActivity(Intent(this, RgbdReplayActivity::class.java))
        }
        label("USB 设备", 14f)
        devices = Spinner(this).apply { id = ID_DEVICES; column.addView(this, LinearLayout.LayoutParams(-1,dip(48))) }
        val connectionRow = row()
        button(connectionRow,"刷新",1013) {
            if (!controller.state.connected && !controller.state.connecting) pendingPermission = null
            permissionMessage = null; refreshDevices()
        }
        connect = button(connectionRow,"连接设备",ID_CONNECT) { requestConnection() }
        disconnect = button(connectionRow,"断开",ID_DISCONNECT) { permissionMessage = null; controller.disconnect(); refreshDevices() }
        status = label().apply { id = ID_STATUS }
        val modes = RadioGroup(this).apply { orientation = RadioGroup.HORIZONTAL; column.addView(this) }
        manual = RadioButton(this).apply { id = ID_MANUAL; text = "手动模式"; modes.addView(this) }
        automatic = RadioButton(this).apply { id = ID_AUTO; text = "自动模式 · 2 次/秒"; modes.addView(this) }
        manual.isChecked = true
        modes.setOnCheckedChangeListener { _, id ->
            controller.stop("模式已切换，保留最后结果")
            autoMode = id == ID_AUTO; render(controller.state)
        }
        val captureRow = row()
        sample = button(captureRow,"采集一次",ID_SAMPLE) { begin(1) }
        start = button(captureRow,"开始",ID_START) { begin(2) }
        stop = button(captureRow,"停止",ID_STOP) { controller.stop() }
        record = label("尚未采集",14f)
        grid = DotGridView(this).apply { id = ID_GRID; column.addView(this,LinearLayout.LayoutParams(-1,-2)) }
        kLabel = label("K = $kValue / 16",16f)
        column.addView(SeekBar(this).apply {
            id = ID_K; max = 15; progress = kValue-1
            setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) { kValue=progress+1; render(controller.state) }
                override fun onStartTrackingTouch(seekBar: SeekBar?) {}
                override fun onStopTrackingTouch(seekBar: SeekBar?) {}
            })
        })
        label("黑点：障碍小格数达到 K。空心点包含未知区域。",12f)
        export = button(row(),"导出当前点阵 JSON",ID_EXPORT) { saveJson() }
        val info = label("查看诊断信息",13f)
        diagnostics = label("",12f).apply { visibility=View.GONE }
        button(row(),"导出 USB 诊断日志",1014) { saveDiagnostics() }
        info.setOnClickListener {
            diagnostics.visibility=if(diagnostics.visibility==View.GONE)View.VISIBLE else View.GONE
            if (diagnostics.visibility==View.VISIBLE) controller.collectDiagnostics { diagnostics.text=it }
        }
        // Keep Start/Stop reachable while the user scrolls the grid or adjusts K.
        column.removeView(captureRow)
        captureRow.setPadding(dip(16),dip(4),dip(16),dip(4))
        captureRow.setBackgroundColor(Color.WHITE)
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.WHITE)
            addView(ScrollView(context).apply { isFillViewport=true; addView(column) },LinearLayout.LayoutParams(-1,0,1f))
            addView(View(context).apply { setBackgroundColor(0xFFDDDDDD.toInt()) },LinearLayout.LayoutParams(-1,dip(1)))
            addView(captureRow,LinearLayout.LayoutParams(-1,dip(56)))
        }
    }
}
