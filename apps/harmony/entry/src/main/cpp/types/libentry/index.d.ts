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
