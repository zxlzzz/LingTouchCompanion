package com.lingtouch.cs30live

import android.app.Activity
import android.app.Instrumentation
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Bitmap
import android.net.Uri
import android.os.Bundle
import android.os.SystemClock
import android.widget.Button
import android.widget.RadioButton
import android.widget.SeekBar
import android.widget.Spinner
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

object NativeSimulator {
    init { System.loadLibrary("cs30_live_test") }
    @JvmStatic external fun create(): Long
    @JvmStatic external fun configure(blob: ByteArray)
    @JvmStatic external fun open(handle: Long, fd: Int): String?
    @JvmStatic external fun acquire(handle: Long, mode: Int): String?
    @JvmStatic external fun poll(handle: Long): String
    @JvmStatic external fun disconnect(handle: Long): String?
    @JvmStatic external fun destroy(handle: Long)
    @JvmStatic external fun feed(raw: ByteArray, fid: Int)
    @JvmStatic external fun unplug()
    @JvmStatic external fun forceClaim(id: Int, force: Boolean): Boolean
    @JvmStatic external fun javaRelease(id: Int): Boolean
    @JvmStatic external fun policyReport(): String
    @JvmStatic external fun transportCheck(blob: ByteArray): String
}

class SimulatedBackend(private val tests: Instrumentation) : CameraBackend {
    private val assets = tests.context.assets
    private val blob = assets.open("calibration.bin").use { it.readBytes() }
    private val frames = (0..3).map { assets.open("frame$it.raw").use { stream -> stream.readBytes() } }
    private val empty = ByteArray(614400)
    @Volatile var frameIndex = 0
    @Volatile var feedEnabled = true
    @Volatile var available = true
    @Volatile var permission = true
    @Volatile var enumerationMode = 0 // 1=temporary empty, 2=temporary query exception
    @Volatile var connectedId = -1
    @Volatile var handle = 0L
    private var producer: java.util.concurrent.ScheduledExecutorService? = null
    override val needsCameraPermission = false
    override fun devices(): List<DeviceChoice> {
        if(enumerationMode==2)error("Temporary USB device-list query failure")
        return if (available && enumerationMode==0) listOf(DeviceChoice(42,"测试 CS30 A · 模拟 USB",true),
        DeviceChoice(43,"测试 CS30 B · 模拟 USB",true),DeviceChoice(44,"其他 USB 设备",false)) else emptyList()
    }
    override fun hasPermission(id: Int) = permission && available
    override fun requestPermission(id: Int) {}
    override fun connect(id: Int) {
        disconnect()
        NativeSimulator.configure(blob)
        UsbClaims.forceAll(listOf(0,1,1), { NativeSimulator.forceClaim(it,true) },
            { NativeSimulator.javaRelease(it) }, { "simulated interface=$it" }, {})
        if (handle == 0L) handle = NativeSimulator.create()
        check(NativeSimulator.open(handle, id) == null)
        connectedId = id
        var fid = 0
        producer = Executors.newSingleThreadScheduledExecutor().also { p ->
            p.scheduleWithFixedDelay({ if (feedEnabled) { NativeSimulator.feed(if(frameIndex < 0) empty else frames[frameIndex],fid);fid=1-fid } },0,55,TimeUnit.MILLISECONDS)
        }
    }
    override fun acquire(mode: Int) { check(NativeSimulator.acquire(handle,mode)==null) }
    override fun poll() = NativeSimulator.poll(handle)
    fun stats() = JSONObject(poll()).getJSONObject("stats")
    override fun disconnect() {
        producer?.shutdownNow();producer?.awaitTermination(2,TimeUnit.SECONDS);producer=null
        if(handle!=0L)check(NativeSimulator.disconnect(handle)==null)
        connectedId = -1
    }
    override fun close() { disconnect();if(handle!=0L)NativeSimulator.destroy(handle);handle=0 }
}

