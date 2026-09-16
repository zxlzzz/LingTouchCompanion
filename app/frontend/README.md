# 手机应用

基于 uni-app（Vue），提供导航、BLE 设备控制、语音交互与诊断页面。

## 运行

用 HBuilderX 打开 `app/frontend/`，选择运行到浏览器或手机；BLE 等设备功能需在支持的平台验证。

- `utils/request.js`：后端地址，默认 `http://localhost:3000`；真机访问需改为电脑可达地址。
- `api/map.js`：高德路线服务配置。
- `pages/navigation/navigation.vue`：高德地图 JS 配置。

两处地图 Key 均为无效占位值（`REPLACE_WITH_YOUR_...`），不能直接调用服务。使用前分别配置自己的高德 Web 服务 Key 和 JS API Key；不要把真实值提交到仓库。

## 页面

| 页面 | 用途 |
|---|---|
| `home` | 首页与入口 |
| `navigation` | 步行导航 |
| `map` | 地图页面 |
| `device` | BLE连接与触觉控制 |
| `diagnostic` | 设备诊断 |

后端说明见 [app/backend](../backend/README.md)。编译输出 `unpackage/` 不提交。
