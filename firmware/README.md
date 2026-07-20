# 固件（ESP32-S3 盲文驱动）

ESP32-S3 固件，通过 SPI 驱动 74HC595 级联链路控制 15 个 WUJIE SMA 盲文模块，BLE 接收手机端触觉帧数据。

## 环境要求

- Arduino IDE >= 2.0
- Board package：**esp32 by Espressif Systems**（通过 Boards Manager 安装）
- 开发板选择：ESP32-S3 Dev Module

## 编译烧录

1. 用 Arduino IDE 打开 `braille_15module_prod/braille_15module_prod.ino`
2. 选择开发板 ESP32-S3 Dev Module，端口选择对应串口
3. 编译并上传

## 硬件连接

| 信号 | GPIO | 功能 |
|------|------|------|
| SER (MOSI) | GPIO11 | SPI 数据 |
| SRCLK | GPIO12 | SPI 时钟 |
| RCLK | GPIO10 | 74HC595 锁存 |
| OE# | GPIO9 | 输出使能（低有效） |
| SRCLR# | GPIO8 | 移位寄存器清零（低有效） |
| BTN | GPIO6 | 按钮 |

## 通讯协议

BLE GATT 服务 0xFFE0，特征 0xFFE1/0xFFE3。每帧 30 字节，每字节 bit0~bit5 对应一个盲文模块的 6 个点。
