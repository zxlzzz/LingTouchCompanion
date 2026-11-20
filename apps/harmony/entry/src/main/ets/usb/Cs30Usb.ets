/** API 18 USB host bridge. Protocol and SensorAdapter state live in C++. */
import { usbManager, BusinessError } from '@kit.BasicServicesKit';
import core, { CameraUsbCommand, CameraUsbDevice, CameraResult } from 'libentry.so';

const OK = 0;
const DISCONNECTED = 8;
const INTERRUPTED = 9;
const IO_ERROR = 11;
const DRAIN_LIMIT_MS = 3000;

class IsoSlot {
  params: usbManager.UsbDataTransferParams;
  epoch: number;
  pending: boolean = false;
  descs: Int32Array;
  constructor(params: usbManager.UsbDataTransferParams, epoch: number) {
    this.params = params; this.epoch = epoch;
    this.descs = new Int32Array(params.isoPacketCount * 3);
  }
}

export class Cs30Usb {
  status: string = '未连接';
  path: string = '';
  callbacks: number = 0;
  callbackErrors: number = 0;
  diagnostics: string = '';
  private nativeDiagnostics: string = '';
  private transferDiagnostics: string = '';
  private badPackets: number = 0;
  private firstPacketError: string = '';
  private device: usbManager.USBDevice | undefined = undefined;
  private pipe: usbManager.USBDevicePipe | undefined = undefined;
  private claimed: usbManager.USBInterface[] = [];
  private slots: IsoSlot[] = [];
  private running: boolean = false;
  private pending: number = 0;
  private drainResolve: (() => void) | undefined = undefined;
  private drainWait: Promise<void> | undefined = undefined;
  private queue: Promise<void> = Promise.resolve();
  private commands: Promise<void> = Promise.resolve();
  private wanted: boolean = false;
  private busy: boolean = false;
  private retryCount: number = 0;
  private retryAt: number = Number.MAX_SAFE_INTEGER;
  private healthySince: number = 0;
  private deviceId: string = '';
  private timer: number = -1;
  private registered: boolean = false;

  private ensureBridge(): void {
    if (!this.registered) {
      core.cameraSetUsbHandler((command: CameraUsbCommand) => {
        // System operations remain serial. A drain timeout returns an error
        // without releasing buffers, so later commands can retry safely.
        this.commands = this.commands.then(() => this.handleUsb(command)).catch(() => {
          core.cameraCompleteUsb(command.requestId, IO_ERROR, 'USB 系统请求处理异常', new ArrayBuffer(0), []);
        });
      });
      this.registered = true;
    }
    if (this.timer < 0) this.timer = setInterval(() => { this.poll(); }, 500);
  }

  findDevice(): usbManager.USBDevice | undefined {
    return usbManager.getDevices().find((d: usbManager.USBDevice) => d.vendorId === 0x2207 && d.productId === 0x0016);
  }

  private findInterface(id: number, alt: number): usbManager.USBInterface | undefined {
    if (this.device === undefined) return undefined;
    for (const config of this.device.configs) {
      for (const iface of config.interfaces) {
        if (iface.id === id && iface.alternateSetting === alt) return iface;
      }
    }
    return undefined;
  }

