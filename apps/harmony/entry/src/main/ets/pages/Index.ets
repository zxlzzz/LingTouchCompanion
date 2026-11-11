/**
 * 骨架界面：USB 授权 → 打开 CS30 → 核心开流 → 读屏可读的 9×6 栅格 → BLE 写一帧到手柄；长时任务。
 * 界面不放假数据：没连设备显示「未连接」，拿不到的值不显示。
 */
import { abilityAccessCtrl, common, Permissions } from '@kit.AbilityKit';
import core from 'libentry.so';
import { Cs30Usb } from '../usb/Cs30Usb';
import { HandleCallbacks, HandleLink, HandleState } from '../device/HandleLink';
import { WitImuLink } from '../device/WitImuLink';
import { startKeepAlive, stopKeepAlive } from '../common/KeepAlive';

interface GroundJson {
  ok: boolean;
  height_m?: number;
  pitch_deg?: number;
}

interface GridJson {
  error?: string;
  digest?: string;
  status: string;
  failure: string;
  frame_id: number | null;
  cells: string | null;
  ground: GroundJson;
}

interface StatsJson {
  transfers: number;
  frames: number;
  incomplete: number;
  packet_errors: number;
  uvc_errors: number;
  frames_processed: number;
  frames_dropped_busy: number;
  last_process_ms: number;
}

class GridRow {
  key: string;
  text: string;
  label: string;

  constructor(key: string, text: string, label: string) {
    this.key = key;
    this.text = text;
    this.label = label;
  }
}

const POLICY_UNSET = 0;
const POLICY_FLAT = 1;
const POLICY_RAISED = 2;
const POLL_MS = 200;

const usb = new Cs30Usb();
const callbacks = new HandleCallbacks();
const handle = new HandleLink(callbacks);
const imu = new WitImuLink();

function symbol(c: string): string {
  return c === '0' ? '·' : (c === '1' ? '■' : '?');
}

function word(c: string): string {
  return c === '0' ? '空' : (c === '1' ? '障碍' : '未知');
}

function stateText(s: HandleState): string {
  if (s === 'connected') {
    return '已连接';
  }
  if (s === 'connecting') {
    return '连接中';
  }
  if (s === 'scanning') {
    return '扫描中';
  }
  return '未连接';
}

@Entry
@Component
struct Index {
  @State coreError: string = '';
  @State cameraText: string = '相机：未连接';
  @State gridStatus: string = '栅格：未连接';
  @State rows: GridRow[] = [];
  @State handleText: string = '手柄：未连接';
  @State imuText: string = 'IMU：未连接';
  @State policy: number = POLICY_UNSET;
  @State sendText: string = '';
  @State continuous: boolean = false;
  @State keepAlive: boolean = false;
  @State planeText: string = '';
  @State detailText: string = '';
  private timer: number = -1;
  private framesSent: number = 0;
  private lastFrames: number = -1;
  private lastFramesAt: number = 0;
  private fps: number = -1;

  aboutToAppear(): void {
    this.coreError = core.init();
    if (!this.coreError) {
      this.policy = core.configUnknownPolicy();  // 0 = 待 Hsinlung 定，不预选
    }
    callbacks.onState = (s: HandleState) => {
      this.handleText = `手柄：${stateText(s)}`;
    };
    callbacks.onFrameDone = (shown: boolean) => {
      if (this.continuous) {
        setTimeout(() => this.sendLatest(), 50);  // 持续发送：每次刷新完成（或超时）后发最新一帧
      }
    };
    callbacks.onButton = () => {
      this.sendText = '手柄：按键扫描请求（0x04）';
    };
    this.requestPermissions();
    this.timer = setInterval(() => this.refresh(), POLL_MS);
  }

  aboutToDisappear(): void {
    imu.disconnect();
    if (this.timer >= 0) {
      clearInterval(this.timer);
    }
  }

  private context(): common.UIAbilityContext {
    return getContext(this) as common.UIAbilityContext;
  }

  private async requestPermissions(): Promise<void> {
    const perms: Permissions[] = [
      'ohos.permission.ACCESS_BLUETOOTH',
      'ohos.permission.APPROXIMATELY_LOCATION',
      'ohos.permission.LOCATION'
    ];
    try {
      await abilityAccessCtrl.createAtManager().requestPermissionsFromUser(this.context(), perms);
    } catch (e) {
      this.detailText = `申请权限失败：${JSON.stringify(e)}`;
    }
  }

