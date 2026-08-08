/*
 * 灵触·随行 — ESP32-S3 固件 (15模组正式版 · 板体180°反装)
 * V2.3-reverse — 板子物理旋转180°后的 posToChain / deadDots 重映射
 *
 * 与 braille_15module_prod 的唯一区别：
 *   - posToChain：旋转180°后原来的反序映射变为恒等映射
 *   - deadDots：按新的物理位置顺序重排（bit值不变，接线未动）
 *   其余逻辑（含 Phase A/B/C 时序）与 prod 保持一致
 *
 * 变更（相对 V2.2）：
 *   - 新增串口命令：hold / ex / stop（来自诊断固件 V1.1）
 *     共用主固件的 SPI/GPIO/posToChain，无重复定义
 *   - hold/ex 执行期间阻塞串口（与 V1.1 行为一致）
 *   - hold/ex 执行完毕后调用 allOff() 并恢复 brailleData 状态
 *
 * 命令（新增）：
 *   hold N XX [T]   位置N(1-15)线圈按0xXX通电T秒(1-10,默认5)，SMA不动
 *   ex N XX [C]     位置N按0xXX做解锁锻炼循环C次(1-30,默认10)
 *   stop            立即全部断电（同 clear 但不改 brailleData）
 *
 * ex 每循环节奏（共1.3秒/次）：
 *   [SMA+线圈 400ms 解锁窗口] [仅线圈 300ms 保持] [全断 600ms 散热]
 */

#include <SPI.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// ═══════════════════════════════════════
//  硬件引脚
// ═══════════════════════════════════════

#define PIN_SER    11
#define PIN_SRCLK  12
#define PIN_RCLK   10
#define PIN_OE      9
#define PIN_SRCLR   8
#define PIN_BTN     6

// ═══════════════════════════════════════
//  系统参数
// ═══════════════════════════════════════

#define NUM_MODULES     15
#define FRAME_LEN       15
#define PINS_PER_MOD    6

#define DEFAULT_PHASE_A  200
#define DEFAULT_PHASE_B   80
#define DEFAULT_PHASE_C  300
#define DEFAULT_PHASE_D   10

#define DEFAULT_STEP      8

#define RETRY_GAP_MS      5
#define BTN_DEBOUNCE_MS   200
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
#define EVT_SCAN_REQUEST  0x04

// ═══════════════════════════════════════
//  物理位置 → SPI字节索引 映射
// ═══════════════════════════════════════

uint8_t posToChain[NUM_MODULES] = {
   0,  1,  2,  3,  4,
   5,  6,  7,  8,  9,
  10, 11, 12, 13, 14,
};

// 新pos: 0=M15  1=M14  2=M13  3=M12  4=M11
//         5=M10  6=M9   7=M8   8=M7   9=M6
//        10=M5  11=M4  12=M3  13=M2  14=M1
uint8_t deadDots[NUM_MODULES] = {
  0x00, 0x20, 0x1A, 0x3F, 0x00,
  0x00, 0x00, 0x08, 0x27, 0x1F,
  0x11, 0x08, 0x2F, 0x13, 0x0A,
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
bool rawMode = false;

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
  digitalWrite(PIN_OE,    HIGH);
  digitalWrite(PIN_SRCLR, HIGH);
}

void sendRaw(uint8_t *frame, size_t len) {
  digitalWrite(PIN_OE, LOW);
  digitalWrite(PIN_RCLK, LOW);
  hspi->transferBytes(frame, NULL, len);
  digitalWrite(PIN_RCLK, HIGH);
}

void allOff() {
  uint8_t f[FRAME_LEN] = {0};
  sendRaw(f, FRAME_LEN);
}

// ═══════════════════════════════════════
//  四相分组刷新（V2.2: Phase A线圈隔离）
// ═══════════════════════════════════════

void refreshGrouped(uint8_t *posData, uint16_t changeMask, uint16_t risingMask) {
  uint8_t frame[FRAME_LEN];
  static uint8_t holdFrame[FRAME_LEN] = {0};
  refreshComplete = false;

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

    bool batchHasRising = false;
    for (int j = i; j < batchEnd; j++) {
      if (risingMask & (1 << needRefresh[j])) { batchHasRising = true; break; }
    }

    // Phase A: 全清，只开当前batch SMA
    memset(frame, 0x00, FRAME_LEN);
    for (int j = i; j < batchEnd; j++) {
      frame[posToChain[needRefresh[j]]] = 0x40;
    }
    sendRaw(frame, FRAME_LEN);
    vTaskDelay(pdMS_TO_TICKS(phaseA));

    // Phase B: 关SMA，只保持线圈 — 锁在冷却复位窗口内被线圈顶在高位咬合
    memset(frame, 0x00, FRAME_LEN);
    for (int j = i; j < batchEnd; j++) {
      int p = needRefresh[j];
      frame[posToChain[p]] = posData[p] & 0x3F;
    }
    sendRaw(frame, FRAME_LEN);
    vTaskDelay(pdMS_TO_TICKS(phaseB));

    // 二次脉冲（含升边batch）
    if (batchHasRising) {
      sendRaw(holdFrame, FRAME_LEN);
      vTaskDelay(pdMS_TO_TICKS(RETRY_GAP_MS));

      memset(frame, 0x00, FRAME_LEN);
      for (int j = i; j < batchEnd; j++) {
        frame[posToChain[needRefresh[j]]] = 0x40;
      }
      sendRaw(frame, FRAME_LEN);
      vTaskDelay(pdMS_TO_TICKS(phaseA));

      memset(frame, 0x00, FRAME_LEN);
      for (int j = i; j < batchEnd; j++) {
        int p = needRefresh[j];
        frame[posToChain[p]] = posData[p] & 0x3F;
      }
      sendRaw(frame, FRAME_LEN);
      vTaskDelay(pdMS_TO_TICKS(phaseB));
    }

    // Phase C
    sendRaw(holdFrame, FRAME_LEN);
    vTaskDelay(pdMS_TO_TICKS(phaseC));

    // Phase D
    vTaskDelay(pdMS_TO_TICKS(phaseD));
  }

  vTaskDelay(pdMS_TO_TICKS(300));
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

