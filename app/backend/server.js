/**
 * server.js
 * 后端服务入口
 */

const http = require('http');
const express = require('express');
const cors = require('cors');
const { WebSocketServer } = require('ws');

const mapRouter = require('./routes/map');
const assistantRouter = require('./routes/assistant');
const visionRouter = require('./routes/vision');

const app = express();
const PORT = process.env.PORT || 3000;

/**
 * 中间件
 */
app.use(cors());
app.use(express.json({ limit: '1mb' }));
app.use(express.urlencoded({ extended: true }));

/**
 * 健康检查
 */
app.get('/', (req, res) => {
  res.json({
    code: 200,
    message: 'server is running',
    data: {
      service: 'smart-cane-backend'
    }
  });
});

/**
 * 路由挂载
 */
app.use('/api/map', mapRouter);
app.use('/api/assistant', assistantRouter);
app.use('/api/vision', visionRouter);

/**
 * 404 处理
 */
app.use((req, res) => {
  res.status(404).json({
    code: 404,
    message: '接口不存在',
    data: null
  });
});

/**
 * 全局错误处理
 */
app.use((err, req, res, next) => {
  console.error('[Global Error]', err);
  res.status(500).json({
    code: 500,
    message: err.message || '服务器内部错误',
    data: null
  });
});

// ── HTTP + WebSocket ──────────────────────────────────────

const server = http.createServer(app);

const wss = new WebSocketServer({ server, path: '/api/vision/stream' });

wss.on('connection', (ws) => {
  console.log('[WS] Phone subscriber connected');
  visionRouter._subscribers.add(ws);

  ws.on('close', () => {
    console.log('[WS] Phone subscriber disconnected');
    visionRouter._subscribers.delete(ws);
  });

  ws.on('error', () => {
    visionRouter._subscribers.delete(ws);
  });
});

server.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}`);
  console.log(`Vision WS stream at ws://localhost:${PORT}/api/vision/stream`);
});