  private async handleUsb(c: CameraUsbCommand): Promise<void> {
    let code = OK;
    let message = '';
    let data = new ArrayBuffer(0);
    const devices: CameraUsbDevice[] = [];
    try {
      if (c.operation === 0) {
        for (const d of usbManager.getDevices()) {
          if (d.vendorId === 0x2207 && d.productId === 0x0016)
            devices.push({ id: d.name, authorized: usbManager.hasRight(d.name) });
        }
      } else if (c.operation === 1) {
        const dev = usbManager.getDevices().find((d: usbManager.USBDevice) => d.name === c.deviceId &&
          d.vendorId === 0x2207 && d.productId === 0x0016);
        if (dev === undefined) { code = 1; message = '设备已移除，请重新连接'; }
        else if (!usbManager.hasRight(dev.name)) { code = 2; message = '请在前台连接并授予 USB 权限'; }
        else if (this.pipe !== undefined) { code = 3; message = '上一次 USB 连接尚未释放'; }
        else {
          const pipe = usbManager.connectDevice(dev);
          if (pipe === undefined) { code = 3; message = '无法打开 USB 连接'; }
          else { this.device = dev; this.pipe = pipe; }
        }
      } else if (c.operation === 6) {
        await this.drainIso();
      } else if (c.operation === 7) {
        await this.closePipe();
      } else {
        const pipe = this.pipe;
        if (pipe === undefined) { code = DISCONNECTED; message = 'USB 连接已关闭'; }
        else if (this.pending > 0 && !this.running) {
          code = IO_ERROR; message = 'USB 取消尚未完成，已保留接收缓冲，请稍后重试';
        } else if (c.operation === 2) {
          if (!this.claimed.some((i: usbManager.USBInterface) => i.id === c.interfaceNumber)) {
            const iface = this.findInterface(c.interfaceNumber, 0);
            if (iface === undefined) { code = 4; message = 'USB 接口描述符缺失'; }
            else if (usbManager.claimInterface(pipe, iface, true) !== 0) { code = 3; message = '接管 USB 接口失败'; }
            else this.claimed.push(iface);
          }
        } else if (c.operation === 3) {
          if (c.alternate !== 0 || this.claimed.some((i: usbManager.USBInterface) => i.id === c.interfaceNumber)) {
            const iface = this.findInterface(c.interfaceNumber, c.alternate);
            if (iface === undefined) { code = 4; message = 'USB alternate 描述符缺失'; }
            else if (usbManager.setInterface(pipe, iface) !== 0) { code = IO_ERROR; message = '切换 USB 接口失败'; }
          }
        } else if (c.operation === 4) {
          const input = (c.requestType & 0x80) !== 0;
          const bytes = input ? new Uint8Array(c.length) : new Uint8Array(c.data);
          const req: usbManager.USBDeviceRequestParams = { bmRequestType: c.requestType, bRequest: c.request,
            wValue: c.value, wIndex: c.index, wLength: c.length, data: bytes };
          const count = await usbManager.usbControlTransfer(pipe, req, c.timeoutMs);
          if (count < 0 || count > bytes.length || (!input && count !== c.length) || (input && c.length > 0 && count === 0)) {
            code = IO_ERROR; message = 'USB 控制请求返回长度异常：' + count;
          } else if (input) data = bytes.buffer.slice(0, count);
        } else if (c.operation === 5) {
          await this.queueIso(pipe, c);
        } else { code = IO_ERROR; message = '未知 USB 操作'; }
      }
    } catch (e) {
      const error = e as BusinessError;
      code = IO_ERROR; message = 'USB 操作 ' + c.operation + ' 失败：' + error.code + ' ' + error.message;
    }
    core.cameraCompleteUsb(c.requestId, code, message, data, devices);
  }

  private async queueIso(pipe: usbManager.USBDevicePipe, c: CameraUsbCommand): Promise<void> {
    if (this.pending !== 0 || this.slots.length !== 0) throw new Error('上一次接收队列尚未排空');
    this.badPackets = 0; this.firstPacketError = '';
    // Keep the negotiated packet size. Some tablet USB hosts cannot allocate a
    // 32-packet URB (96 KiB); shorten its duration rather than truncating packets.
    let packets = Math.min(c.packets, 8);
    const attempts: number[] = [];
    while (true) {
      attempts.push(packets);
      this.transferDiagnostics = 'USB请求：' + c.transfers + '个 × ' + packets + '包 × ' + c.packetBytes +
        'B，每请求 ' + (packets * c.packetBytes) + 'B；尝试包数 ' + attempts.join('→');
      this.updateDiagnostics(this.nativeDiagnostics);
      this.running = true;
      try {
        for (let i = 0; i < c.transfers; i++) {
          const params: usbManager.UsbDataTransferParams = {
            devPipe: pipe, flags: usbManager.UsbTransferFlags.USB_TRANSFER_SHORT_NOT_OK, endpoint: c.endpoint,
            type: usbManager.UsbEndpointTransferType.TRANSFER_TYPE_ISOCHRONOUS,
            timeout: c.isoTimeoutMs, length: packets * c.packetBytes,
            callback: (err: BusinessError, result: usbManager.SubmitTransferCallback) => {},
            userData: new Uint8Array(0), buffer: new Uint8Array(packets * c.packetBytes), isoPacketCount: packets
          };
          const slot = new IsoSlot(params, c.epoch);
          params.callback = (err: BusinessError, result: usbManager.SubmitTransferCallback) => { this.onTransfer(slot, err, result); };
          this.slots.push(slot);
          this.submit(slot);
        }
        return;
      } catch (e) {
        const error = e as BusinessError;
        // A partial queue still owns buffers. Wait for actual cancellation
        // callbacks before allocating or submitting the smaller replacement.
        await this.drainIso();
        // 14400012 is generic I/O, not proof of ENOMEM by itself. The affected
        // tablet's system log reported submiturb errno=12. Bound this workaround.
        if (error.code !== 14400012 || packets <= 1) {
          const failure = e as Error;
          throw failure;
        }
        packets = Math.max(1, Math.floor(packets / 2));
      }
    }
  }

