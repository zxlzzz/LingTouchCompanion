package com.lingtouch.companion

import android.Manifest
import android.app.Activity
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.ClipData
import android.content.ClipboardManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.graphics.Typeface
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.SystemClock
import android.view.View
import android.widget.Button
import android.widget.CompoundButton
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import org.json.JSONObject

/**
 * 骨架界面：USB 授权 → 打开 CS30 → 核心开流 → 读屏可读的 9×6 栅格 → 连接手柄写一帧。
 * 界面不放假数据：没连设备显示「未连接」，拿不到的值不显示。
 */
class MainActivity : Activity() {
    companion object {
        const val ACTION_USB_PERMISSION = "com.lingtouch.companion.USB_PERMISSION"
        const val CS30_VENDOR_ID = 0x2207
        const val CS30_PRODUCT_ID = 0x0016
        const val REQUEST_PERMISSIONS = 1
        const val POLL_MS = 200L
    }

    private val main = Handler(Looper.getMainLooper())
    private var service: StreamService? = null

    private lateinit var cameraText: TextView
    private lateinit var gridStatusText: TextView
    private lateinit var gridRows: List<TextView>
    private lateinit var handleText: TextView
    private lateinit var policyGroup: RadioGroup
    private lateinit var sendText: TextView
    private lateinit var continuousSwitch: Switch
    private lateinit var planeText: TextView
    private lateinit var detailText: TextView
    private lateinit var usbLogText: TextView

    private var lastFrames = -1L
    private var lastFramesAt = 0L
    private var fps = -1.0

