package com.lingtouch.cs30live

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Bundle
import android.os.SystemClock
import android.provider.DocumentsContract
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.Spinner
import android.widget.TextView
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.time.LocalDateTime
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.concurrent.Executors

internal object NativeRgbd {
    init { System.loadLibrary("cs30_live") }
    @JvmStatic external fun review(depths: Array<ByteArray>, times: LongArray, masks: Array<ByteArray>): String
}

internal data class ReplayResult(val preview: Bitmap, val record: FrameRecord,
                                 val labels: List<String>, val report: JSONObject)

internal class RgbdProcessor(context: Context) : AutoCloseable {
    private val yolo = YoloSeg(context)
    fun process(png: ByteArray, depths: Array<ByteArray>, times: LongArray): ReplayResult {
        val start = SystemClock.elapsedRealtime()
        require(depths.size in 1..3 && depths.all { it.size == RGBD_BYTES } && times.size == depths.size) {
            "深度必须是 960×540 对齐 RAW。"
        }
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(png, 0, png.size, bounds)
        require(bounds.outMimeType == "image/png" && bounds.outWidth == RGB_WIDTH && bounds.outHeight == RGB_HEIGHT) {
            "请选择配对的 960×540 RGB PNG。"
        }
        val bitmap = requireNotNull(BitmapFactory.decodeByteArray(png, 0, png.size))
        val predictions = yolo.predict(bitmap)
        val json = JSONObject(NativeRgbd.review(depths, times, predictions.masks))
        val pixels = json.getJSONObject("counts")
        val grid = json.getJSONObject("evidence").getJSONArray("obstacle")
        val valid = json.getBoolean("ground_valid")
        val text = "可疑 ${pixels.getInt("suspect")} · 保留 ${pixels.getInt("confirmed")} · " +
            "冲突 ${pixels.getInt("conflicts")} · 对齐 ${pixels.getInt("aligned_views")} 帧 · YOLO ${pixels.getInt("yolo_subcells")} 个小格"
        val elapsed = (SystemClock.elapsedRealtime() - start).toDouble()
        val record = FrameRecord(1, valid, json.optString("failure"), System.currentTimeMillis(),
            elapsed, IntArray(54) { grid.getInt(it) }, text)
        return ReplayResult(bitmap, record, predictions.names, json)
    }
    override fun close() = yolo.close()
}

