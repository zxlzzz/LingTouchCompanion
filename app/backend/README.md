# 后端服务（smart_cane_server）

为手机 App 提供百度地图路径规划和 AI 语音助手接口。

## 环境要求

- Node.js >= 16

## 配置

复制 `.env.example` 为 `.env`，填入百度地图 AK：

```bash
cp .env.example .env
```

## 运行

```bash
npm install
node server.js
```

## 接口

| 路由文件 | 功能 |
|---------|------|
| `routes/map.js` | 地点搜索、步行路径规划、逆地理编码 |
| `routes/assistant.js` | AI 语音助手对话 |
