/**
 * routes/vision.js
 * Vision pipeline frame relay: RPi → Backend → Phone → BLE → ESP32
 *
 * POST /api/vision/frame   — Vision sends base64-encoded 15-byte frame
 * WS   /api/vision/stream  — Phone subscribes, receives frames for BLE forwarding
 */

const express = require('express');
const router = express.Router();

// In-memory subscriber set — each is a WebSocket
const subscribers = new Set();

let frameCount = 0;

/**
 * POST /api/vision/frame
 * Body: { frame: "<base64>" }
 * Vision pipeline calls this after each depth/edge frame.
 */
router.post('/frame', (req, res) => {
  try {
    const { frame } = req.body || {};
    if (!frame) {
      return res.status(400).json({ code: 400, message: '缺少 frame 字段', data: null });
    }

    const now = Date.now();
    frameCount++;

    // Broadcast to all connected phone subscribers
    const payload = JSON.stringify({ frame, seq: frameCount, ts: now });
    for (const ws of subscribers) {
      try {
        ws.send(payload);
      } catch (_) {
        subscribers.delete(ws);
      }
    }

    return res.json({ code: 200, message: 'ok', data: { seq: frameCount, subs: subscribers.size } });
  } catch (err) {
    console.error('[POST /api/vision/frame]', err);
    return res.status(500).json({ code: 500, message: err.message, data: null });
  }
});

router._subscribers = subscribers;
module.exports = router;
