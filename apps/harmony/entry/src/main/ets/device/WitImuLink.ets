import { ble, constant } from '@kit.ConnectivityKit';
import core from 'libentry.so';

const SERVICE_UUID = '0000ffe5-0000-1000-8000-00805f9a34fb';
const NOTIFY_UUID = '0000ffe4-0000-1000-8000-00805f9a34fb';
const SCAN_MS = 8000;
const CONNECT_MS = 15000;

export class WitImuLink {
  state: string = '未连接';
  private scanner?: ble.BleScanner;
  private client?: ble.GattClientDevice;
  private scanTimer: number = -1;
  private connectTimer: number = -1;
  private inputStarted: boolean = false;

  async scanAndConnect(): Promise<void> {
    this.disconnect();
    let best: ble.ScanResult | undefined;
    let bestIs901: boolean = false;
    try {
      // 单独的扫描器可以与现有手柄扫描独立启动和停止。
      const scanner = ble.createBleScanner();
      this.scanner = scanner;
      scanner.on('BLEDeviceFind', (report: ble.ScanReport) => {
        if (scanner !== this.scanner) {
          return;
        }
        for (const result of report.scanResult) {
          const name = result.deviceName.toUpperCase();
          const is901 = name.startsWith('WT901BLE') || name.startsWith('BWT901BLE');
          if (result.connectable && (is901 || name.startsWith('WT')) &&
              (best === undefined || (is901 && !bestIs901) ||
               (is901 === bestIs901 && result.rssi > best.rssi))) {
            best = result;
            bestIs901 = is901;
          }
        }
      });
      this.state = '扫描中';
      const options: ble.ScanOptions = { interval: 0, dutyMode: ble.ScanDuty.SCAN_MODE_LOW_LATENCY };
      try {
        // API 18 要求过滤器数组非空，空条件对象匹配所有广播。
        const filter: ble.ScanFilter = {};
        await scanner.startScan([filter], options);
      } catch (e) {
        if (scanner === this.scanner) {
          this.disconnect('扫描失败，请检查蓝牙和权限');
        }
        return;
      }
      if (scanner !== this.scanner) {
        // 用户可能在异步启动完成前已经断开。
        try { scanner.stopScan().catch(() => {}); } catch (e) {}
        return;
      }
      this.scanTimer = setTimeout(() => {
        this.stopScan();
        if (best === undefined) {
          this.state = '没找到维特 IMU';
        } else {
          this.connect(best.deviceId);
        }
      }, SCAN_MS);
    } catch (e) {
      this.disconnect('无法启动 IMU 扫描');
    }
  }

  disconnect(reason: string = '未连接'): void {
    this.stopScan();
    this.clearConnectTimer();
    const client = this.client;
    this.client = undefined;
    this.inputStarted = false;
    core.stopImu();
    if (client !== undefined) {
      try { client.off('BLEConnectionStateChange'); } catch (e) {}
      try { client.off('BLECharacteristicChange'); } catch (e) {}
      try { client.disconnect(); } catch (e) {}
      try { client.close(); } catch (e) {}
    }
    this.state = reason;
  }

  private stopScan(): void {
    if (this.scanTimer >= 0) {
      clearTimeout(this.scanTimer);
      this.scanTimer = -1;
    }
    const scanner = this.scanner;
    this.scanner = undefined;
    if (scanner !== undefined) {
      try { scanner.off('BLEDeviceFind'); } catch (e) {}
      try { scanner.stopScan().catch(() => {}); } catch (e) {}
    }
  }

  private clearConnectTimer(): void {
    if (this.connectTimer >= 0) {
      clearTimeout(this.connectTimer);
      this.connectTimer = -1;
    }
  }

  private connect(deviceId: string): void {
    this.state = '连接中';
    try {
      const client = ble.createGattClientDevice(deviceId);
      this.client = client;
      client.on('BLEConnectionStateChange', (change: ble.BLEConnectionChangeState) => {
        if (client !== this.client) {
          return;
        }
        if (change.state === constant.ProfileConnectionState.STATE_CONNECTED) {
          this.subscribe(client);
        } else if (change.state === constant.ProfileConnectionState.STATE_DISCONNECTED) {
          this.disconnect('连接断开');
        }
      });
      client.on('BLECharacteristicChange', (characteristic: ble.BLECharacteristic) => {
        if (client === this.client && this.inputStarted &&
            characteristic.characteristicUuid.toLowerCase() === NOTIFY_UUID) {
          // 同步进入 native，在入口用深度帧的时钟取时。
          core.pushImuNotify(characteristic.characteristicValue);
        }
      });
      client.connect();
      this.connectTimer = setTimeout(() => this.disconnect('连接或订阅超时'), CONNECT_MS);
    } catch (e) {
      this.disconnect('无法建立 BLE 连接');
    }
  }

  private async subscribe(client: ble.GattClientDevice): Promise<void> {
    try {
      const services: ble.GattService[] = await client.getServices();
      if (client !== this.client) {
        return;
      }
      const service = services.find((s: ble.GattService) => s.serviceUuid.toLowerCase() === SERVICE_UUID);
      const notify = service?.characteristics.find((c: ble.BLECharacteristic) =>
        c.characteristicUuid.toLowerCase() === NOTIFY_UUID);
      if (notify === undefined) {
        this.disconnect('设备没有 FFE5/FFE4 通知特征');
        return;
      }
      const error = core.startImu();
      if (error) {
        this.disconnect(error);
        return;
      }
      this.inputStarted = true;
      await client.setCharacteristicChangeNotification(notify, true);
      if (client === this.client) {
        this.clearConnectTimer();
        this.state = '已订阅 FFE4';
      }
    } catch (e) {
      if (client === this.client) {
        this.disconnect('订阅 FFE4 失败');
      }
    }
  }
}
