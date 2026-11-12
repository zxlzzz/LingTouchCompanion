package com.lingtouch.cs30live

import android.app.Instrumentation
import android.graphics.Bitmap
import android.os.SystemClock
import org.json.JSONArray
import org.json.JSONObject

internal object FusionCheck {
    fun run(test: Instrumentation, verify: (Boolean, String) -> Unit) {
        fun asset(name: String) = test.context.assets.open(name).use { it.readBytes() }
        NativeSimulator.configure(asset("calibration.bin"))
        val live = NativeSimulator.createReviewed()
        check(live != 0L)
        try {
            check(NativeSimulator.forceClaim(0,true) && NativeSimulator.forceClaim(1,true))
            check(NativeSimulator.open(live, 44, false) == null)
            val depth = asset("frame2.raw")
            NativeSimulator.feed(depth, 0)
            Thread.sleep(210)
            NativeSimulator.feed(depth, 1)
            Thread.sleep(210)
            check(NativeSimulator.acquire(live,1) == null)
            NativeSimulator.feed(depth,0)
            val end = SystemClock.elapsedRealtime() + 5000
            var report: JSONObject
            do {
                report = JSONObject(NativeSimulator.poll(live))
                if (report.optString("status") != "no_frame") break
                Thread.sleep(20)
            } while (SystemClock.elapsedRealtime() < end)
            verify(report.optBoolean("ground_valid") && report.getJSONObject("counts").has("suspect"),
                "Native 640x480 USB stream produces reviewed occupancy")
            verify(report.getJSONObject("stats").getLong("frames_processed")==1L,
                "Reviewed live manual mode publishes exactly one selected frame")
            val reflection = NativeSimulator.autoReflectionFixture(live)
            check(NativeSimulator.acquire(live,2) == null)
            val seen = mutableSetOf<Long>()
            val autoEnd = SystemClock.elapsedRealtime() + 2300
            var nextFeed = 0L
            var fid = 1
            while (SystemClock.elapsedRealtime() < autoEnd) {
                val time = SystemClock.elapsedRealtime()
                if (time >= nextFeed) {
                    NativeSimulator.feed(reflection, fid)
                    fid = fid xor 1
                    nextFeed = time + 105
                }
                val snapshot = JSONObject(NativeSimulator.poll(live))
                if (snapshot.optString("status") != "no_frame" && seen.add(snapshot.getLong("frame_id"))) {
                    val evidence = snapshot.getJSONObject("evidence")
                    val counts = snapshot.getJSONObject("counts")
                    check(snapshot.getBoolean("ground_valid") && counts.getInt("suspect") > 0 &&
                          evidence.getJSONArray("obstacle").getInt(51) < 3 &&
                          evidence.getJSONArray("unknown").getInt(51) > 0) {
                        "Auto published an unreviewed reflection: $snapshot"
                    }
                }
                Thread.sleep(20)
            }
            verify(seen.size >= 3, "Reviewed auto mode publishes only completed grids without the injected reflection (${seen.size} frames)")
            check(NativeSimulator.acquire(live,0) == null)
        } finally {
            NativeSimulator.disconnect(live)
            NativeSimulator.destroy(live)
        }

        val captures = test.context.assets.list("fusion").orEmpty()
        if (captures.isEmpty()) {
            // The public repository can exercise ONNX with no private capture files.
            val image = Bitmap.createBitmap(RGB_WIDTH, RGB_HEIGHT, Bitmap.Config.ARGB_8888)
            try {
                YoloSeg(test.targetContext).use { model ->
                    val prediction = model.predict(image)
                    verify(prediction.names.size == prediction.masks.size &&
                        prediction.masks.all { it.size == RGBD_PIXELS },
                        "Android ONNX model runs on a 960x540 image without private capture assets")
                }
            } finally {
                image.recycle()
            }
            return
        }
        RgbdProcessor(test.targetContext).use { engine ->
            val checks = listOf(intArrayOf(11), intArrayOf(24,25,26), intArrayOf(25,26,27), intArrayOf(53,54,55))
            for (sequence in checks) {
                val n = sequence.last()
                val png = asset("fusion/$n.png")
                val raws = sequence.map { asset("fusion/$it.raw") }.toTypedArray()
                val times = sequence.map { it.toLong() * 1_000_000_000 }.toLongArray()
                val result = engine.process(png, raws, times)
                try {
                    val data = result.report
                    val counts = data.getJSONObject("counts")
                    val evidence = data.getJSONObject("evidence")
                    val obstacle = evidence.getJSONArray("obstacle")
                    val unknown = evidence.getJSONArray("unknown")
                    android.util.Log.i("FusionCheck", "frame $n · ${result.record.diagnostics} · obstacle $obstacle")
                    verify(result.record.valid, "RGB-D #$n has an accepted ground reference")
                    if (n == 11) verify(result.labels.count { it == "chair" } >= 2 && counts.getInt("yolo_subcells") > 0,
                        "Android ONNX YOLO detects both chairs and backprojects masks")
                    if (n == 26 || n == 27) {
                        val cell = if (n == 26) 52 else 51
                        verify(obstacle.getInt(cell) < 3 && unknown.getInt(cell) > 0 && counts.getInt("suspect") > 0,
                            "RGB-D #$n reflective near-right cell withheld as unknown")
                        verify(counts.getInt("aligned_views") > 0 && counts.getInt("conflicts") > 0,
                            "RGB-D #$n has contradictory measured depth after motion alignment")
                    }
                    if (n == 55) verify(obstacle.getInt(21) >= 3, "RGB-D #55 retains the pillar in row 3 col 4")
                    for (k in 1..16) {
                        val matrix = JSONArray(result.record.json(k))
                        for (r in 0 until 6) for (c in 0 until 9)
                            check(matrix.getJSONArray(r).getInt(c) == if (obstacle.getInt(r*9+c) >= k) 1 else 0)
                    }
                } finally {
                    result.preview.recycle()
                }
            }
            verify(true, "RGB-D replay exports strict K matrices at every threshold")
        }
    }
}
