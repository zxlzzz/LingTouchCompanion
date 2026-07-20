/*
 * 灵触·随行 — ESP32-S3 固件 (15模组正式版)
 * V2.2 — Phase A线圈隔离修复
 *
 * 变更（相对 V2.1）：
 *   - refreshGrouped Phase A：从 memcpy(holdFrame) 改为 memset(0x00)
 *     确保Phase A期间只有当前batch的SMA通电，VCCS不被其他模组线圈瓜分
 *     step参数因此真正生效
 *   - 二次脉冲的第二次Phase A同样修复
 *
 * 设计动机：
 *   V2.1中Phase A发的frame = holdFrame（历史线圈全开）+ 当前batch SMA=0x40
 *   导致VCCS同时给所有已激活模组的线圈续流，step无论设多小电流都不够
 *   修复后Phase A全清线圈，VCCS电流集中给当前batch的SMA加热
 *
 * 数据流：
 *   手机(uni-app) → BLE FFE1 write 15字节 → ESP32 刷新点阵
 *   物理按钮 → ESP32 检测 → FFE3 notify 模式切换 → 手机转发给RPi
 *
 * 硬件架构：
 *   ESP32-S3 DevKitC-1 (N16R8)
 *   → SPI → 15× SN74HC595N (DIP-16, 菊花链)
 *   → 15× ULN2803APG (SOIC-18)
 *   → 15× WUJIE 2×3 SMA盲文模组
 *
 * 物理布局（手杖上方俯视）：
 *    1  2  3
 *    4  5  6
 *    7  8  9
 *   10 11 12
 *   13 14 15
 *
 * 电源（外接方案，板上XL4015/MT3608已断开隔离）：
 *   5V      = 外接电源 → J_ESP_R pin22
 *   VCC     = 2.5V (外接DC-DC降压模块 → U46排针/R1注入, 线圈驱动)
 *   VCCS    = 2.0V (板上AMS1117-ADJ从5V降压, SMA pin12, 经ULN后~1.1V)
 *   V_LOGIC = 3.3V (ESP32 3V3引脚供595逻辑)
 *
 * 接线（ESP32 → PCB）：
 *   GPIO11 → SER    (U1 pin14, SPI MOSI)
 *   GPIO12 → SRCLK  (共享, SPI SCLK)
 *   GPIO10 → RCLK   (共享, 锁存)
 *   GPIO9  → OE#    (共享, 输出使能, 低有效)
 *   GPIO8  → SRCLR# (共享, 清零, 低有效)
 *   GPIO6  → BTN    (物理按钮, 按下接GND, 内部上拉)
 */

#include <SPI.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// ═══════════════════════════════════════
//  硬件引脚
// ═══════════════════════════════════════

#define PIN_SER    11   // SPI MOSI → U1 SER
#define PIN_SRCLK  12   // SPI SCLK → 共享SRCLK
#define PIN_RCLK   10   // 锁存时钟（共享）
#define PIN_OE      9   // 输出使能（低有效，共享）
#define PIN_SRCLR   8   // 清零（低有效，共享）
#define PIN_BTN     6   // 物理按钮（按下拉低，内部上拉）

// ═══════════════════════════════════════
//  系统参数
// ═══════════════════════════════════════

#define NUM_MODULES     15
#define FRAME_LEN       15
#define PINS_PER_MOD    6

// SMA四相时序（ms）
#define DEFAULT_PHASE_A   10    // 打开SMA
#define DEFAULT_PHASE_B   80    // 发送线圈数据
#define DEFAULT_PHASE_C  300    // 关闭SMA，线圈保持
#define DEFAULT_PHASE_D   10    // 全部断电

#define DEFAULT_STEP      8

// 二次脉冲A-B之间的短暂间隔（ms）
#define RETRY_GAP_MS      5

// 按钮去抖时间（ms）
#define BTN_DEBOUNCE_MS   200

// SMA安全保护：单相最大时间（ms）
#define MAX_PHASE_MS      500

