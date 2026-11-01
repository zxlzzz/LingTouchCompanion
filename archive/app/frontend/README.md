# 手机应用

基于 uni-app（Vue），提供导航、BLE 设备控制、语音交互、危险播报与诊断页面。

## 运行

用 HBuilderX 打开 `archive/app/frontend/`，选择运行到浏览器或手机；BLE 等设备功能需在支持的平台验证。需要同时启动后端（地图 REST 接口代理），见 [agent/backend](../../../agent/backend/README.md)。

- `utils/request.js`：后端地址，默认 `http://localhost:3000`；真机访问需改为电脑可达地址。
- `config/baidu.js`：百度地图 JS API Key（`BAIDU_JS_AK`），用于页面地图渲染。
- `agent/backend/.env`：百度服务端 AK（`BAIDU_AK`），地点搜索/步行路线/逆地理编码由后端代理调用，不暴露前端。两个 AK 应用类型不同，不可混用。
- 坐标统一用百度 BD09，浏览器 WGS84 / uni GCJ02 由 `utils/coord.js` 转换。

仓库里的 Key 均为无效占位值（`REPLACE_WITH_YOUR_...`），不能直接调用服务。使用前配置自己的 Key；不要把真实值提交到仓库。

## 页面

| 页面 | 用途 |
|---|---|
| `home` | 首页与入口（语音助手待命、危险播报演示开关） |
| `navigation` | 步行导航（百度地图 JS API + 语音指引） |
| `map` | 地图页面 |
| `device` | BLE连接与触觉控制 |
| `diagnostic` | 设备诊断 |

## 语音助手「灵触助手」

- 说「灵触助手」（含谐音别名）唤醒，再下达指令：`带我去XX` / `去医院` / `连接设备` / `检测设备` / `打开XX页` 等
- 命令解析由后端 `/api/assistant/parse-command` 完成（规则优先，LLM 预留）
- 导航中逐段语音指引：转向预告、偏离路线自动重规划、到达提醒
- 语音识别/播报基于浏览器 Web Speech API，需 Chrome/Edge 且 localhost 或 HTTPS

## 危险播报

- `utils/hazardEngine.js`：类型/方位/距离 → 分级播报（≤2m 紧急、2~5m 常规、>5m 仅 UI 提示），同类型同方向去重，优先于导航播报
- 当前数据源为模拟源 `utils/hazardMockSource.js`（首页「危险播报演示」开关控制），真实数据源就绪后替换注册即可
- 独立于唤醒词常驻监听，不受「语音播报」开关限制

编译输出 `unpackage/` 不提交。