  private sendLatest(): string {
    if (this.coreError) {
      return this.coreError;
    }
    if (this.policy === POLICY_UNSET) {
      return '状态 2 的触点表示还没选（平或凸），不能发帧';
    }
    const frame = core.encodeLatest(this.policy);
    if (frame === undefined) {
      const err = core.lastError();
      if (this.continuous) {
        setTimeout(() => this.sendLatest(), 500);  // 还没有栅格等情况，0.5 s 后重试
      }
      return err;
    }
    const err = handle.show(new Uint8Array(frame));
    if (!err) {
      this.framesSent++;
    } else if (this.continuous) {
      setTimeout(() => this.sendLatest(), 500);
    }
    return err;
  }

  private refresh(): void {
    if (this.coreError) {
      this.gridStatus = `核心初始化失败：${this.coreError}`;
      return;
    }
    this.cameraText = `相机：${usb.status}`;
    const sample = core.latestImu();
    this.imuText = sample ? `IMU：${imu.state}\n${sample}` : `IMU：${imu.state}`;
    const g = JSON.parse(core.gridJson()) as GridJson;
    if (g.status === 'ok') {
      this.gridStatus = `栅格：正常（离地 ${(g.ground.height_m ?? 0).toFixed(2)} m，俯仰 ${(g.ground.pitch_deg ?? 0).toFixed(0)}°）`;
    } else if (g.status === 'ground_fit_failed') {
      this.gridStatus = `栅格：降级，整张为未知（地面拟合失败：${g.failure}）`;
    } else if (g.status === 'no_calibration') {
      this.gridStatus = `栅格：没有可用内参（${g.failure}）`;
    } else {
      this.gridStatus = '栅格：未连接';
    }
    const rows: GridRow[] = [];
    for (let r = 0; r < 6; r++) {
      const far = 3.4 - 0.4 * r;
      const label = `第 ${r + 1} 行（${(far - 0.4).toFixed(1)} 到 ${far.toFixed(1)} 米）`;
      if (g.cells === null) {
        rows.push(new GridRow(`${r}:-`, '—', `${label}：无数据`));
        continue;
      }
      const part = g.cells.substring(r * 9, r * 9 + 9);
      const symbols: string[] = [];
      const words: string[] = [];
      for (let c = 0; c < 9; c++) {
        symbols.push(symbol(part.charAt(c)));
        words.push(word(part.charAt(c)));
      }
      rows.push(new GridRow(`${r}:${part}`, symbols.join(' '), `${label}：${words.join('，')}`));
    }
    this.rows = rows;

    const st = JSON.parse(core.statsJson()) as StatsJson;
    const now = Date.now();
    if (this.lastFrames < 0) {
      this.lastFrames = st.frames_processed;
      this.lastFramesAt = now;
    } else if (now - this.lastFramesAt >= 2000) {
      this.fps = (st.frames_processed - this.lastFrames) * 1000 / (now - this.lastFramesAt);
      this.lastFrames = st.frames_processed;
      this.lastFramesAt = now;
    }
    const lines: string[] = [];
    if (usb.path !== '' && this.fps >= 0) {
      lines.push(`处理帧率 ${this.fps.toFixed(1)} 帧/秒（实测，最近 2 秒）`);
    }
    lines.push(`传输 ${st.transfers}（回调 ${usb.callbacks}，回调错误 ${usb.callbackErrors}），拼帧 ${st.frames}，` +
      `丢弃不完整 ${st.incomplete}，包错误 ${st.packet_errors}，UVC 错误位 ${st.uvc_errors}，` +
      `计算忙时替换 ${st.frames_dropped_busy}，上一帧计算 ${st.last_process_ms} ms`);
    lines.push(`已发帧 ${this.framesSent}，手柄确认刷新 ${handle.framesShown}`);
    lines.push(core.deviceSummary());
    this.detailText = lines.join('\n');
  }