// ═══════════════════════════════════════
//  模式定义
// ═══════════════════════════════════════

enum DeviceMode : uint8_t {
  MODE_RAPID_AVOID = 0x01,
  MODE_LOCAL_ZOOM  = 0x02
};

// ═══════════════════════════════════════
//  FFE3 Notify 事件类型
// ═══════════════════════════════════════

#define EVT_REFRESH_DONE  0x01
#define EVT_MODE_SWITCH   0x02
#define EVT_BATTERY       0x03

// ═══════════════════════════════════════
//  物理位置 → SPI字节索引 映射
// ═══════════════════════════════════════

uint8_t posToChain[NUM_MODULES] = {
  14, 13, 12, 11, 10,
   9,  8,  7,  6,  5,
   4,  3,  2,  1,  0,
};

uint8_t deadDots[NUM_MODULES] = {
  0x00,0x00,0x00,0x00,0x00,
  0x00,0x00,0x00,0x00,0x00,
  0x00,0x00,0x00,0x00,0x00,
};

// ═══════════════════════════════════════
//  运行时参数
// ═══════════════════════════════════════

int phaseA = DEFAULT_PHASE_A;
int phaseB = DEFAULT_PHASE_B;
int phaseC = DEFAULT_PHASE_C;
int phaseD = DEFAULT_PHASE_D;
int refreshStep = DEFAULT_STEP;

uint16_t moduleMask = 0x7FFF;

// ═══════════════════════════════════════
//  状态变量
// ═══════════════════════════════════════

uint8_t brailleData[NUM_MODULES] = {0};
uint8_t prevData[NUM_MODULES] = {0};

volatile bool newDataReady = false;
volatile bool forceRefresh = false;
volatile bool refreshComplete = true;

DeviceMode currentMode = MODE_RAPID_AVOID;

volatile unsigned long lastBtnPress = 0;
volatile bool btnPressed = false;

volatile bool pendingNotify = false;
volatile uint8_t pendingNotifyType = 0;
volatile uint8_t pendingNotifyData = 0;

// ═══════════════════════════════════════
//  SPI
// ═══════════════════════════════════════

SPIClass *hspi = NULL;

void initSPI() {
  hspi = new SPIClass(HSPI);
  hspi->begin(PIN_SRCLK, -1, PIN_SER, -1);
  hspi->setFrequency(1000000);
  hspi->setDataMode(SPI_MODE0);
}

void initGPIO() {
  pinMode(PIN_RCLK,  OUTPUT);
  pinMode(PIN_OE,    OUTPUT);
  pinMode(PIN_SRCLR, OUTPUT);

  digitalWrite(PIN_RCLK,  HIGH);
  digitalWrite(PIN_OE,    HIGH);  // 先禁止输出
  digitalWrite(PIN_SRCLR, HIGH);
}

void sendRaw(uint8_t *frame, size_t len) {
  digitalWrite(PIN_OE, LOW);
  digitalWrite(PIN_RCLK, LOW);
  hspi->transferBytes(frame, NULL, len);
  digitalWrite(PIN_RCLK, HIGH);
}

// ═══════════════════════════════════════
//  四相分组刷新（V2.2: Phase A线圈隔离）
// ═══════════════════════════════════════

