# 手机应用

基于 uni-app（Vue），提供导航、BLE 设备控制、语音交互与诊断页面。

## 运行

用 HBuilderX 打开 `app/frontend/`，选择运行到浏览器或手机；BLE 等设备功能需在支持的平台验证。

- `utils/request.js`：后端地址，默认 `http://localhost:3000`；真机访问需改为电脑可达地址。
- `api/map.js`：高德路线服务配置。
- `pages/navigation/navigation.vue`：高德地图 JS 配置。

地图 Key 需自行配置；当前代码含硬编码值，发布前应处理。

## 页面

| 页面 | 用途 |
|---|---|
| `home` | 首页与入口 |
| `navigation` | 步行导航 |
| `map` | 地图页面 |
| `device` | BLE连接与触觉控制 |
| `diagnostic` | 设备诊断 |

后端说明见 [app/backend](../backend/README.md)。编译输出 `unpackage/` 不提交。
