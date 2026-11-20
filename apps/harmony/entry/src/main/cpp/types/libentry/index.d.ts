// libentry.so（apps/harmony/entry/src/main/cpp/napi_init.cpp）导出的接口。
export interface ProtocolInfo {
  vendorId: number;
  productId: number;
  isoEndpoint: number;
  controlTimeoutMs: number;
  libusbAvailable: boolean;
}

export interface StartupStep {
  kind: string;  // 'control' | 'alt' | 'queue_iso'
  isIn: boolean;
  requestType: number;
  request: number;
  value: number;
  index: number;
  length: number;
  data: ArrayBuffer;  // OUT 请求的数据（IN 请求为空）
  interfaceNumber: number;
  altSetting: number;
  isoTransfers: number;
  isoTransferBytes: number;
  isoPackets: number;
  isoTimeoutMs: number;
  settleMs: number;  // 这一步之后、下一步之前要等的毫秒数
}

export const init: () => string;
export const protocolInfo: () => ProtocolInfo;
export const startupStepCount: () => number;
export const startupStep: (index: number) => StartupStep;
export const onStartupResponse: (index: number, data: ArrayBuffer) => string;
export const finishStartup: () => string;
export const resetStream: () => void;
// descs：每 3 个数一组 [申请长度, 实际长度, 状态]
export const pushIsoTransfer: (buffer: ArrayBuffer, descs: Int32Array) => void;
export const gridJson: () => string;
export const statsJson: () => string;
export const deviceSummary: () => string;
export const configText: () => string;
export const configUnknownPolicy: () => number;
export const encodeLatest: (policy: number) => ArrayBuffer | undefined;
export const lastError: () => string;
export const planeCheck: () => string;
export const saveLatestFrame: (path: string) => string;
export const processFrameFile: (path: string) => string;
export const openFd: (fd: number) => string;
export const closeFd: () => void;
export const libusbLog: () => string;

export const startImu: () => string;
export const stopImu: () => void;
export const pushImuNotify: (data: ArrayBuffer) => void;
export const latestImu: () => string;

export interface CameraUsbDevice { id: string; authorized: boolean; }
export interface CameraResult { code: number; message: string; }
export interface CameraState extends CameraResult {
  receiving: boolean;
  diagnostics: string;
  previewEpoch: number;
  receivedFrames: number;
  captureFrameId: number;
  previewCopies: number;
  lastFrameAgeMs: number;
}
export interface CameraPreviewFrame {
  epoch: number;
  frameId: number;
  colorWidth: number;
  colorHeight: number;
  colorJpeg: ArrayBuffer;
  depthWidth: number;
  depthHeight: number;
  depthRgba: ArrayBuffer;
}
export interface CameraUsbCommand {
  requestId: number;
  epoch: number;
  operation: number;
  deviceId: string;
  interfaceNumber: number;
  alternate: number;
  requestType: number;
  request: number;
  value: number;
  index: number;
  length: number;
  timeoutMs: number;
  data: ArrayBuffer;
  endpoint: number;
  transfers: number;
  packets: number;
  packetBytes: number;
  isoTimeoutMs: number;
}
export const cameraSetUsbHandler: (handler: (command: CameraUsbCommand) => void) => void;
export const cameraCompleteUsb: (id: number, code: number, message: string, data: ArrayBuffer, devices: CameraUsbDevice[]) => void;
export const cameraPushIso: (epoch: number, buffer: ArrayBuffer, descs: ArrayBuffer | Int32Array) => void;
export const cameraPushEvent: (epoch: number, code: number, message: string) => void;
export const cameraOperation: (operation: string, deviceId: string, color: boolean) => Promise<CameraResult>;
export const cameraStatus: () => CameraState;
// Demand-driven preview snapshot; 1=color, 2=depth, 3=both (default).
// Undefined after stop/reset/disconnect or while waiting for a newer snapshot.
export const cameraPreview: (afterFrameId: number, channels?: number) => CameraPreviewFrame | undefined;