  build() {
    Scroll() {
      Column({ space: 8 }) {
        Text('灵触 · 端侧骨架').fontSize(24)
        Text(this.cameraText).fontSize(16)
        Button('连接相机（usbSubmitTransfer）').onClick(async () => {
          const err = await usb.startSubmitTransfer();
          this.cameraText = err ? `相机：开流失败：${err}` : `相机：${usb.status}`;
        })
        Button('连接相机（备选：fd + libusb）').onClick(async () => {
          const err = await usb.startViaFd();
          this.cameraText = err ? `相机：开流失败：${err}` : `相机：${usb.status}`;
        })
        Button('断开相机').onClick(async () => {
          await usb.stop();
        })

        Text(this.gridStatus).fontSize(16)
        Text('从远到近 6 行、从左到右 9 列；· 空  ■ 障碍  ? 未知（相机视角，未做穿戴镜像）').fontSize(13)
        ForEach(this.rows, (row: GridRow) => {
          Text(row.text)
            .fontSize(24)
            .fontFamily('monospace')
            .accessibilityText(row.label)
        }, (row: GridRow) => row.key)

        Text(this.handleText).fontSize(16)
        Button('扫描并连接手柄').onClick(() => {
          handle.scanAndConnect();
        })

        Text(this.imuText).fontSize(16)
        Button('扫描并连接 IMU').onClick(() => {
          imu.scanAndConnect();
        })
        Button('断开 IMU').onClick(() => {
          imu.disconnect();
        })

        Text('未知（状态 2）在触点上表示为：（待 Hsinlung 定，每次需手选）').fontSize(14)
        Row({ space: 12 }) {
          Radio({ value: 'flat', group: 'policy' })
            .checked(this.policy === POLICY_FLAT)
            .onChange((checked: boolean) => {
              if (checked) {
                this.policy = POLICY_FLAT;
              }
            })
          Text('平')
          Radio({ value: 'raised', group: 'policy' })
            .checked(this.policy === POLICY_RAISED)
            .onChange((checked: boolean) => {
              if (checked) {
                this.policy = POLICY_RAISED;
              }
            })
          Text('凸')
        }
        Button('发送一帧到手柄').onClick(() => {
          const err = this.sendLatest();
          this.sendText = err ? `没有发送：${err}` : '已发出，等待手柄刷新完成';
        })
        Text(this.sendText).fontSize(14)
        Row({ space: 8 }) {
          Toggle({ type: ToggleType.Switch, isOn: this.continuous })
            .onChange((on: boolean) => {
              this.continuous = on;
              if (on) {
                this.sendLatest();
              }
            })
          Text('持续发送（后台测试用）')
        }
        Row({ space: 8 }) {
          Toggle({ type: ToggleType.Switch, isOn: this.keepAlive })
            .onChange(async (on: boolean) => {
              this.keepAlive = on;
              const err = on ? await startKeepAlive(this.context()) : await stopKeepAlive(this.context());
              if (err) {
                this.sendText = err;
              }
            })
          Text('后台运行（长时任务：蓝牙交互 + 定位）')
        }

        Button('平面检查（对着平整的墙或斜看地面）').onClick(() => {
          this.planeText = core.planeCheck();
        })
        Text(this.planeText).fontSize(13).fontFamily('monospace')
        // 真机验收第 1、3 条：帧文件在应用沙箱 files 目录（hdc file send / recv 到 /data/app/el2/100/base/com.lingtouch.companion/haps/entry/files/）
        Button('保存当前帧（latest_frame.bin）').onClick(() => {
          const path = `${this.context().filesDir}/latest_frame.bin`;
          const err = core.saveLatestFrame(path);
          this.planeText = err ? `没有保存：${err}` : `已保存：${path}`;
        })
        Button('核对帧文件（frame.bin → 栅格与摘要）').onClick(() => {
          const path = `${this.context().filesDir}/frame.bin`;
          const g = JSON.parse(core.processFrameFile(path)) as GridJson;
          if (g.error !== undefined) {
            this.planeText = `核对失败：${g.error}（${path}）`;
          } else {
            const cells = g.cells ?? '';
            const lines: string[] = [];
            for (let r = 0; r < 6; r++) {
              lines.push(cells.substring(r * 9, r * 9 + 9));
            }
            this.planeText = `frame.bin：${g.status}，摘要 ${g.digest ?? ''}\n${lines.join('\n')}`;
          }
        })
        Button('显示当前参数').onClick(() => {
          this.planeText = core.configText();
        })
        Text(this.detailText).fontSize(13)
      }
      .padding(16)
      .alignItems(HorizontalAlign.Start)
      .width('100%')
    }
  }
}
