import { image } from '@kit.ImageKit';
import core, { CameraPreviewFrame } from 'libentry.so';

export class PreviewImages {
  frameId: number;
  color: image.PixelMap | undefined;
  depth: image.PixelMap | undefined;

  constructor(frameId: number, color: image.PixelMap | undefined, depth: image.PixelMap | undefined) {
    this.frameId = frameId;
    this.color = color;
    this.depth = depth;
  }
}

class PreviewLane {
  map: image.PixelMap | undefined = undefined;
  retired: image.PixelMap | undefined = undefined;
  frameId: number = 0;
  afterFrame: number = 0;
  busy: boolean = false;
  startedAt: number = 0;
  waitingAt: number = 0;
  releasing: number = 0;
  timedOut: boolean = false;
  timeouts: number = 0;
  renderResets: number = 0;
  recoveries: number = 0;
  lastMs: number = 0;
  operation: string = '';
  error: string = '';
}

const WAIT_LIMIT_MS = 2000;

// One active lane and at most one quarantined SDK job per channel. A timeout
// never pretends to cancel the old job; late results are released, not shown.
// Color decoding and source cleanup cannot hold up depth presentation.
export class CameraPreview {
  private active: boolean = false;
  private generation: number = 0;
  private epoch: number = -1;
  private receiving: boolean = false;
  private color: PreviewLane = new PreviewLane();
  private depth: PreviewLane = new PreviewLane();
  private oldColor: PreviewLane | undefined = undefined;
  private oldDepth: PreviewLane | undefined = undefined;
  private onChange: (images: PreviewImages | undefined, message: string) => void;

  constructor(onChange: (images: PreviewImages | undefined, message: string) => void) {
    this.onChange = onChange;
  }

  start(): void { this.active = true; }

  stop(): void {
    this.active = false;
    this.clear('预览已暂停');
  }

  private release(map: image.PixelMap | undefined, lane: PreviewLane): void {
    if (map === undefined) return;
    lane.releasing++;
    try {
      map.release().catch(() => {}).finally(() => { lane.releasing--; });
    } catch (_) { lane.releasing--; }
  }

  colorDisplayed(): void { this.displayed(this.color); }
  depthDisplayed(): void { this.displayed(this.depth); }

  private displayed(lane: PreviewLane): void {
    this.release(lane.retired, lane);
    lane.retired = undefined;
    lane.waitingAt = 0;
  }

  private clearLane(lane: PreviewLane): void {
    this.release(lane.map, lane);
    this.displayed(lane);
    lane.map = undefined;
    lane.frameId = 0;
    lane.afterFrame = 0;
    lane.error = '';
    // Keep busy set until the actual SDK job finishes, even across sessions.
  }

  private clear(message: string): void {
    this.generation++;
    this.onChange(undefined, message);
    this.clearLane(this.color);
    this.clearLane(this.depth);
  }

  private emit(): void {
    const errors: string[] = [];
    if (this.color.error !== '') errors.push(this.color.error);
    if (this.depth.error !== '') errors.push(this.depth.error);
    this.onChange(new PreviewImages(Math.max(this.color.frameId, this.depth.frameId),
      this.color.map, this.depth.map), errors.length > 0 ? errors.join('；') : '相机实时画面');
  }

  private available(lane: PreviewLane, name: string, now: number): boolean {
    if (lane.busy) {
      if (!lane.timedOut && now - lane.startedAt >= WAIT_LIMIT_MS) {
        lane.timedOut = true;
        lane.timeouts++;
        lane.error = `${name}${lane.operation}超时，已限制该路任务`;
        this.emit();
      }
      return false;
    }
    if (lane.releasing >= 2) {
      lane.error = `${name}图像资源释放较慢，已限制该路任务`;
      this.emit();
      return false;
    }
    if (lane.retired !== undefined) {
      if (now - lane.waitingAt < WAIT_LIMIT_MS) return false;
      // No renderer completion: clear the source before releasing its maps,
      // then resume on the next poll with a strict resource bound.
      lane.renderResets++;
      const old = lane.map;
      lane.map = undefined;
      lane.frameId = 0;
      lane.error = `${name}显示等待超时，已重置预览`;
      this.emit();
      this.release(old, lane);
      this.displayed(lane);
      return false;
    }
    return true;
  }

  private recoverLane(lane: PreviewLane, old: PreviewLane | undefined, name: string,
    now: number): PreviewLane {
    const stuckJob = lane.busy && now - lane.startedAt >= WAIT_LIMIT_MS;
    const stuckRelease = lane.releasing >= 2 && now - lane.startedAt >= WAIT_LIMIT_MS;
    if ((!stuckJob && !stuckRelease) || (old !== undefined && (old.busy || old.releasing > 0))) return lane;
    // Keep ownership of the outstanding task in the quarantine slot. There is
    // no third replacement while it remains outstanding, including reconnects.
    lane.timedOut = true;
    this.clearLane(lane);
    const next = new PreviewLane();
    next.timeouts = lane.timeouts + 1;
    next.recoveries = lane.recoveries + 1;
    next.renderResets = lane.renderResets;
    next.error = `${name}预览等待超时，已隔离旧任务并重建该路预览`;
    return next;
  }