// posData     : 15模组的目标点阵数据
// changeMask  : 需要刷新的模组位掩码
// risingMask  : 含0→1升边的模组位掩码
void refreshGrouped(uint8_t *posData, uint16_t changeMask, uint16_t risingMask) {
  uint8_t frame[FRAME_LEN];
  static uint8_t holdFrame[FRAME_LEN] = {0};
  refreshComplete = false;

  // 收集需要刷新的模组
  int needRefresh[NUM_MODULES];
  int needCount = 0;
  for (int p = 0; p < NUM_MODULES; p++) {
    if ((changeMask & (1 << p)) && (moduleMask & (1 << p))) {
      needRefresh[needCount++] = p;
    }
  }

  if (needCount == 0) {
    vTaskDelay(pdMS_TO_TICKS(1000));
    memset(holdFrame, 0x00, FRAME_LEN);
    sendRaw(holdFrame, FRAME_LEN);
    refreshComplete = true;
    return;
  }

  // 更新 holdFrame
  for (int k = 0; k < needCount; k++) {
    int p = needRefresh[k];
    holdFrame[posToChain[p]] = posData[p] & 0x3F;
  }

  #define MAX_STEP 12
  int step = min(refreshStep, MAX_STEP);

  for (int i = 0; i < needCount; i += step) {
    if (newDataReady) {
      vTaskDelay(pdMS_TO_TICKS(1000));
      memset(holdFrame, 0x00, FRAME_LEN);
      sendRaw(holdFrame, FRAME_LEN);
      refreshComplete = true;
      return;
    }

    int batchEnd = min(i + step, needCount);

    // 判断当前batch是否含升边模组
    bool batchHasRising = false;
    for (int j = i; j < batchEnd; j++) {
      if (risingMask & (1 << needRefresh[j])) { batchHasRising = true; break; }
    }

    // ── 第一轮 A-B ──

    // Phase A: 全部清零，只开当前batch的SMA
    // ★V2.2修复：memset(0x00)而非memcpy(holdFrame)
    // 确保VCCS电流不被其他模组线圈瓜分，step真正生效
    memset(frame, 0x00, FRAME_LEN);
    for (int j = i; j < batchEnd; j++) {
      frame[posToChain[needRefresh[j]]] = 0x40;
    }
    sendRaw(frame, FRAME_LEN);
    vTaskDelay(pdMS_TO_TICKS(phaseA));

    // Phase B: 只写当前batch，全清其他
    memset(frame, 0x00, FRAME_LEN);  // 原来是 memcpy(frame, holdFrame, FRAME_LEN)
    for (int j = i; j < batchEnd; j++) {
      int p = needRefresh[j];
      frame[posToChain[p]] = (posData[p] & 0x3F) | 0x40;
    }
    sendRaw(frame, FRAME_LEN);
    vTaskDelay(pdMS_TO_TICKS(phaseB));

    // ── 二次脉冲：仅对含升边的batch ──
    if (batchHasRising) {
      // 短暂回到holdFrame（关本批SMA）
      sendRaw(holdFrame, FRAME_LEN);
      vTaskDelay(pdMS_TO_TICKS(RETRY_GAP_MS));

      // 再来一次 Phase A（同样全清）
      memset(frame, 0x00, FRAME_LEN);
      for (int j = i; j < batchEnd; j++) {
        frame[posToChain[needRefresh[j]]] = 0x40;
      }
      sendRaw(frame, FRAME_LEN);
      vTaskDelay(pdMS_TO_TICKS(phaseA));

      // 再来一次 Phase B
      memset(frame, 0x00, FRAME_LEN);  // 原来是 memcpy(frame, holdFrame, FRAME_LEN)
      for (int j = i; j < batchEnd; j++) {
        int p = needRefresh[j];
        frame[posToChain[p]] = (posData[p] & 0x3F) | 0x40;
      }
      sendRaw(frame, FRAME_LEN);
      vTaskDelay(pdMS_TO_TICKS(phaseB));
    }

    // Phase C: 关闭SMA，线圈保持（holdFrame）
    sendRaw(holdFrame, FRAME_LEN);
    vTaskDelay(pdMS_TO_TICKS(phaseC));

    // Phase D
    vTaskDelay(pdMS_TO_TICKS(phaseD));
  }

  vTaskDelay(pdMS_TO_TICKS(1000));
  memset(holdFrame, 0x00, FRAME_LEN);
  sendRaw(holdFrame, FRAME_LEN);
  refreshComplete = true;
}

// ═══════════════════════════════════════
//  BLE
// ═══════════════════════════════════════

#define SERVICE_UUID        "0000FFE0-0000-1000-8000-00805F9B34FB"
#define CHAR_BRAILLE_UUID   "0000FFE1-0000-1000-8000-00805F9B34FB"
#define CHAR_STATUS_UUID    "0000FFE3-0000-1000-8000-00805F9B34FB"