    private val connectionToService = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName, binder: IBinder) {
            val s = (binder as StreamService.LocalBinder).service()
            service = s
            when (s.policy) {
                NativeCore.POLICY_FLAT -> policyGroup.check(idFlat)
                NativeCore.POLICY_RAISED -> policyGroup.check(idRaised)
                else -> policyGroup.clearCheck()  // 待 Hsinlung 定：不预选
            }
            continuousSwitch.isChecked = s.continuousSend
        }

        override fun onServiceDisconnected(name: ComponentName) {
            service = null
        }
    }

    private val usbReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action != ACTION_USB_PERMISSION) return
            val granted = intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false)
            val device = findCs30()
            if (!granted || device == null) {
                cameraText.text = "相机：没有得到 USB 权限"
                return
            }
            openCamera(device)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(buildUi())
        val filter = IntentFilter(ACTION_USB_PERMISSION)
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(usbReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
        else registerReceiver(usbReceiver, filter)
        bindService(Intent(this, StreamService::class.java), connectionToService, Context.BIND_AUTO_CREATE)
        requestRuntimePermissions()
    }

    override fun onResume() {
        super.onResume()
        main.post(poller)
    }

    override fun onPause() {
        super.onPause()
        main.removeCallbacks(poller)
    }

    override fun onDestroy() {
        unregisterReceiver(usbReceiver)
        unbindService(connectionToService)
        super.onDestroy()
    }

    // ---- 权限 -------------------------------------------------------------------------------

    private fun neededPermissions(): List<String> {
        val list = mutableListOf(Manifest.permission.CAMERA)  // 安卓 9 起，UVC 设备的 USB 授权要求 CAMERA 权限
        if (Build.VERSION.SDK_INT >= 31) {
            list += Manifest.permission.BLUETOOTH_SCAN
            list += Manifest.permission.BLUETOOTH_CONNECT
        } else {
            list += Manifest.permission.ACCESS_FINE_LOCATION
        }
        if (Build.VERSION.SDK_INT >= 33) list += Manifest.permission.POST_NOTIFICATIONS
        return list.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
    }

    private fun requestRuntimePermissions() {
        val missing = neededPermissions()
        if (missing.isEmpty()) startStreamService() else requestPermissions(missing.toTypedArray(), REQUEST_PERMISSIONS)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        val missing = neededPermissions()
        if (missing.isEmpty()) startStreamService()
        else detailText.text = "缺少权限：" + missing.joinToString("、") { it.substringAfterLast('.') }
    }

    // 安卓 14 起，connectedDevice 类型的前台服务要在蓝牙/USB 权限到手后才能启动
    private fun startStreamService() {
        startForegroundService(Intent(this, StreamService::class.java))
    }

    // ---- 相机 -------------------------------------------------------------------------------

    private fun findCs30(): UsbDevice? {
        val usb = getSystemService(Context.USB_SERVICE) as UsbManager
        return usb.deviceList.values.firstOrNull { it.vendorId == CS30_VENDOR_ID && it.productId == CS30_PRODUCT_ID }
    }

    private fun connectCamera() {
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestRuntimePermissions()
            return
        }
        val device = findCs30() ?: run { cameraText.text = "相机：未连接（没找到 2207:0016）"; return }
        val usb = getSystemService(Context.USB_SERVICE) as UsbManager
        if (usb.hasPermission(device)) {
            openCamera(device)
            return
        }
        val intent = Intent(ACTION_USB_PERMISSION).setPackage(packageName)
        val flags = if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0
        usb.requestPermission(device, PendingIntent.getBroadcast(this, 0, intent, flags))
        cameraText.text = "相机：等待 USB 授权"
    }

    private fun openCamera(device: UsbDevice) {
        val s = service ?: run { cameraText.text = "相机：服务还没启动"; return }
        cameraText.text = "相机：启动中（Commit 约需 2–3 秒）"
        Thread {
            val error = s.openCamera(device)
            main.post { cameraText.text = if (error == null) "相机：已开流" else "相机：开流失败：$error" }
        }.start()
    }

    // ---- 定时刷新 ----------------------------------------------------------------------------

    private val poller = object : Runnable {
        override fun run() {
            refresh()
            main.postDelayed(this, POLL_MS)
        }
    }

    private fun refresh() {
        val s = service
        if (s == null || s.handle == 0L) {
            gridStatusText.text = "栅格：未连接"
            return
        }
        cameraText.text = "相机：" + s.cameraStatus
        usbLogText.text = NativeCore.nativeUsbLog()
        handleText.text = "手柄：" + s.handleLink.state
        renderGrid(JSONObject(NativeCore.nativeGridJson(s.handle)))
        val stats = JSONObject(NativeCore.nativeStatsJson(s.handle))
        val frames = stats.getLong("frames_processed")
        val now = SystemClock.elapsedRealtime()
        if (lastFrames >= 0 && now - lastFramesAt >= 2000) {
            fps = (frames - lastFrames) * 1000.0 / (now - lastFramesAt)
            lastFrames = frames
            lastFramesAt = now
        } else if (lastFrames < 0) {
            lastFrames = frames
            lastFramesAt = now
        }
        val streaming = NativeCore.nativeCameraStreaming(s.handle)
        val lines = mutableListOf<String>()
        if (streaming && fps >= 0) lines += "处理帧率 %.1f 帧/秒（实测，最近 2 秒）".format(fps)
        lines += "拼帧 ${stats.getLong("frames")}，丢弃不完整 ${stats.getLong("incomplete")}，" +
            "包错误 ${stats.getLong("packet_errors")}，UVC 错误位 ${stats.getLong("uvc_errors")}，" +
            "计算忙时替换 ${stats.getLong("frames_dropped_busy")}，上一帧计算 ${stats.getDouble("last_process_ms")} ms"
        lines += "已发帧 ${s.framesSent}，手柄确认刷新 ${s.framesShown}" +
            (if (s.lastFrameHex.isNotEmpty()) "，最后一帧 ${s.lastFrameHex}" else "")
        if (s.lastLog.isNotEmpty()) lines += s.lastLog
        lines += NativeCore.nativeDeviceSummary(s.handle)
        detailText.text = lines.joinToString("\n")
    }

    private fun renderGrid(g: JSONObject) {
        val status = g.getString("status")
        gridStatusText.text = when (status) {
            "ok" -> {
                val ground = g.getJSONObject("ground")
                "栅格：正常（离地 %.2f m，俯仰 %.0f°）".format(ground.getDouble("height_m"), ground.getDouble("pitch_deg"))
            }
            "ground_fit_failed" -> "栅格：降级，整张为未知（地面拟合失败：${g.getString("failure")}）"
            "no_calibration" -> "栅格：没有可用内参（${g.getString("failure")}）"
            else -> "栅格：未连接"
        }
        val cells = if (g.isNull("cells")) null else g.getString("cells")
        for (row in 0 until 6) {
            val far = 3.4 - 0.4 * row
            val label = "第 ${row + 1} 行（%.1f 到 %.1f 米）".format(far - 0.4, far)
            val view = gridRows[row]
            if (cells == null) {
                view.text = "—"
                view.contentDescription = "$label：无数据"
                continue
            }
            val part = cells.substring(row * 9, row * 9 + 9)
            view.text = part.map { symbol(it) }.joinToString(" ")
            view.contentDescription = label + "：" + part.map { word(it) }.joinToString("，")
        }
    }

    private fun symbol(c: Char) = when (c) { '0' -> '·'; '1' -> '■'; else -> '?' }
    private fun word(c: Char) = when (c) { '0' -> "空"; '1' -> "障碍"; else -> "未知" }

    // ---- 界面 -------------------------------------------------------------------------------

    private val idFlat = View.generateViewId()
    private val idRaised = View.generateViewId()

    private fun buildUi(): View {
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 32, 32, 32)
        }
        fun text(size: Float = 16f, mono: Boolean = false) = TextView(this).apply {
            textSize = size
            if (mono) typeface = Typeface.MONOSPACE
            column.addView(this)
        }
        fun button(label: String, onClick: () -> Unit) = Button(this).apply {
            text = label
            setOnClickListener { onClick() }
            column.addView(this)
        }

        text(22f).text = "灵触 · 端侧骨架"
        cameraText = text()
        cameraText.text = "相机：未连接"
        button("连接相机（CS30）") { connectCamera() }
        button("断开相机") { service?.closeCamera() }

        gridStatusText = text()
        gridStatusText.text = "栅格：未连接"
        text(13f).text = "从远到近 6 行、从左到右 9 列；· 空  ■ 障碍  ? 未知（相机视角，未做穿戴镜像）"
        gridRows = (0 until 6).map { text(24f, mono = true).apply { text = "—" } }

        handleText = text()
        handleText.text = "手柄：未连接"
        button("扫描并连接手柄") { service?.handleLink?.scanAndConnect() }

        text().text = "未知（状态 2）在触点上表示为：（待 Hsinlung 定，每次需手选）"
        policyGroup = RadioGroup(this).apply {
            orientation = RadioGroup.HORIZONTAL
            addView(RadioButton(context).apply { id = idFlat; text = "平" })
            addView(RadioButton(context).apply { id = idRaised; text = "凸" })
            setOnCheckedChangeListener { _, checked ->
                service?.policy = when (checked) {
                    idFlat -> NativeCore.POLICY_FLAT
                    idRaised -> NativeCore.POLICY_RAISED
                    else -> NativeCore.POLICY_UNSET
                }
            }
            column.addView(this)
        }
        sendText = text()
        button("发送一帧到手柄") {
            val s = service
            val error = if (s == null) "服务还没启动" else s.sendLatest()
            sendText.text = if (error == null) "已发出，等待手柄刷新完成" else "没有发送：$error"
        }
        continuousSwitch = Switch(this).apply {
            text = "持续发送（后台测试用）"
            setOnCheckedChangeListener { _: CompoundButton, on: Boolean -> service?.continuousSend = on }
            column.addView(this)
        }

        button("平面检查（对着平整的墙或斜看地面）") {
            val s = service ?: return@button
            planeText.text = "计算中…"
            Thread {
                val report = NativeCore.nativePlaneCheck(s.handle)
                main.post { planeText.text = report }
            }.start()
        }
        planeText = text(13f, mono = true)
        // 真机验收第 1、3 条：帧文件放在 /sdcard/Android/data/com.lingtouch.companion/files/
        button("保存当前帧（latest_frame.bin）") {
            val s = service ?: return@button
            val file = java.io.File(getExternalFilesDir(null), "latest_frame.bin")
            val error = NativeCore.nativeSaveLatestFrame(s.handle, file.absolutePath)
            planeText.text = if (error == null) "已保存：${file.absolutePath}" else "没有保存：$error"
        }
        button("核对帧文件（frame.bin → 栅格与摘要）") {
            val s = service ?: return@button
            val file = java.io.File(getExternalFilesDir(null), "frame.bin")
            val g = JSONObject(NativeCore.nativeProcessFrameFile(s.handle, file.absolutePath))
            planeText.text = if (g.has("error")) "核对失败：${g.getString("error")}（${file.absolutePath}）"
            else "${file.name}：${g.getString("status")}，摘要 ${g.getString("digest")}\n" +
                (0 until 6).joinToString("\n") { g.getString("cells").substring(it * 9, it * 9 + 9) }
        }
        button("复位相机（release 后重开仍失败时）") {
            val s = service
            val error = if (s == null) "服务还没启动" else s.resetCamera()
            cameraText.text = if (error == null) "相机：已复位，请重新连接" else "相机：复位失败：$error"
        }
        detailText = text(13f)
        button("复制诊断信息") {
            val usb = getSystemService(Context.USB_SERVICE) as UsbManager
            val devices = usb.deviceList.values.joinToString("\n") {
                "%s %04x:%04x USB %s，%d 个接口".format(it.deviceName, it.vendorId, it.productId, it.version, it.interfaceCount)
            }
            val report = "${Build.MANUFACTURER} ${Build.MODEL}，安卓 ${Build.VERSION.RELEASE}\n" +
                "相机：${service?.cameraStatus}\nUSB 设备：\n$devices\n日志：\n${NativeCore.nativeUsbLog()}"
            val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            clipboard.setPrimaryClip(ClipData.newPlainText("灵触诊断", report))
            planeText.text = "已复制，可直接粘贴发出"
        }
        usbLogText = text(12f, mono = true)
        button("显示当前参数") { planeText.text = service?.let { NativeCore.nativeConfigText(it.handle) } ?: "" }

        return ScrollView(this).apply { addView(column) }
    }
}
