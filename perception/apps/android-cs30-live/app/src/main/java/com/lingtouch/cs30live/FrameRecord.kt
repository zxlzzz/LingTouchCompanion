package com.lingtouch.cs30live

import org.json.JSONArray
import org.json.JSONObject

/** An acquired measurement, retained while paused or disconnected. */
class FrameRecord(val id: Long, val valid: Boolean, val failure: String,
                  val capturedAtMs: Long, val processMs: Double, private val obstacles: IntArray,
                  val diagnostics: String) {
    companion object {
        fun parse(json: JSONObject): FrameRecord? {
            if (json.optString("status") == "no_frame" || json.isNull("frame_id")) return null
            val evidence = json.getJSONObject("evidence")
            val a = evidence.getJSONArray("obstacle")
            val g = evidence.getJSONArray("ground")
            val u = evidence.getJSONArray("unknown")
            require(a.length() == 54 && g.length() == 54 && u.length() == 54)
            val counts = IntArray(54) { i ->
                val n = a.getInt(i)
                require(n in 0..16 && g.getInt(i) in 0..16 && u.getInt(i) in 0..16)
                require(n + g.getInt(i) + u.getInt(i) == 16)
                n
            }
            val stats = json.getJSONObject("stats")
            val review = json.optJSONObject("counts")
            val detail = "已收完整帧：${stats.optLong("frames")}；已处理：${stats.optLong("frames_processed")}\n" +
                "不完整帧：${stats.optLong("incomplete")}；包错误：${stats.optLong("packet_errors")}；UVC 错误：${stats.optLong("uvc_errors")}\n" +
                "USB 回调距今：${json.optDouble("usb_callback_age_ms", -1.0)} ms；状态：${json.optInt("usb_last_transfer_status", -1)}；传输错误：${json.optLong("usb_error_count")}\n" +
                "深度复核：可疑 ${review?.optInt("suspect") ?: 0}，保留 ${review?.optInt("confirmed") ?: 0}，" +
                "冲突 ${review?.optInt("conflicts") ?: 0}，对齐帧 ${review?.optInt("aligned_views") ?: 0}\n" +
                json.optString("device") + "\n" + json.optString("usb_log")
            return FrameRecord(json.getLong("frame_id"), json.getBoolean("ground_valid"),
                json.optString("failure"), System.currentTimeMillis() - json.optDouble("age_ms", 0.0).toLong(),
                stats.optDouble("last_process_ms", 0.0), counts, detail)
        }
    }
    fun bits(k: Int): IntArray {
        require(k in 1..16)
        return IntArray(54) { if (valid && obstacles[it] >= k) 1 else 0 }
    }
    fun json(k: Int): String {
        check(valid) { "当前帧缺少有效地面参考，不能导出点阵" }
        val bits = bits(k)
        return JSONArray().apply { repeat(6) { r -> put(JSONArray().apply { repeat(9) { c -> put(bits[r*9+c]) } }) } }.toString()
    }
}
