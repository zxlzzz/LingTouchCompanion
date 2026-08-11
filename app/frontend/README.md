# 前端 App（smart_cane）

基于 uni-app（Vue）的跨平台手机应用，提供导航界面、BLE 设备连接、语音助手交互。

## 环境要求

- HBuilderX

## 运行

**HBuilderX 方式：**
1. 用 HBuilderX 打开
2. 菜单 → 运行 → 运行到浏览器 / 运行到手机

**需要同时启动后端服务**（地图 REST 接口代理）：`cd backend && npm run dev`（详见 backend/README.md）

## 页面结构

| 页面 | 路径 | 功能 |
|------|------|------|
| 首页 | `pages/home/` | 主入口（语音助手待命、危险播报演示开关） |
| 地图 | `pages/map/` | 百度地图展示与导航（web-view） |
| 导航 | `pages/navigation/` | 步行导航模式（百度地图 JS API + 语音指引） |
| 设备 | `pages/device/` | BLE 盲文设备连接管理 |
| 诊断 | `pages/diagnostic/` | 设备调试与状态检测 |

## 语音助手「灵触助手」

- 说「灵触助手」（含谐音别名）唤醒，再下达指令：`带我去XX` / `去医院` / `连接设备` / `检测设备` / `打开XX页` 等
- 命令解析由后端 `/api/assistant/parse-command` 完成（规则优先，LLM 预留）
- 导航中逐段语音指引：转向预告（前方 30 米左转）、偏离路线自动重规划、到达提醒
- 语音识别/播报基于浏览器 Web Speech API，需 Chrome/Edge 且 localhost 或 HTTPS

## 危险播报

- 危险播报引擎 `utils/hazardEngine.js`：类型/方位/距离 → 分级播报（≤2m 紧急、2~5m 常规、>5m 仅 UI 提示），同类型同方向去重，危险播报优先于导航播报
- 当前数据源为模拟源 `utils/hazardMockSource.js`（首页「危险播报演示」开关控制），硬件摄像头/BLE 就绪后替换注册即可
- 危险播报为安全功能：独立于唤醒词常驻监听，且不受「语音播报」开关限制

## 地图配置

- 前端 JS API Key：`config/baidu.js`（BAIDU_JS_AK）
- 服务端 REST AK：`backend/.env`（BAIDU_AK），REST 接口经后端代理调用，不暴露前端
- 坐标统一使用百度坐标系 BD09，浏览器 WGS84 / uni GCJ02 由 `utils/coord.js` 自动转换