BLEServer *pServer = NULL;
BLECharacteristic *pBrailleChar = NULL;
BLECharacteristic *pStatusChar = NULL;
bool deviceConnected = false;
bool oldDeviceConnected = false;

void notifyStatus(uint8_t eventType, uint8_t eventData); // 前向声明

class ServerCB : public BLEServerCallbacks {
  void onConnect(BLEServer *s) override {
    deviceConnected = true;
    Serial.println("[BLE] 已连接");
    notifyStatus(EVT_MODE_SWITCH, currentMode);
  }
  void onDisconnect(BLEServer *s) override {
    deviceConnected = false;
    Serial.println("[BLE] 已断开");
  }
};

class BrailleCB : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    String rx = c->getValue();
    if (rx.length() != NUM_MODULES) {
      Serial.printf("[BLE] 长度错误: %d (需要%d)\n", rx.length(), NUM_MODULES);
      return;
    }
    for (int i = 0; i < NUM_MODULES; i++) {
      brailleData[i] = ((uint8_t)rx[i]) & 0x3F;
    }
    newDataReady = true;
    Serial.println("[BLE] 收到数据帧");
  }
};

void notifyStatus(uint8_t eventType, uint8_t eventData) {
  if (!deviceConnected) return;
  uint8_t payload[2] = {eventType, eventData};
  pStatusChar->setValue(payload, 2);
  pStatusChar->notify();
  Serial.printf("[BLE] notify: type=0x%02X data=0x%02X\n", eventType, eventData);
}

void queueNotify(uint8_t eventType, uint8_t eventData) {
  pendingNotifyType = eventType;
  pendingNotifyData = eventData;
  pendingNotify = true;
}

void dispatchNotify() {
  if (pendingNotify) {
    pendingNotify = false;
    notifyStatus(pendingNotifyType, pendingNotifyData);
  }
}

void initBLE() {
  BLEDevice::init("LingChu-Tactile");
  BLEDevice::setMTU(64);

  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new ServerCB());

  BLEService *svc = pServer->createService(SERVICE_UUID);

  pBrailleChar = svc->createCharacteristic(
    CHAR_BRAILLE_UUID,
    BLECharacteristic::PROPERTY_WRITE |
    BLECharacteristic::PROPERTY_WRITE_NR
  );
  pBrailleChar->setCallbacks(new BrailleCB());

  pStatusChar = svc->createCharacteristic(
    CHAR_STATUS_UUID,
    BLECharacteristic::PROPERTY_NOTIFY
  );
  pStatusChar->addDescriptor(new BLE2902());

  svc->start();

  BLEAdvertising *adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(SERVICE_UUID);
  adv->setScanResponse(true);
  adv->setMinPreferred(0x06);
  adv->setMaxPreferred(0x12);
  BLEDevice::startAdvertising();

  Serial.println("[BLE] 广播中: LingChu-Tactile");
}

// ═══════════════════════════════════════
//  按钮处理
// ═══════════════════════════════════════

void IRAM_ATTR btnISR() {
  unsigned long now = millis();
  if (now - lastBtnPress > BTN_DEBOUNCE_MS) {
    lastBtnPress = now;
    btnPressed = true;
  }
}

void initButton() {
  pinMode(PIN_BTN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_BTN), btnISR, FALLING);
  Serial.println("[BTN] GPIO6 就绪 (内部上拉, 按下拉低)");
}

void handleButton() {
  if (!btnPressed) return;
  btnPressed = false;

  if (currentMode == MODE_RAPID_AVOID) {
    currentMode = MODE_LOCAL_ZOOM;
  } else {
    currentMode = MODE_RAPID_AVOID;
  }

  const char *modeName = (currentMode == MODE_RAPID_AVOID) ? "RAPID_AVOID" : "LOCAL_ZOOM";
  Serial.printf("[BTN] 模式切换 → %s (0x%02X)\n", modeName, currentMode);

  notifyStatus(EVT_MODE_SWITCH, currentMode);
}

