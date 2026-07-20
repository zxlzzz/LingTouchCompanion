/**
 * routes/assistant.js
 * 语音助手命令解析路由
 */

const express = require('express');
const router = express.Router();
const assistantService = require('../services/assistantService');

/**
 * POST /api/assistant/parse-command
 * 请求体：
 * {
 *   "text": "带我去威海站"
 * }
 *
 * 返回示例：
 * {
 *   "code": 200,
 *   "message": "success",
 *   "data": {
 *     "intent": "start_navigation",
 *     "destination": "威海站"
 *   }
 * }
 */
router.post('/parse-command', async (req, res) => {
  try {
    const { text } = req.body || {};

    if (typeof text !== 'string' || !text.trim()) {
      return res.status(400).json({
        code: 400,
        message: '参数错误：text 为必填字符串',
        data: null
      });
    }

    const data = await assistantService.parseCommand(text);

    return res.json({
      code: 200,
      message: 'success',
      data
    });
  } catch (err) {
    console.error('[POST /api/assistant/parse-command] 错误:', err);

    return res.status(500).json({
      code: 500,
      message: err.message || '服务器内部错误',
      data: null
    });
  }
});

module.exports = router;
