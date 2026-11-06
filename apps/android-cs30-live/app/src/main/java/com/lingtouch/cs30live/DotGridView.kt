package com.lingtouch.cs30live

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.view.View

class DotGridView(context: Context) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var bits = IntArray(54)
    private var hasResult = false
    fun show(frame: FrameRecord?, k: Int) {
        hasResult = frame?.valid == true
        bits = frame?.bits(k) ?: IntArray(54)
        contentDescription = if (!hasResult) "等待有效点阵" else "6 行 9 列点阵，${bits.sum()} 个障碍点；上远下近，左至右"
        invalidate()
    }
    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val width = MeasureSpec.getSize(widthMeasureSpec)
        setMeasuredDimension(width, (width * 0.70f + 36 * resources.displayMetrics.density).toInt())
    }
    override fun onDraw(canvas: Canvas) {
        canvas.drawColor(Color.WHITE)
        val density = resources.displayMetrics.density
        paint.color = Color.BLACK; paint.style = Paint.Style.FILL; paint.textSize = 12*density; paint.textAlign = Paint.Align.LEFT
        canvas.drawText("远 3.4 m", 4*density, 16*density, paint)
        canvas.drawText("近 1.0 m", 4*density, height-3*density, paint)
        val top = 30*density; val bottom = height-23*density
        val dx = width/9f; val dy = (bottom-top)/6f
        for (r in 0..5) for (c in 0..8) {
            paint.strokeWidth = 1.7f*density
            paint.style = if (hasResult && bits[r*9+c] == 1) Paint.Style.FILL else Paint.Style.STROKE
            canvas.drawCircle((c+.5f)*dx, top+(r+.5f)*dy, minOf(dx,dy)*.27f, paint)
        }
    }
}