  private recover(now: number): void {
    if (this.oldColor !== undefined && !this.oldColor.busy && this.oldColor.releasing === 0) this.oldColor = undefined;
    if (this.oldDepth !== undefined && !this.oldDepth.busy && this.oldDepth.releasing === 0) this.oldDepth = undefined;
    const color = this.recoverLane(this.color, this.oldColor, '彩色', now);
    const depth = this.recoverLane(this.depth, this.oldDepth, '深度', now);
    const changed = color !== this.color || depth !== this.depth;
    if (color !== this.color) { this.oldColor = this.color; this.color = color; }
    if (depth !== this.depth) { this.oldDepth = this.depth; this.depth = depth; }
    if (changed) this.emit();
  }

  private valid(generation: number, epoch: number): boolean {
    if (!this.active || generation !== this.generation) return false;
    const state = core.cameraStatus();
    return state.receiving && state.previewEpoch === epoch;
  }

  private publish(lane: PreviewLane, map: image.PixelMap, frame: CameraPreviewFrame, generation: number): void {
    if (lane.timedOut || (lane !== this.color && lane !== this.depth) || !this.valid(generation, frame.epoch)) {
      this.release(map, lane);
      return;
    }
    lane.retired = lane.map;
    lane.map = map;
    lane.frameId = frame.frameId;
    lane.waitingAt = lane.retired !== undefined ? Date.now() : 0;
    lane.error = '';
    this.emit();
  }

  private begin(lane: PreviewLane, frameId: number): void {
    lane.busy = true;
    lane.timedOut = false;
    lane.startedAt = Date.now();
    lane.afterFrame = frameId;
  }

  private async decodeColor(frame: CameraPreviewFrame, generation: number): Promise<void> {
    const lane = this.color;
    this.begin(lane, frame.frameId);
    lane.operation = '解码';
    let source: image.ImageSource | undefined = undefined;
    try {
      if (frame.colorJpeg.byteLength === 0) throw new Error('当前帧没有彩色图像');
      source = image.createImageSource(frame.colorJpeg);
      const map = await source.createPixelMap({ desiredSize: { width: 480, height: 270 } });
      this.publish(lane, map, frame, generation);
    } catch (e) {
      if (this.valid(generation, frame.epoch)) {
        lane.error = `彩色预览解码失败：${JSON.stringify(e)}`;
        this.emit();
      }
    } finally {
      // Source cleanup stays part of this one bounded job, but happens after
      // presentation and independently of depth processing.
      lane.operation = '资源释放';
      if (source !== undefined) {
        try { await source.release(); } catch (_) {}
      }
      lane.lastMs = Date.now() - lane.startedAt;
      lane.busy = false;
    }
  }

  private async decodeDepth(frame: CameraPreviewFrame, generation: number): Promise<void> {
    const lane = this.depth;
    this.begin(lane, frame.frameId);
    lane.operation = '生成';
    try {
      const map = await image.createPixelMap(frame.depthRgba, {
        size: { width: frame.depthWidth, height: frame.depthHeight },
        srcPixelFormat: image.PixelMapFormat.RGBA_8888,
        pixelFormat: image.PixelMapFormat.RGBA_8888,
        editable: false,
        alphaType: image.AlphaType.OPAQUE
      });
      this.publish(lane, map, frame, generation);
    } catch (e) {
      if (this.valid(generation, frame.epoch)) {
        lane.error = `深度预览生成失败：${JSON.stringify(e)}`;
        this.emit();
      }
    } finally {
      lane.lastMs = Date.now() - lane.startedAt;
      lane.busy = false;
    }
  }

  diagnostics(): string {
    return `预览帧：彩色 ${this.color.frameId}，深度 ${this.depth.frameId}；` +
      `生成耗时 ${this.color.lastMs}/${this.depth.lastMs} ms；` +
      `等待超时 ${this.color.timeouts}/${this.depth.timeouts}，显示重置 ${this.color.renderResets}/${this.depth.renderResets}；` +
      `预览重建 ${this.color.recoveries}/${this.depth.recoveries}，隔离任务 ${this.oldColor !== undefined ? 1 : 0}/${this.oldDepth !== undefined ? 1 : 0}；` +
      `待释放图像 ${this.color.releasing}/${this.depth.releasing}`;
  }

  progress(): string {
    return `彩色帧 ${this.color.frameId}，深度帧 ${this.depth.frameId}`;
  }

  async update(): Promise<void> {
    if (!this.active) return;
    const state = core.cameraStatus();
    if (state.previewEpoch !== this.epoch) {
      this.epoch = state.previewEpoch;
      this.clear('等待当前连接的画面');
    }
    if (!state.receiving) {
      if (this.receiving) this.clear('尚无相机画面');
      this.receiving = false;
      return;
    }
    this.receiving = true;
    const now = Date.now();
    this.recover(now);
    const color = this.available(this.color, '彩色', now);
    const depth = this.available(this.depth, '深度', now);
    const channels = (color ? 1 : 0) + (depth ? 2 : 0);
    if (channels === 0) return;
    const after = Math.min(color ? this.color.afterFrame : Number.MAX_SAFE_INTEGER,
      depth ? this.depth.afterFrame : Number.MAX_SAFE_INTEGER);
    const frame = core.cameraPreview(after, channels);
    if (frame === undefined) return;
    const generation = this.generation;
    // The controller tick must finish even when an ImageKit task does not.
    if (color && frame.frameId > this.color.afterFrame) this.decodeColor(frame, generation).catch(() => {});
    if (depth && frame.frameId > this.depth.afterFrame) this.decodeDepth(frame, generation).catch(() => {});
  }
}