// ═══════════════════════════════════════
//  BLE重连管理
// ═══════════════════════════════════════

void manageBLE() {
  if (!deviceConnected && oldDeviceConnected) {
    delay(500);
    pServer->startAdvertising();
    Serial.println("[BLE] 断连，重新广播");
    oldDeviceConnected = false;
  }
  if (deviceConnected && !oldDeviceConnected) {
    oldDeviceConnected = true;
  }
}

// ═══════════════════════════════════════
//  驱动任务（核心1）
// ═══════════════════════════════════════

void driveTask(void *pvParam) {
  while (true) {
    if (newDataReady) {
      newDataReady = false;
      for (int i = 0; i < NUM_MODULES; i++) brailleData[i] &= ~deadDots[i];

      // 计算差量 + 升边
      uint16_t changeMask = 0;
      uint16_t risingMask = 0;
      for (int i = 0; i < NUM_MODULES; i++) {
        if (brailleData[i] != prevData[i]) {
          changeMask |= (1 << i);
        }
        uint8_t rising = brailleData[i] & ~prevData[i] & 0x3F;
        if (rising) {
          risingMask |= (1 << i);
        }
      }

      if (changeMask != 0) {
        int cnt = 0, rcnt = 0;
        for (int i = 0; i < NUM_MODULES; i++) {
          if (changeMask & (1<<i)) cnt++;
          if (risingMask & (1<<i)) rcnt++;
        }
        Serial.printf("[刷新] %d个模组变化 (含%d个升边), changeMask=0x%04X risingMask=0x%04X\n",
                      cnt, rcnt, changeMask, risingMask);

        refreshGrouped(brailleData, changeMask, risingMask);
        memcpy(prevData, brailleData, NUM_MODULES);
      } else {
        Serial.println("[跳过] 数据无变化");
      }

      queueNotify(EVT_REFRESH_DONE, 0x00);
    }

    if (forceRefresh) {
      forceRefresh = false;
      refreshGrouped(brailleData, 0x7FFF, 0x7FFF);
      memcpy(prevData, brailleData, NUM_MODULES);
    }

    vTaskDelay(pdMS_TO_TICKS(20));
  }
}

// ═══════════════════════════════════════
//  串口命令
// ═══════════════════════════════════════

void printHelp() {
  Serial.println("=== 灵触·随行 15模组驱动 V2.2 ===");
  Serial.println("命令:");
  Serial.println("  help              显示帮助");
  Serial.println("  test              全部凸起");
  Serial.println("  clear             全部复位");
  Serial.println("  set N XX          位置N(1-15)设为0xXX");
  Serial.println("  row R XX          第R行(1-5)设为0xXX");
  Serial.println("  col C XX          第C列(1-3)设为0xXX");
  Serial.println("  mask 0xNNNN       设模组掩码");
  Serial.println("  step N            设分组步长(1-15)");
  Serial.println("  timing A B C D    设四相时序(ms)");
  Serial.println("  mode              查看/切换模式");
  Serial.println("  print             打印当前状态");
  Serial.println("  demo              演示动画");
  Serial.println("  refresh           强制重刷");
}

void printStatus() {
  Serial.println("--- 当前状态 ---");
  Serial.printf("模式: %s (0x%02X)\n",
    (currentMode == MODE_RAPID_AVOID) ? "RAPID_AVOID" : "LOCAL_ZOOM",
    currentMode);
  Serial.printf("掩码: 0x%04X\n", moduleMask);
  Serial.printf("步长: %d\n", refreshStep);
  Serial.printf("时序: A=%d B=%d C=%d D=%d ms\n", phaseA, phaseB, phaseC, phaseD);
  Serial.printf("BLE: %s\n", deviceConnected ? "已连接" : "未连接");
  Serial.println("点阵数据:");
  for (int row = 0; row < 5; row++) {
    Serial.print("  ");
    for (int col = 0; col < 3; col++) {
      int pos = row * 3 + col;
      bool active = moduleMask & (1 << pos);
      if (active) {
        Serial.printf("[%2d]=0x%02X  ", pos + 1, brailleData[pos]);
      } else {
        Serial.printf("[%2d]=----  ", pos + 1);
      }
    }
    Serial.println();
  }
}