class RgbdReplayActivity : Activity() {
    companion object {
        const val ID_PICK_FOLDER = 2011
    }
    private data class Document(val id: String, val name: String, val folder: Boolean)
    private data class PairInput(val name: String, val rgb: Uri, val raw: Uri, val time: Long)
    private lateinit var choices: Spinner
    private lateinit var run: Button
    private lateinit var folder: Button
    private lateinit var export: Button
    private lateinit var status: TextView
    private lateinit var info: TextView
    private lateinit var grid: DotGridView
    private lateinit var preview: ImageView
    private lateinit var threshold: TextView
    private val worker = Executors.newSingleThreadExecutor()
    private var processor: RgbdProcessor? = null
    private var pairs = emptyList<PairInput>()
    private var result: ReplayResult? = null
    private var pendingExport: String? = null
    private var busy = false
    private var k = 3

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        pendingExport = savedInstanceState?.getString("export")
        val body = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val pad = (16 * resources.displayMetrics.density).toInt()
            setPadding(pad, pad, pad, pad)
        }
        fun text(value: String) = TextView(this).apply { text = value; body.addView(this) }
        fun button(value: String, action: () -> Unit) = Button(this).apply {
            text = value
            isAllCaps = false
            setOnClickListener { action() }
            body.addView(this)
        }
        setContentView(ScrollView(this).apply { addView(body) })
        text("CS30 RGB-D 回放").textSize = 23f
        folder = button("选择样本目录") { pickFolder() }
        folder.id = ID_PICK_FOLDER
        choices = Spinner(this).also { body.addView(it) }
        run = button("处理所选帧") { process() }
        status = text("选择含同帧 RGB PNG 和深度 RAW 的目录")
        threshold = text("K = 3")
        val slider = SeekBar(this).apply {
            max = 15
            progress = 2
            contentDescription = "点阵阈值 K"
        }
        body.addView(slider)
        grid = DotGridView(this).also {
            body.addView(it, LinearLayout.LayoutParams(-1, (210 * resources.displayMetrics.density).toInt()))
        }
        info = text("")
        export = button("导出点阵 JSON") { exportResult() }
        preview = ImageView(this).apply {
            adjustViewBounds = true
            contentDescription = "当前 RGB 图"
        }
        body.addView(preview, LinearLayout.LayoutParams(-1, -2))
        slider.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(bar: SeekBar, value: Int, fromUser: Boolean) {
                k = value + 1
                render()
            }
            override fun onStartTrackingTouch(bar: SeekBar) = Unit
            override fun onStopTrackingTouch(bar: SeekBar) = Unit
        })
        choices.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>, view: View?, position: Int, id: Long) {
                result = null
                preview.setImageDrawable(null)
                if (!busy && pairs.isNotEmpty()) status.text = "等待处理所选帧"
                render()
            }
            override fun onNothingSelected(parent: AdapterView<*>) = Unit
        }
        render()
    }

    private fun render() {
        threshold.text = "K = $k · 上远下近"
        grid.show(result?.record, k)
        folder.isEnabled = !busy
        choices.isEnabled = !busy && pairs.isNotEmpty()
        run.isEnabled = !busy && pairs.isNotEmpty()
        export.isEnabled = !busy && result?.record?.valid == true
        info.text = result?.let { "YOLO：${it.labels.ifEmpty { listOf("无候选") }.joinToString("、")}\n${it.record.diagnostics}" } ?: ""
    }

    @Suppress("DEPRECATION")
    private fun pickFolder() {
        startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT_TREE), 61)
    }

    private fun children(tree: Uri, id: String): List<Document> {
        val uri = DocumentsContract.buildChildDocumentsUriUsingTree(tree, id)
        return contentResolver.query(uri, arrayOf(DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME, DocumentsContract.Document.COLUMN_MIME_TYPE),
            null, null, null)?.use { rows ->
            buildList {
                while (rows.moveToNext()) add(Document(rows.getString(0), rows.getString(1),
                    rows.getString(2) == DocumentsContract.Document.MIME_TYPE_DIR))
            }
        } ?: emptyList()
    }

    private fun scan(tree: Uri): List<PairInput> {
        val root = DocumentsContract.getTreeDocumentId(tree)
        val top = children(tree, root)
        val rootName = root.substringAfterLast('/').substringAfterLast(':')
        val groups = listOf(rootName to top) + top.filter { it.folder }.map { it.name to children(tree, it.id) }
        val rgbPattern = Regex("""RGBD_RGB\[(\d+)]\.png""", RegexOption.IGNORE_CASE)
        val timeFormat = DateTimeFormatter.ofPattern("uuuuMMddHHmmss")
        return groups.flatMap { (name, docs) ->
            val time = runCatching {
                LocalDateTime.parse(name.take(14), timeFormat).toEpochSecond(ZoneOffset.UTC) * 1_000_000_000L
            }.getOrDefault(0)
            val byName = docs.associateBy { it.name.lowercase() }
            docs.mapNotNull { d ->
                val index = rgbPattern.matchEntire(d.name)?.groupValues?.get(1) ?: return@mapNotNull null
                val depth = byName["rgbd_depth[$index].raw"] ?: return@mapNotNull null
                PairInput("$name [$index]", DocumentsContract.buildDocumentUriUsingTree(tree, d.id),
                    DocumentsContract.buildDocumentUriUsingTree(tree, depth.id), time)
            }
        }.sortedWith(compareBy<PairInput> { it.time }.thenBy { it.name })
    }

    private fun InputStream.bounded(limit: Int): ByteArray {
        val out = ByteArrayOutputStream()
        val buffer = ByteArray(8192)
        while (true) {
            val count = read(buffer)
            if (count < 0) break
            require(out.size() + count <= limit) { "样本文件尺寸超出支持范围" }
            out.write(buffer, 0, count)
        }
        return out.toByteArray()
    }

    private fun bytes(uri: Uri, limit: Int) =
        requireNotNull(contentResolver.openInputStream(uri)) { "无法读取样本" }.use { it.bounded(limit) }

    private fun process() {
        val index = choices.selectedItemPosition
        val chosen = pairs.getOrNull(index) ?: return
        val history = pairs.take(index).filter { it.time > 0 && it.time < chosen.time &&
            chosen.time - it.time <= 2_200_000_000L }.takeLast(2)
        busy = true
        result = null
        status.text = "正在复核深度并运行 YOLO…"
        render()
        worker.execute {
            val outcome = runCatching {
                val sequence = history + chosen
                val model = processor ?: RgbdProcessor(applicationContext).also { processor = it }
                model.process(bytes(chosen.rgb, 8 * 1024 * 1024),
                    sequence.map { bytes(it.raw, RGBD_BYTES) }.toTypedArray(), sequence.map { it.time }.toLongArray())
            }
            runOnUiThread {
                if (isDestroyed) return@runOnUiThread
                busy = false
                outcome.onSuccess {
                    result = it
                    preview.setImageBitmap(it.preview)
                    status.text = if (it.record.valid) "处理完成 · ${it.record.processMs.toInt()} ms"
                    else "地面参考未通过 · ${it.record.failure}"
                }.onFailure { status.text = "处理失败 · ${it.message}" }
                render()
            }
        }
    }

    @Suppress("DEPRECATION")
    private fun exportResult() {
        val current = result?.record?.takeIf { it.valid } ?: return
        pendingExport = current.json(k)
        startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "application/json"
            putExtra(Intent.EXTRA_TITLE, "cs30_fusion_k$k.json")
        }, 62)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val uri = data?.data.takeIf { resultCode == RESULT_OK }
        if (requestCode == 62) {
            val content = pendingExport
            pendingExport = null
            if (uri != null && content != null) runCatching {
                requireNotNull(contentResolver.openOutputStream(uri, "wt")).use { it.write(content.toByteArray()) }
            }.onSuccess { status.text = "已保存点阵" }.onFailure { status.text = "保存失败 · ${it.message}" }
        } else if (requestCode == 61 && uri != null) {
            busy = true
            result = null
            status.text = "正在查找配对样本…"
            render()
            worker.execute {
                val loaded = runCatching { scan(uri) }
                runOnUiThread {
                    if (isDestroyed) return@runOnUiThread
                    busy = false
                    pairs = loaded.getOrDefault(emptyList())
                    choices.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, pairs.map { it.name })
                    status.text = if (pairs.isEmpty()) "目录中没有可读取的配对样本" else "已找到 ${pairs.size} 组样本"
                    render()
                }
            }
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString("export", pendingExport)
        super.onSaveInstanceState(outState)
    }

    override fun onDestroy() {
        worker.execute { processor?.close() }
        worker.shutdown()
        super.onDestroy()
    }
}
