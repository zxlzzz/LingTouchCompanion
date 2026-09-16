# ESP32-S3 触觉固件

通过 SPI 驱动15个六点模组，BLE接收15字节触觉帧。

## 烧录

Arduino IDE 安装 **esp32 by Espressif Systems**，选择 **ESP32-S3 Dev Module**，打开 [当前 V2.8 固件](braille_15module_prod/braille_15module_prod.ino) 并烧录。

`braille_15module_reverse/` 为旧 V2.3 版本，保留作历史参考，不是当前默认入口。

## 引脚与协议

| 信号 | GPIO |
|---|---|
| SER / SRCLK / RCLK | 11 / 12 / 10 |
| OE# / SRCLR# | 9 / 8 |
| 按钮 | 6 |

BLE 服务 `FFE0`：写入特征 `FFE1` 接收15字节，每字节低6位对应一个模组；通知特征 `FFE3` 中，`0x01` 为刷新完成，`0x04` 为按键扫描请求。

V2.8 默认全量刷新约220 ms。电脑端实验通路见 [visionss](../visionss/README.md)；浏览器调试可使用根目录两个 BLE 工具，注意其 ROT180 / PROD 映射差异。

[PCB历史摘要](PCB历史检查摘要.md) 与 [早期改版记录](pcb_v2_revision.md) 仅供追溯，不代表当前生产板状态。