  private submit(slot: IsoSlot): void {
    slot.pending = true; this.pending++;
    try { usbManager.usbSubmitTransfer(slot.params); }
    catch (e) {
      slot.pending = false; this.pending--; this.running = false;
      const error = e as Error;
      throw error;
    }
  }

  private onTransfer(slot: IsoSlot, err: BusinessError, result: usbManager.SubmitTransferCallback): void {
    if (!slot.pending) return;
    slot.pending = false; this.pending--; this.callbacks++;
    let action = '处理 USB 接收回调';
    try {
      if (this.running) {
        if (err && err.code) this.reportFault(slot.epoch, INTERRUPTED, '等时回调错误：' + err.code);
        else if (result.status === usbManager.UsbTransferStatus.TRANSFER_COMPLETED ||
          result.status === usbManager.UsbTransferStatus.TRANSFER_TIMED_OUT) {
          this.pushTransfer(slot, result, result.status === usbManager.UsbTransferStatus.TRANSFER_TIMED_OUT);
        } else if (result.status === usbManager.UsbTransferStatus.TRANSFER_NO_DEVICE) {
          this.reportFault(slot.epoch, DISCONNECTED, 'USB 设备已断开');
        } else {
          this.reportFault(slot.epoch, INTERRUPTED, '等时传输中断：' + result.status);
        }
        if (this.running) { action = '继续提交 USB 接收'; this.submit(slot); }
      }
    } catch (e) {
      const error = e as BusinessError;
      const codeText = typeof error.code === 'number' ? error.code + ' ' : '';
      this.reportFault(slot.epoch, INTERRUPTED, '无法' + action + '：' + codeText + error.message);
    }
    if (this.pending === 0 && this.drainResolve !== undefined) {
      const resolve = this.drainResolve; this.drainResolve = undefined; resolve();
    }
  }

  private pushTransfer(slot: IsoSlot, result: usbManager.SubmitTransferCallback, timedOut: boolean = false): void {
    const count = slot.params.isoPacketCount;
    const packetBytes = slot.params.length / count;
    const packets = result.isoPacketDescs;
    // A wrong count/stride makes every following packet offset untrustworthy.
    // Discard the whole batch in that case, but still poison its partial frame.
    let layoutValid = !timedOut && packets.length === count;
    let layoutError = timedOut ? 'USB 批次超时，已丢弃其所在图像组' :
      (layoutValid ? '' : '包数 ' + packets.length + '，预期 ' + count);
    if (layoutValid) {
      for (let i = 0; i < count; i++) {
        if (packets[i].length !== packetBytes) {
          layoutValid = false;
          layoutError = '包 ' + i + ' length=' + packets[i].length + '，预期 ' + packetBytes;
          break;
        }
      }
    }
    const descs = slot.descs;
    descs.fill(0);
    for (let i = 0; i < count; i++) {
      descs[3*i] = packetBytes;
      // Error packets can contain undefined/negative lengths. Never clamp a
      // broken packet into a successful empty packet or pass it as image data.
      let valid = false;
      let detail = layoutError;
      if (layoutValid) {
        const d = packets[i];
        valid = d.status === usbManager.UsbTransferStatus.TRANSFER_COMPLETED &&
          Number.isInteger(d.actualLength) && d.actualLength >= 0 && d.actualLength <= packetBytes;
        if (valid) descs[3*i+1] = d.actualLength;
        else detail = '包 ' + i + ' length=' + d.length + ' actualLength=' + d.actualLength + ' status=' + d.status;
      }
      if (!valid) {
        descs[3*i+2] = 1;
        this.badPackets++;
        if (this.firstPacketError === '') this.firstPacketError = detail;
      }
    }
    // Native copies this small batch into a fixed pool before returning. Its
    // dedicated worker assembles frames after this slot has been resubmitted.
    // Use an explicit byte buffer at this boundary, avoiding runtime-specific
    // TypedArray length units. Native still supports typed views for tools.
    core.cameraPushIso(slot.epoch, slot.params.buffer.buffer, descs.buffer);
  }