void notifyStatus(uint8_t eventType, uint8_t eventData);

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
  Serial.println("[SCAN]");
  notifyStatus(EVT_SCAN_REQUEST, currentMode);
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
  Serial.println("=== 灵触·随行 15模组驱动 V2.3 ===");
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
  Serial.println("  raw on/off        二进制帧模式");
  Serial.println("  refresh           强制重刷");
  Serial.println("--- 诊断命令 ---");
  Serial.println("  hold N XX [T]     线圈通电T秒(默认5,1-10)，SMA不动");
  Serial.println("    例: hold 6 02 8  → M6仅点2线圈通电8秒");
  Serial.println("  ex N XX [C]       解锁锻炼循环C次(默认10,1-30)");
  Serial.println("    例: ex 6 3F 20   → M6全部点锻炼20次");
  Serial.println("    解锁窗口(串口打印'解锁'时)用指腹按压再快速抬起");
  Serial.println("  stop              立即全部断电（不改点阵数据）");
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
  Serial.printf("RAW: %s\n", rawMode ? "开启" : "关闭");
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

// ── 诊断：hold ──
// 阻塞执行，完成后 allOff()，不修改 brailleData/prevData
void cmdHold(int pos, uint8_t val, int sec) {
  uint8_t frame[FRAME_LEN] = {0};
  frame[posToChain[pos - 1]] = val & 0x3F;
  sendRaw(frame, FRAME_LEN);
  Serial.printf("M%d 线圈=0x%02X 通电中... %d秒\n", pos, val & 0x3F, sec);
  for (int s = sec; s > 0; s--) {
    Serial.printf("  %d\n", s);
    delay(1000);
  }
  allOff();
  Serial.println("已断电");
}

// ── 诊断：ex ──
// 阻塞执行，完成后 allOff()，不修改 brailleData/prevData
void cmdEx(int pos, uint8_t val, int cycles) {
  uint8_t frame[FRAME_LEN];
  Serial.printf("M%d 锻炼 0x%02X × %d次\n", pos, val & 0x3F, cycles);
  for (int c = 0; c < cycles; c++) {
    // 阶段1: SMA+线圈, 400ms
    memset(frame, 0, FRAME_LEN);
    frame[posToChain[pos - 1]] = (val & 0x3F) | 0x40;
    sendRaw(frame, FRAME_LEN);
    Serial.printf("  [%d/%d] 解锁 ← 现在按压抬起\n", c + 1, cycles);
    delay(400);
    // 阶段2: 仅线圈, 300ms
    frame[posToChain[pos - 1]] = val & 0x3F;
    sendRaw(frame, FRAME_LEN);
    delay(300);
    // 阶段3: 全断, 600ms
    allOff();
    delay(600);
  }
  allOff();
  Serial.println("锻炼完成，已断电");
}

void processSerial() {
  if (!Serial.available()) return;

  if (rawMode) {
    if (Serial.available() >= NUM_MODULES) {
      Serial.readBytes(brailleData, NUM_MODULES);
      for (int i = 0; i < NUM_MODULES; i++) brailleData[i] &= 0x3F;
      newDataReady = true;
    }
    while (Serial.available() && Serial.peek() == '\n') Serial.read();
    return;
  }

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
  else if (line == "stop") {
    allOff();
    Serial.println("已全部断电");
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
    int pos; unsigned int val;
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
    int row; unsigned int val;
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
    int col; unsigned int val;
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
  else if (line == "raw on") {
    rawMode = true;
    Serial.println("进入 raw 模式 (15字节二进制帧)");
  }
  else if (line == "raw off") {
    rawMode = false;
    Serial.println("退出 raw 模式");
  }
  // ── 诊断命令 ──
  else if (line.startsWith("hold ")) {
    int pos; unsigned int val; int sec = 5;
    int n = sscanf(line.c_str(), "hold %d %x %d", &pos, &val, &sec);
    if (n >= 2 && pos >= 1 && pos <= NUM_MODULES) {
      sec = constrain(sec, 1, 10);
      cmdHold(pos, (uint8_t)val, sec);
    } else {
      Serial.println("格式: hold N XX [T]");
    }
  }
  else if (line.startsWith("ex ")) {
    int pos; unsigned int val; int cycles = 10;
    int n = sscanf(line.c_str(), "ex %d %x %d", &pos, &val, &cycles);
    if (n >= 2 && pos >= 1 && pos <= NUM_MODULES) {
      cycles = constrain(cycles, 1, 30);
      cmdEx(pos, (uint8_t)val, cycles);
    } else {
      Serial.println("格式: ex N XX [次数]");
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
  Serial.println("  V2.3 — 合并线圈通道诊断命令");
  Serial.println("================================");

  initGPIO();
  initSPI();

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
  Serial.println("按物理按钮触发扫描 | 串口输入 mode 切换模式");
  Serial.println();
}

void loop() {
  processSerial();
  handleButton();
  manageBLE();
  dispatchNotify();
  delay(10);
}