void runDemo() {
  Serial.println("[DEMO] 逐模组点亮...");
  for (int i = 0; i < NUM_MODULES; i++) {
    if (!(moduleMask & (1 << i))) continue;
    memset(brailleData, 0x00, NUM_MODULES);
    brailleData[i] = 0x3F;
    newDataReady = true;
    while (!refreshComplete) vTaskDelay(pdMS_TO_TICKS(10));
    vTaskDelay(pdMS_TO_TICKS(300));
  }

  Serial.println("[DEMO] 逐行点亮...");
  for (int row = 1; row <= 5; row++) {
    memset(brailleData, 0x00, NUM_MODULES);
    for (int col = 0; col < 3; col++) {
      int pos = (row - 1) * 3 + col;
      if (moduleMask & (1 << pos)) {
        brailleData[pos] = 0x3F;
      }
    }
    newDataReady = true;
    while (!refreshComplete) vTaskDelay(pdMS_TO_TICKS(10));
    vTaskDelay(pdMS_TO_TICKS(500));
  }

  Serial.println("[DEMO] 全部凸起");
  for (int i = 0; i < NUM_MODULES; i++) brailleData[i] = 0x3F;
  newDataReady = true;
  while (!refreshComplete) vTaskDelay(pdMS_TO_TICKS(10));
  vTaskDelay(pdMS_TO_TICKS(1000));

  memset(brailleData, 0x00, NUM_MODULES);
  newDataReady = true;
  Serial.println("[DEMO] 结束");
}