  private reportFault(epoch: number, code: number, message: string): void {
    this.callbackErrors++; this.running = false;
    core.cameraPushEvent(epoch, code, message);
  }

  private async drainIso(): Promise<void> {
    this.running = false;
    if (this.pending > 0) {
      if (this.drainWait === undefined) {
        this.drainWait = new Promise<void>((resolve) => { this.drainResolve = resolve; });
      }
      for (const slot of this.slots) {
        if (!slot.pending) continue;
        try { usbManager.usbCancelTransfer(slot.params); }
        catch (e) { /* Only an actual completion can release a buffer. */ }
      }
      let timer: number = -1;
      try {
        const completed = await Promise.race([
          this.drainWait.then(() => true),
          new Promise<boolean>((resolve) => { timer = setTimeout(() => resolve(false), DRAIN_LIMIT_MS); })
        ]);
        if (!completed && this.pending > 0) {
          throw new Error('USB 取消等待超时，仍有 ' + this.pending + ' 个请求；缓冲已保留，可稍后重试或重新插拔相机');
        }
      } finally {
        if (timer >= 0) clearTimeout(timer);
        // Retain slots, not another promise continuation on every failed retry.
        if (this.pending > 0) { this.drainWait = undefined; this.drainResolve = undefined; }
      }
    }
    this.slots = []; this.drainWait = undefined;
  }

  private async closePipe(): Promise<void> {
    await this.drainIso();
    const pipe = this.pipe;
    if (pipe !== undefined) {
      for (let i = this.claimed.length - 1; i >= 0; i--) {
        const iface = this.claimed[i];
        const alt0 = this.findInterface(iface.id, 0);
        try { if (alt0 !== undefined) usbManager.setInterface(pipe, alt0); } catch (e) {}
        try { usbManager.releaseInterface(pipe, iface); } catch (e) {}
      }
      usbManager.closePipe(pipe);
    }
    this.claimed = []; this.pipe = undefined; this.device = undefined;
  }

  private enqueue(operation: () => Promise<string>): Promise<string> {
    const next = this.queue.then(operation);
    this.queue = next.then(() => {}, () => {});
    return next;
  }

  async startSubmitTransfer(): Promise<string> {
    this.ensureBridge(); this.wanted = true;
    return this.enqueue(async () => {
      this.busy = true; this.retryCount = 0; this.retryAt = Number.MAX_SAFE_INTEGER;
      try {
        if (!this.wanted) return '';
        const dev = this.findDevice();
        if (dev === undefined) { this.status = '未找到 CS30，请检查连接和供电'; return this.status; }
        this.deviceId = dev.name;
        if (!usbManager.hasRight(dev.name) && !await usbManager.requestRight(dev.name)) {
          this.status = 'USB 未授权，请重新点击连接'; return this.status;
        }
        if (!this.wanted) return '';
        this.status = '正在启动深度和彩色取流';
        const result = await core.cameraOperation('connect', dev.name, true);
        this.applyResult(result);
        return result.code === OK ? '' : result.message;
      } catch (e) { this.status = '连接失败：' + JSON.stringify(e); return this.status; }
      finally { this.busy = false; }
    });
  }

