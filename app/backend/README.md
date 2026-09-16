# 手机应用后端

Node.js + Express：百度地图接口、规则式语音命令解析，以及视觉帧 HTTP 接收 / WebSocket 转发。LLM 解析仅预留接口。

## 运行

进入 `app/backend/`，复制 `.env.example` 为 `.env`，配置 `BAIDU_AK`：

```sh
npm ci
npm start
```

默认端口3000，可用环境变量 `PORT` 修改；`npm run dev` 启用自动重启。

| 接口 | 用途 |
|---|---|
| `GET /` | 服务状态 |
| `/api/map/search`、`walk-route`、`reverse-geocode` | 地点搜索、步行路线、逆地理编码 |
| `POST /api/assistant/parse-command` | 文本命令解析 |
| `POST /api/vision/frame` | 接收视觉帧 |
| `WS /api/vision/stream` | 向手机推送视觉帧 |

当前实验服务 `visionss/` 可独立运行，不依赖此后端。`.env` 不提交。