void processSerial() {
  if (!Serial.available()) return;

  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) return;

  Serial.printf("> %s\n", line.c_str());

  if (line == "help") {
    printHelp();
  }
  else if (line == "test") {
    for (int i = 0; i < NUM_MODULES; i++) brailleData[i] = 0x3F;
    newDataReady = true;
    Serial.println("全部凸起");
  }
  else if (line == "clear") {
    memset(brailleData, 0x00, NUM_MODULES);
    newDataReady = true;
    Serial.println("全部复位");
  }
  else if (line == "refresh") {
    forceRefresh = true;
    Serial.println("强制刷新");
  }
  else if (line == "print") {
    printStatus();
  }
  else if (line == "demo") {
    runDemo();
  }
  else if (line == "mode") {
    if (currentMode == MODE_RAPID_AVOID) {
      currentMode = MODE_LOCAL_ZOOM;
    } else {
      currentMode = MODE_RAPID_AVOID;
    }
    const char *modeName = (currentMode == MODE_RAPID_AVOID) ? "RAPID_AVOID" : "LOCAL_ZOOM";
    Serial.printf("模式切换 → %s\n", modeName);
    notifyStatus(EVT_MODE_SWITCH, currentMode);
  }
  else if (line.startsWith("set ")) {
    int pos;
    unsigned int val;
    if (sscanf(line.c_str(), "set %d %x", &pos, &val) == 2) {
      if (pos >= 1 && pos <= NUM_MODULES) {
        brailleData[pos - 1] = val & 0x3F;
        newDataReady = true;
        Serial.printf("位置%d = 0x%02X\n", pos, val & 0x3F);
      } else {
        Serial.println("位置范围: 1-15");
      }
    } else {
      Serial.println("格式: set N XX");
    }
  }
  else if (line.startsWith("row ")) {
    int row;
    unsigned int val;
    if (sscanf(line.c_str(), "row %d %x", &row, &val) == 2) {
      if (row >= 1 && row <= 5) {
        for (int col = 0; col < 3; col++) {
          brailleData[(row - 1) * 3 + col] = val & 0x3F;
        }
        newDataReady = true;
        Serial.printf("第%d行 = 0x%02X\n", row, val & 0x3F);
      } else {
        Serial.println("行范围: 1-5");
      }
    } else {
      Serial.println("格式: row R XX");
    }
  }
  else if (line.startsWith("col ")) {
    int col;
    unsigned int val;
    if (sscanf(line.c_str(), "col %d %x", &col, &val) == 2) {
      if (col >= 1 && col <= 3) {
        for (int row = 0; row < 5; row++) {
          brailleData[row * 3 + (col - 1)] = val & 0x3F;
        }
        newDataReady = true;
        Serial.printf("第%d列 = 0x%02X\n", col, val & 0x3F);
      } else {
        Serial.println("列范围: 1-3");
      }
    } else {
      Serial.println("格式: col C XX");
    }
  }
  else if (line.startsWith("mask ")) {
    unsigned int val;
    if (sscanf(line.c_str(), "mask %x", &val) == 1) {
      moduleMask = val & 0x7FFF;
      Serial.printf("掩码 = 0x%04X\n", moduleMask);
      printStatus();
    } else {
      Serial.println("格式: mask 0xNNNN");
    }
  }
  else if (line.startsWith("step ")) {
    int val;
    if (sscanf(line.c_str(), "step %d", &val) == 1 && val >= 1 && val <= NUM_MODULES) {
      refreshStep = val;
      Serial.printf("步长 = %d\n", refreshStep);
      if (refreshStep > 12) {
        Serial.println("⚠ 警告: step>12时VCCS电流可能超AMS1117的1A极限");
      } else if (refreshStep > 8) {
        Serial.println("ℹ 提示: step>8时升起成功率可能下降（推荐≤8）");
      }
    } else {
      Serial.println("格式: step N (1-15)");
    }
  }
  else if (line.startsWith("timing ")) {
    int a, b, c, d;
    if (sscanf(line.c_str(), "timing %d %d %d %d", &a, &b, &c, &d) == 4) {
      a = min(a, (int)MAX_PHASE_MS);
      b = min(b, (int)MAX_PHASE_MS);
      c = min(c, (int)MAX_PHASE_MS);
      d = min(d, (int)MAX_PHASE_MS);
      phaseA = max(1, a); phaseB = max(1, b); phaseC = max(1, c); phaseD = max(1, d);
      Serial.printf("时序 = A:%d B:%d C:%d D:%d ms\n", phaseA, phaseB, phaseC, phaseD);
    } else {
      Serial.println("格式: timing A B C D");
    }
  }
  else {
    Serial.printf("未知命令: %s (输入help查看)\n", line.c_str());
  }
}

// ═══════════════════════════════════════
//  setup / loop
// ═══════════════════════════════════════

void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println();
  Serial.println("================================");
  Serial.println("  灵触·随行 15模组盲文驱动");
  Serial.println("  V2.2 — Phase A线圈隔离修复");
  Serial.println("================================");

  initGPIO();
  initSPI();

  // ── 上电安全序列 ──
  digitalWrite(PIN_SRCLR, LOW);
  delayMicroseconds(10);
  digitalWrite(PIN_SRCLR, HIGH);
  uint8_t zeroFrame[FRAME_LEN] = {0};
  sendRaw(zeroFrame, FRAME_LEN);
  digitalWrite(PIN_OE, LOW);
  Serial.println("[HW] 上电安全序列完成，输出已使能");

  initButton();
  initBLE();

  xTaskCreatePinnedToCore(
    driveTask,
    "DriveTask",
    4096,
    NULL,
    2,
    NULL,
    1
  );

  printHelp();
  Serial.println();
  Serial.printf("当前模式: RAPID_AVOID (0x%02X)\n", currentMode);
  Serial.printf("模组掩码: 0x%04X\n", moduleMask);
  Serial.printf("分组步长: %d\n", refreshStep);
  Serial.println("按物理按钮或输入 mode 切换模式");
  Serial.println();
}

void loop() {
  processSerial();
  handleButton();
  manageBLE();
  dispatchNotify();
  delay(10);
}