  async restart(): Promise<string> {
    this.ensureBridge();
    return this.enqueue(async () => {
      this.busy = true;
      try {
        const dev = this.findDevice();
        if (dev === undefined) return '未找到 CS30，请检查连接和供电';
        // Reopen the pipe as well as restarting the stream after a fault.
        const result = await core.cameraOperation('connect', dev.name, true);
        this.applyResult(result); return result.code === OK ? '' : result.message;
      } finally { this.busy = false; }
    });
  }

  async stop(): Promise<void> {
    this.wanted = false; this.retryAt = Number.MAX_SAFE_INTEGER;
    await this.enqueue(async () => {
      if (!this.registered) return '';
      this.busy = true;
      try {
        const result = await core.cameraOperation('close', '', true);
        this.status = result.code === OK ? '未连接' : result.message; this.path = '';
        return '';
      } finally { this.busy = false; }
    });
  }

  async shutdown(): Promise<void> {
    if (this.timer >= 0) { clearInterval(this.timer); this.timer = -1; }
    await this.stop();
  }

  private recoverable(code: number): boolean {
    return code === 3 || code === 5 || code === DISCONNECTED || code === INTERRUPTED || code === IO_ERROR;
  }

  private applyResult(result: CameraResult): void {
    const status = core.cameraStatus();
    this.healthySince = 0; this.status = status.message;
    this.updateDiagnostics(status.diagnostics);
    this.path = result.code === OK ? 'submit' : '';
    if (result.code !== OK) this.scheduleRetry(result.code);
  }

  private updateDiagnostics(nativeDiagnostics: string): void {
    this.nativeDiagnostics = nativeDiagnostics;
    this.diagnostics = nativeDiagnostics + (nativeDiagnostics !== '' && this.transferDiagnostics !== '' ? '；' : '') +
      this.transferDiagnostics;
    if (this.badPackets > 0) this.diagnostics += '；USB坏包 ' + this.badPackets + '；首个异常：' + this.firstPacketError;
  }

  private scheduleRetry(code: number): void {
    this.retryAt = Number.MAX_SAFE_INTEGER;
    if (!this.wanted || !this.recoverable(code)) return;
    if (this.retryCount >= 3) { this.status += '；自动重试已结束，请检查后重新连接'; return; }
    this.retryAt = Date.now() + 1000 * Math.pow(2, this.retryCount++);
  }

  private poll(): void {
    if (!this.wanted || this.busy) return;
    if (this.path !== '') {
      const status = core.cameraStatus(); this.status = status.message; this.updateDiagnostics(status.diagnostics);
      if (this.recoverable(status.code)) {
        this.scheduleRetry(status.code); this.path = ''; this.busy = true;
        this.enqueue(async () => {
          try { await core.cameraOperation('close', '', true); return ''; }
          finally { this.busy = false; }
        });
      } else if (status.receiving) {
        if (this.healthySince === 0) this.healthySince = Date.now();
        if (Date.now() - this.healthySince >= 10000) this.retryCount = 0;
      }
      return;
    }
    // Detect unplug/replug; permission prompts only occur on user action.
    const dev = this.findDevice();
    if (dev === undefined) { this.deviceId = ''; return; }
    if (dev.name !== this.deviceId) { this.deviceId = dev.name; this.retryCount = 0; this.retryAt = Date.now(); }
    if (Date.now() < this.retryAt) return;
    this.retryAt = Number.MAX_SAFE_INTEGER;
    if (!usbManager.hasRight(dev.name)) { this.status = '相机已插入，请在前台连接并授权'; return; }
    this.busy = true;
    this.enqueue(async () => {
      try {
        if (!this.wanted) return '';
        this.status = '正在恢复深度和彩色取流';
        const result = await core.cameraOperation('connect', dev.name, true);
        this.applyResult(result); return '';
      } catch (e) {
        this.status = '恢复相机失败：' + JSON.stringify(e);
        this.path = '';
        this.scheduleRetry(IO_ERROR); return '';
      } finally { this.busy = false; }
    });
  }
}

export const cs30Usb = new Cs30Usb();