class LiveCheck : Instrumentation() {
    private val checks = mutableListOf<String>()
    private lateinit var activity: MainActivity
    private lateinit var source: SimulatedBackend
    private fun verify(value: Boolean, message: String) { check(value) { message }; checks.add(message) }
    private fun waitFor(message: String, timeoutMs: Long = 6000, condition: () -> Boolean) {
        val end=SystemClock.elapsedRealtime()+timeoutMs
        while(SystemClock.elapsedRealtime()<end) { if(condition())return;Thread.sleep(25) }
        error("Timeout: $message; ${if(::activity.isInitialized)activity.controller.state else "no activity"}")
    }
    private fun click(id: Int) { runOnMainSync { activity.findViewById<android.view.View>(id).performClick() };waitForIdleSync() }
    private fun screenshot(name: String) {
        waitForIdleSync()
        uiAutomation.takeScreenshot()?.let { image ->
            File(activity.getExternalFilesDir(null),name).outputStream().use { image.compress(Bitmap.CompressFormat.PNG,100,it) }
            image.recycle()
        }
    }
    override fun onCreate(arguments: Bundle?) { super.onCreate(arguments);start() }
    override fun onStart() {
        val result=Bundle()
        File(targetContext.getExternalFilesDir(null),"validation.json").delete()
        try {
            val transport = JSONObject(NativeSimulator.transportCheck(context.assets.open("calibration.bin").use { it.readBytes() }))
            verify(transport.getBoolean("passed"),"USB BUSY, rapid callbacks, delayed cancellation, failed release and partial submit regressions pass")
            val claimed=mutableListOf<Int>();val released=mutableListOf<Int>()
            UsbClaims.forceAll(listOf(0,1,1),{claimed.add(it);true},{released.add(it);true},{"interface=$it"},{})
            verify(claimed==listOf(0,1),"Java claims each interface once despite duplicate alternate settings")
            claimed.clear();released.clear()
            val partial=runCatching { UsbClaims.forceAll(listOf(0,1),{claimed.add(it);it==0},{released.add(it);true},{"interface=$it"},{}) }
            verify(partial.isFailure&&released==listOf(0),"Failed Java interface claim rolls back previously claimed interfaces")
            source=SimulatedBackend(this)
            AppDependencies.factory={source}
            activity=startActivitySync(Intent(targetContext,MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as MainActivity
            waitForIdleSync()
            verify(activity.findViewById<Spinner>(MainActivity.ID_DEVICES).count==3,"Dropdown lists multiple devices")
            runOnMainSync { activity.findViewById<Spinner>(MainActivity.ID_DEVICES).setSelection(1) }
            click(MainActivity.ID_CONNECT)
            source.enumerationMode=1
            runOnMainSync { activity.refreshDevices() }
            verify(activity.controller.state.connecting || activity.controller.state.connected,"Temporary empty device list does not cancel an opening connection")
            source.enumerationMode=2
            runOnMainSync { activity.refreshDevices() }
            verify(activity.controller.state.connecting || activity.controller.state.connected,"Enumeration exception does not cancel an opening connection")
            waitFor("connect selected device") { activity.controller.state.connected }
            runOnMainSync {
                check((activity.findViewById<Spinner>(MainActivity.ID_DEVICES).selectedItem as DeviceChoice).id==43)
            }
            verify(activity.controller.state.connected,"Selected device remains pinned while enumeration is unavailable")
            source.enumerationMode=0
            runOnMainSync { activity.refreshDevices() }
            verify(source.connectedId==43,"Selected CS30 B is the device opened")
            verify(JSONObject(NativeSimulator.policyReport()).getInt("auto_detach_enables")==0,"Wrapped fd never enables native auto-detach after Java force claim")
            Thread.sleep(650)
            verify(source.stats().getLong("frames")>0 && source.stats().getLong("frames_processed")==0L,
                "Connected but idle receives transport frames without running geometry")
            verify(activity.kValue==3,"Default K is 3")

            var comparisons=0
            for(index in 0..3) {
                source.frameIndex=index;Thread.sleep(120)
                val before=activity.controller.state.delivered
                click(MainActivity.ID_SAMPLE)
                waitFor("manual frame $index") { activity.controller.state.delivered==before+1 && activity.controller.state.mode==0 }
                val frame=checkNotNull(activity.controller.state.frame)
                val expected=JSONObject(context.assets.open("frame$index.json").bufferedReader().use { it.readText() }).getJSONArray("thresholds")
                verify(frame.valid,"Manual fixture $index yields a valid ground reference")
                for(k in 1..16) {
                    val actual=JSONArray(frame.json(k));val reference=expected.getJSONArray(k-1)
                    for(r in 0..5)for(c in 0..8) {
                        check(actual.getJSONArray(r).getInt(c)==reference.getJSONArray(r).getInt(c))
                        comparisons++
                    }
                }
                val processed=source.stats().getLong("frames_processed")
                Thread.sleep(620)
                verify(activity.controller.state.delivered==before+1 && source.stats().getLong("frames_processed")==processed,
                    "Manual click $index processes exactly one frame and then remains idle")
            }
            verify(comparisons==3456,"All 3456 threshold bits match the independently verified fixtures")
            runOnMainSync { activity.findViewById<SeekBar>(MainActivity.ID_K).progress=5 }
            verify(activity.kValue==6,"K slider changes the displayed threshold")

            click(MainActivity.ID_AUTO)
            val startCount=activity.controller.state.delivered
            val startMs=SystemClock.elapsedRealtime()
            click(MainActivity.ID_START)
            source.enumerationMode=1
            runOnMainSync { activity.refreshDevices() }
            Thread.sleep(2200)
            verify(activity.controller.state.connected && activity.controller.state.mode==2,"Automatic capture continues when the discovery list temporarily omits an active device")
            source.enumerationMode=0
            runOnMainSync { activity.refreshDevices() }
            click(MainActivity.ID_STOP)
            val acquired=activity.controller.state.delivered-startCount
            val elapsed=SystemClock.elapsedRealtime()-startMs
            verify(acquired in 4..6,"Automatic mode delivers about 2 frames/s ($acquired frames in $elapsed ms)")
            val frozen=checkNotNull(activity.controller.state.frame).json(activity.kValue)
            val frozenId=activity.controller.state.frame!!.id
            val frozenCount=activity.controller.state.delivered
            Thread.sleep(180)
            val stoppedProcessed=source.stats().getLong("frames_processed")
            source.frameIndex=0;Thread.sleep(950)
            verify(activity.controller.state.frame!!.id==frozenId && activity.controller.state.delivered==frozenCount &&
                activity.controller.state.frame!!.json(activity.kValue)==frozen,"Stop freezes the exact final displayed result")
            verify(source.stats().getLong("frames_processed")==stoppedProcessed,"Stopped mode performs no further geometry processing")
            screenshot("cs30-live-stopped.png")
            repeat(3) {
                runOnMainSync {
                    activity.findViewById<Button>(MainActivity.ID_START).performClick()
                    activity.findViewById<Button>(MainActivity.ID_STOP).performClick()
                }
            }
            Thread.sleep(700)
            verify(activity.controller.state.delivered==frozenCount && activity.controller.state.frame!!.json(activity.kValue)==frozen,
                "Immediate Start/Stop cancels late results and preserves the displayed frame")

            // The actual export button and Activity result handler write the frozen JSON.
            val destination=File(activity.getExternalFilesDir(null),"ui-export.json")
            destination.writeText("")
            val filter=IntentFilter(Intent.ACTION_CREATE_DOCUMENT).apply { addCategory(Intent.CATEGORY_OPENABLE);addDataType("application/json") }
            val monitor=addMonitor(filter,ActivityResult(Activity.RESULT_OK,Intent().setData(Uri.fromFile(destination))),true)
            click(MainActivity.ID_EXPORT)
            waitFor("export saved") { destination.length()>5 }
            removeMonitor(monitor)
            verify(JSONArray(destination.readText()).toString()==JSONArray(frozen).toString(),"Export button saves the frozen 6x9 JSON at the selected K")
            val diagnosticsFile=File(activity.getExternalFilesDir(null),"usb-diagnostics.txt")
            diagnosticsFile.writeText("")
            val logsFilter=IntentFilter(Intent.ACTION_CREATE_DOCUMENT).apply { addCategory(Intent.CATEGORY_OPENABLE);addDataType("text/plain") }
            val logsMonitor=addMonitor(logsFilter,ActivityResult(Activity.RESULT_OK,Intent().setData(Uri.fromFile(diagnosticsFile))),true)
            click(1014)
            waitFor("USB diagnostics saved") { diagnosticsFile.length()>10 }
            removeMonitor(logsMonitor)
            verify(diagnosticsFile.readText().contains("auto_detach=0"),"USB diagnostics export records the actual native claim policy")

            click(MainActivity.ID_START)
            waitFor("auto resumes with a fresh frame") { activity.controller.state.delivered>frozenCount }
            click(MainActivity.ID_MANUAL)
            val switched=activity.controller.state.delivered
            Thread.sleep(750)
            verify(activity.controller.state.mode==0 && activity.controller.state.delivered==switched,"Switching mode stops automatic acquisition")

            // A source with no packets must time out without reusing the old snapshot.
            source.feedEnabled=false;Thread.sleep(150)
            val old=activity.controller.state.delivered
            click(MainActivity.ID_SAMPLE)
            waitFor("missing-frame timeout",6500) { activity.controller.state.mode==0 }
            verify(activity.controller.state.delivered==old && activity.controller.state.message.contains("5 秒"),"Missing fresh frame times out without replaying cached results")
            source.frameIndex=-1;source.feedEnabled=true;Thread.sleep(220)
            click(MainActivity.ID_SAMPLE)
            waitFor("invalid depth") { activity.controller.state.delivered==old+1 }
            waitForIdleSync() // state is published just before its main-thread renderer runs.
            val invalidFrame=activity.controller.state.frame
            verify(invalidFrame?.valid==false,"Zero-depth fixture is reported invalid (frame=${invalidFrame?.id}, valid=${invalidFrame?.valid})")
            var invalidExportEnabled=true
            runOnMainSync { invalidExportEnabled=activity.findViewById<Button>(MainActivity.ID_EXPORT).isEnabled }
            verify(!invalidExportEnabled,"Invalid depth disables JSON export")
            source.frameIndex=2;Thread.sleep(120)
            click(MainActivity.ID_SAMPLE)
            waitFor("valid frame restored") { activity.controller.state.frame?.valid==true }
            val beforeUnplug=activity.controller.state.frame!!.json(6)
            source.available=false;NativeSimulator.unplug()
            runOnMainSync { activity.refreshDevices() }
            waitFor("unplug") { !activity.controller.state.connected }
            verify(activity.controller.state.frame!!.json(6)==beforeUnplug,"Unplug preserves the last measurement and disables acquisition")
            source.available=true;source.permission=false
            runOnMainSync { activity.refreshDevices() }
            click(MainActivity.ID_CONNECT)
            source.enumerationMode=1
            runOnMainSync { activity.refreshDevices() }
            runOnMainSync { check((activity.findViewById<Spinner>(MainActivity.ID_DEVICES).selectedItem as DeviceChoice).id==42) }
            source.permission=true
            targetContext.sendBroadcast(Intent(UsbCameraBackend.ACTION_PERMISSION).setPackage(targetContext.packageName)
                .putExtra(UsbCameraBackend.REQUESTED_DEVICE,42))
            waitFor("permission survives enumeration omission") { activity.controller.state.connected }
            verify(source.connectedId==42,"Pending USB permission survives a temporary empty discovery list")
            source.enumerationMode=0
            click(MainActivity.ID_DISCONNECT)
            source.permission=false
            runOnMainSync { activity.refreshDevices() }
            click(MainActivity.ID_CONNECT)
            targetContext.sendBroadcast(Intent(UsbCameraBackend.ACTION_PERMISSION).setPackage(targetContext.packageName)
                .putExtra(UsbCameraBackend.REQUESTED_DEVICE,42))
            waitFor("permission rejection UI") { activity.findViewById<android.widget.TextView>(MainActivity.ID_STATUS).text.contains("未获得 USB") }
            verify(!activity.controller.state.connected,"Rejected USB permission cannot open the device")
            source.permission=true;click(MainActivity.ID_CONNECT)
            waitFor("reconnect") { activity.controller.state.connected }
            click(MainActivity.ID_SAMPLE)
            waitFor("fresh result after reconnect") { activity.controller.state.mode==0 && activity.controller.state.frame!!.json(6)==beforeUnplug }
            verify(source.connectedId==42,"Reconnect opens the currently selected CS30 A")
            screenshot("cs30-live-manual.png")

            // Production native library can initialize and close without any test USB backend.
            val real=NativeCamera.create();verify(real!=0L,"Production ARM-compatible JNI initializes")
            verify(!JSONObject(NativeCamera.poll(real)).getBoolean("connected"),"Production core reports no invented camera connection")
            NativeCamera.destroy(real)
            val json=JSONObject().put("passed",true).put("checks",JSONArray(checks)).put("threshold_bits",comparisons)
                .put("auto_frames",acquired).put("auto_interval_ms",elapsed).put("physical_camera_tested",false)
                .put("usb_transport",transport)
            File(activity.getExternalFilesDir(null),"validation.json").writeText(json.toString(2))
            result.putString("stream",json.toString(2))
            runOnMainSync { activity.finish() }
            finish(Activity.RESULT_OK,result)
        } catch(error: Throwable) {
            File(targetContext.getExternalFilesDir(null),"validation.json").writeText(
                JSONObject().put("passed",false).put("checks",JSONArray(checks)).put("error",error.stackTraceToString()).toString(2))
            result.putString("stream",error.stackTraceToString())
            if(::activity.isInitialized)runOnMainSync { activity.finish() }
            finish(Activity.RESULT_CANCELED,result)
        }
    }
}
