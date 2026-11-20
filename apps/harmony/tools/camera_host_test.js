// Node >=22.13. Real ArkTS capture controller + real native adapter, mocked OS USB.
// Type stripping checks syntax and behavior, not ArkTS type or SDK compatibility.
// node apps/harmony/tools/camera_host_test.js <absolute entry.node> <repo root>
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { stripTypeScriptTypes } = require('node:module');
const native = require(process.argv[2]);
const root = process.argv[3] || '.';
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(predicate, timeout = 3000) {
  const start = Date.now();
  while (!predicate()) {
    assert(Date.now() - start < timeout, 'condition timed out: ' + JSON.stringify(native.cameraStatus()));
    await pause(10);
  }
}
const device = { name: 'mock/cs30', vendorId: 0x2207, productId: 0x0016, configs: [{ interfaces:
  [{ id: 0, alternateSetting: 0 }, { id: 1, alternateSetting: 0 }, { id: 1, alternateSetting: 1 }] }] };
let granted = true, epoch = 0, opens = 0, closes = 0, canceled = 0, ticks = 0;
let deliverPayload = true, failedRecovery = 0, failConnect = false;
let isoByteLimit = Infinity, submitErrorCode = 14400012, submitCalls = 0, failSubmitAt = 0;
const submitLog = [];
const packetFaults = [], sanitizedFaults = [];
let currentPacketFault = '', corruptEveryCallback = false;
let holdCancellation = false;
const heldCancellations = new Map();
let requestRight = async () => granted;
let slices = [0, 0], offset = 0, fid = 0;
const pending = new Map();
const blobs = [0, 1].map(i => fs.readFileSync(root + '/perception/cs30/calibration_' + i + '.bin'));
const image = Buffer.alloc(640 * 480 * 2);
for (let i = 0; i < image.length; i += 2) image.writeUInt16LE(1000, i);
// Preview samples every other pixel, preserving the sensor's orientation.
[0, 1, 100, 5000, 5001].forEach((mm, x) => image.writeUInt16LE(mm, x * 4));
// Only metadata/framing is tested by this synthetic JPEG.
const jpeg = Buffer.from([255,216,255,192,0,11,8,2,28,3,192,1,1,17,0,255,217]);
const length = Buffer.alloc(4); length.writeUInt32LE(jpeg.length);
const payload = Buffer.concat([image, length, jpeg]);
const core = {};
const descriptorBuffers = new Map();
for (const name of ['cameraCompleteUsb','cameraPushIso','cameraPushEvent','cameraOperation','cameraStatus']) core[name] = native[name];
core.cameraPushIso = (epoch, buffer, descs) => {
  if (!descriptorBuffers.has(epoch)) descriptorBuffers.set(epoch, new Set());
  descriptorBuffers.get(epoch).add(descs);
  const descriptors = new Int32Array(descs);
  if (currentPacketFault) {
    const wholeBatch = currentPacketFault === 'negative_length' || currentPacketFault === 'wrong_count';
    for (let i = 0; i < descriptors.length / 3; i++) {
      assert.equal(descriptors[3*i], 3072, 'bad descriptors must not shift later buffer offsets');
      if (wholeBatch || i === 2) {
        assert.equal(descriptors[3*i+1], 0, 'bad packet bytes must not reach the frame parser');
        assert.notEqual(descriptors[3*i+2], 0, 'bad packets must damage the frame, not become successful empty packets');
      }
    }
    sanitizedFaults.push(currentPacketFault);
    currentPacketFault = '';
  }
  return native.cameraPushIso(epoch, buffer, descs);
};
core.cameraOperation = (operation, ...args) => {
  if (operation === 'connect' && failConnect) {
    failConnect = false; failedRecovery++;
    return Promise.reject(new Error('simulated system bridge rejection'));
  }
  return native.cameraOperation(operation, ...args);
};
core.cameraSetUsbHandler = handler => native.cameraSetUsbHandler(command => {
  if (command.operation === 5) epoch = command.epoch;
  handler(command);
});
const usbManager = {
  UsbTransferFlags: { USB_TRANSFER_SHORT_NOT_OK: 0 },
  UsbEndpointTransferType: { TRANSFER_TYPE_ISOCHRONOUS: 1 },
  UsbTransferStatus: { TRANSFER_COMPLETED: 0, TRANSFER_TIMED_OUT: 2, TRANSFER_CANCELED: 3, TRANSFER_NO_DEVICE: 5 },
  getDevices: () => [device], hasRight: () => granted, requestRight: () => requestRight(),
  connectDevice: () => { opens++; return { generation: opens }; },
  claimInterface: () => 0,
  setInterface: (_pipe, iface) => { if (iface.id === 0) slices = [0,0]; return 0; },
  releaseInterface: () => { assert.equal(pending.size, 0, 'release must wait for callbacks'); return 0; },
  closePipe: () => { assert.equal(pending.size, 0, 'close must wait for callbacks'); closes++; },
  usbControlTransfer: async (_pipe, request) => {
    if (!(request.bmRequestType & 0x80)) return request.wLength;
    const out = request.data;
    if (request.wValue === 0xc100 || request.wValue === 0xc200) {
      const i = request.wValue === 0xc100 ? 0 : 1, blob = blobs[i];
      const start = slices[i], n = Math.min(55, blob.length - start), end = start + n;
      out[0] = blob.length & 255; out[1] = blob.length >> 8;
      out[2] = end & 255; out[3] = end >> 8; out[4] = n;
      out.set(blob.subarray(start, end), 5); slices[i] = end;
    } else if (request.wValue === 0x0100) { out[19] = 0x60; out[20] = 9; }
    return out.length;
  },
  usbSubmitTransfer: params => {
    assert(!pending.has(params), 'buffer cannot be submitted twice');
    assert.equal(params.length, params.isoPacketCount * 3072, 'negotiated packet size must be preserved');
    assert.equal(params.buffer.byteLength, params.length);
    submitCalls++;
    submitLog.push({ packets: params.isoPacketCount, pending: pending.size });
    if (params.length > isoByteLimit || submitCalls === failSubmitAt) {
      const error = new Error('simulated USB submission failure');
      error.code = submitErrorCode;
      throw error;
    }
    const timer = setTimeout(() => {
      pending.delete(params);
      const descs = [];
      for (let i = 0; i < params.isoPacketCount; i++) {
        if (!deliverPayload) {
          descs.push({ length: 3072, actualLength: 0, status: 0 });
          continue;
        }
        const n = Math.min(3070, payload.length - offset), last = offset + n === payload.length;
        params.buffer[i*3072] = 2; params.buffer[i*3072+1] = fid | (last ? 2 : 0);
        params.buffer.set(payload.subarray(offset, offset+n), i*3072+2);
        descs.push({ length: 3072, actualLength: n+2, status: 0 });
        offset += n; if (last) { offset = 0; fid ^= 1; }
      }
      const fault = corruptEveryCallback ? 'negative_actual' : packetFaults.shift();
      if (fault) {
        if (fault === 'negative_actual') descs[2].actualLength = -1;
        else if (fault === 'negative_error_actual') { descs[2].actualLength = -32; descs[2].status = 1; }
        else if (fault === 'negative_length') descs[2].length = -1;
        else if (fault === 'oversized_actual') descs[2].actualLength = 3073;
        else if (fault === 'fractional_actual') descs[2].actualLength = 0.5;
        else if (fault === 'nan_actual') descs[2].actualLength = NaN;
        else if (fault === 'unsigned_actual') descs[2].actualLength = 0xffffffff;
        else if (fault === 'wrong_count') descs.pop();
        currentPacketFault = fault;
      }
      params.callback(undefined, { status: 0, isoPacketDescs: descs });
      assert.equal(currentPacketFault, '', 'corrupt callback must be handled without stopping the queue');
    }, 15);
    pending.set(params, timer);
  },
  usbCancelTransfer: params => {
    const timer = pending.get(params); if (!timer) return;
    clearTimeout(timer);
    if (holdCancellation) {
      pending.set(params, -1);
      heldCancellations.set(params, () => {
        pending.delete(params); canceled++;
        params.callback(undefined, { status: 3, isoPacketDescs: [] });
      });
      return;
    }
    // Deliberately delay completion: closing the pipe before this is a failure.
    pending.set(params, setTimeout(() => {
      pending.delete(params); canceled++;
      params.callback(undefined, { status: 3, isoPacketDescs: [] });
    }, 40));
  }
};
let source = fs.readFileSync(root + '/apps/harmony/entry/src/main/ets/usb/Cs30Usb.ets', 'utf8');
source = source.replace(/^import .*;\r?$/gm, '').replace('export class Cs30Usb', 'class Cs30Usb')
  .replace('export const cs30Usb = new Cs30Usb();', 'globalThis.camera = new Cs30Usb();');
const context = { core, usbManager, setTimeout, clearTimeout, setInterval, clearInterval, console };
vm.runInNewContext(stripTypeScriptTypes(source), context);
const camera = context.camera;
(async () => {
  assert.equal(native.init(), '');
  assert.equal(native.cameraPreview(0), undefined);
  assert.throws(() => native.cameraPreview(-1), /预览/);
  assert.throws(() => native.cameraPushIso(0, new Uint8Array(3072), new Int32Array([3072, -1, 0])),
    /包 0 length=3072 actualLength=-1 status=0/, 'native guard must still reject malformed callers with useful values');
  // Eight packet descriptors occupy 96 bytes, not 96 Int32 elements. Use a
  // nonzero-offset view surrounded by poison values to catch over-reading its
  // own extent even when the backing allocation is larger. Also run this suite
  // against the addon built with tools/ohos_napi_shim to cover Harmony's units.
  const descriptorBacking = new Int32Array(100).fill(-1);
  const descriptorView = descriptorBacking.subarray(3, 27);
  for (let i = 0; i < 8; i++) descriptorView.set([3072, 0, 0], 3*i);
  assert.doesNotThrow(() => native.cameraPushIso(0, new Uint8Array(8*3072), descriptorView));
  assert.doesNotThrow(() => native.cameraPushIso(0, new ArrayBuffer(8*3072), descriptorView.slice().buffer));
  const tick = setInterval(() => ticks++, 10);
  try {
    assert.equal(await camera.startSubmitTransfer(), '');
    await until(() => native.cameraStatus().receiving);
    assert(ticks > 10, 'native startup must leave the JS event loop responsive');
    await until(() => JSON.parse(native.gridJson()).frame_id > 0);
    const progress = native.cameraStatus();
    await until(() => native.cameraStatus().receivedFrames > progress.receivedFrames);
    const unobserved = native.cameraStatus();
    assert.equal(unobserved.previewCopies, 1, 'unconsumed preview must not copy every captured group');
    assert(unobserved.captureFrameId >= progress.captureFrameId && unobserved.lastFrameAgeMs >= 0);
    assert.equal(descriptorBuffers.get(epoch).size, 10, 'ISO descriptors must be reused per slot, not allocated per callback');
    const preview = native.cameraPreview(0);
    assert(preview.frameId > 0);
    assert.equal(preview.epoch, native.cameraStatus().previewEpoch);
    assert.deepEqual([preview.colorWidth, preview.colorHeight], [960, 540]);
    assert.deepEqual(Buffer.from(preview.colorJpeg), jpeg, 'JPEG must arrive unchanged');
    assert.deepEqual([preview.depthWidth, preview.depthHeight], [320, 240]);
    const rgba = new Uint8Array(preview.depthRgba);
    assert.equal(rgba.length, 320 * 240 * 4);
    assert.deepEqual(Array.from(rgba.subarray(0, 20)),
      [0,0,0,255, 0,0,0,255, 255,255,255,255, 32,32,32,255, 0,0,0,255]);
    assert.equal(native.cameraPreview(preview.frameId), undefined, 'do not repeatedly copy the same frame');
    assert.throws(() => native.cameraPreview(0, 4), /预览/);
    const depthOnly = native.cameraPreview(0, 2);
    assert.equal(depthOnly.colorJpeg.byteLength, 0);
    assert.equal(depthOnly.depthRgba.byteLength, 320 * 240 * 4);
    const colorOnly = native.cameraPreview(0, 1);
    assert.deepEqual(Buffer.from(colorOnly.colorJpeg), jpeg);
    assert.equal(colorOnly.depthRgba.byteLength, 0);
    const firstEpoch = epoch;
    assert.equal(submitLog[0].packets, 8, 'tablet requests should start at 24 KiB');
    assert.match(camera.diagnostics, /每请求 24576B/);
    await camera.stop();
    assert(canceled > 0 && pending.size === 0 && closes === opens);
    assert.equal(native.cameraStatus().receiving, false);
    assert.equal(native.cameraPreview(0), undefined, 'stopping must invalidate the preview');
    assert.equal(JSON.parse(native.gridJson()).status, 'no_frame');
    assert.equal(await camera.startSubmitTransfer(), '');
    await until(() => native.cameraStatus().receiving);
    assert(native.cameraStatus().previewEpoch > preview.epoch);
    assert(native.cameraPreview(0).frameId > preview.frameId);
    assert(epoch > firstEpoch);
    native.cameraPushEvent(firstEpoch, 8, 'stale device removal');
    assert.equal(native.cameraStatus().receiving, true);
    native.cameraPushEvent(epoch, 8, 'current device removal');
    await until(() => native.cameraStatus().code === 8);
    assert.equal(native.cameraStatus().code, 8);
    assert.equal(native.cameraPreview(0), undefined, 'unplugging must invalidate the preview');
    assert.match(native.cameraStatus().diagnostics, /USB批次 [1-9][0-9]*/);
    failConnect = true;
    const before = opens;
    await until(() => opens > before && native.cameraStatus().receiving, 7000);
    assert.equal(failedRecovery, 1, 'a rejected recovery promise must not break future recovery');
    assert.equal(await camera.restart(), '');
    await until(() => native.cameraStatus().receiving);
    await camera.stop();
    granted = false;
    const oldOpens = opens;
    assert((await camera.startSubmitTransfer()).length > 0);
    await pause(1200);
    assert.equal(opens, oldOpens, 'denied authorization must not create a retry loop');

    // Cancel while the system authorization dialog is still outstanding.
    let allow;
    requestRight = () => new Promise(resolve => { allow = resolve; });
    const connecting = camera.startSubmitTransfer();
    await until(() => allow !== undefined);
    const stopping = camera.stop();
    granted = true; allow(true);
    await Promise.all([connecting, stopping]);
    assert.equal(opens, oldOpens, 'canceling during authorization must not open the device later');

    // Reject 24 KiB, then reject a partially submitted 12 KiB queue. The 6 KiB
    // replacement must wait for both delayed cancellation callbacks.
    const fallbackStart = submitLog.length, canceledBefore = canceled;
    isoByteLimit = 4 * 3072; failSubmitAt = submitCalls + 4;
    assert.equal(await camera.startSubmitTransfer(), '');
    await until(() => native.cameraStatus().receiving);
    const fallbackLog = submitLog.slice(fallbackStart);
    assert.deepEqual(fallbackLog.slice(0, 5), [
      { packets: 8, pending: 0 }, { packets: 4, pending: 0 },
      { packets: 4, pending: 1 }, { packets: 4, pending: 2 },
      { packets: 2, pending: 0 }
    ]);
    assert.equal(canceled - canceledBefore, 2, 'partial queue must drain before fallback');
    assert.match(camera.diagnostics, /尝试包数 8→4→2/);
    assert.match(native.cameraStatus().diagnostics, /深度标定 .*640x480.*；彩色 960×540/);
    await until(() => JSON.parse(native.gridJson()).frame_id > 0);
    assert.equal(await camera.restart(), '');
    await until(() => native.cameraStatus().receiving);
    assert.match(camera.diagnostics, /每请求 12288B/);
    await camera.stop();
    assert.equal(pending.size, 0);

    // Exhaust all four bounded sizes and retain the original system error.
    isoByteLimit = 0;
    const exhaustedStart = submitLog.length;
    assert.match(await camera.startSubmitTransfer(), /14400012.*simulated USB submission failure/);
    await camera.stop();
    assert.deepEqual(submitLog.slice(exhaustedStart).map(s => s.packets), [8, 4, 2, 1]);
    assert.match(camera.diagnostics, /每请求 3072B.*尝试包数 8→4→2→1/);
    assert.equal(pending.size, 0);
    assert.equal(opens, closes);

    // Other errors must not trigger the memory workaround.
    submitErrorCode = 14400008;
    const otherErrorStart = submitLog.length;
    assert.match(await camera.startSubmitTransfer(), /14400008/);
    await camera.stop();
    assert.deepEqual(submitLog.slice(otherErrorStart).map(s => s.packets), [8]);
    assert.equal(pending.size, 0);

    // A successful batch may still contain failed or malformed packet metadata.
    // Drop its damaged frame, preserve stride, and receive a later valid frame.
    isoByteLimit = Infinity; submitErrorCode = 14400012;
    assert.equal(await camera.startSubmitTransfer(), '');
    await until(() => native.cameraStatus().receiving);
    const faults = ['negative_actual', 'negative_error_actual', 'negative_length', 'oversized_actual',
      'fractional_actual', 'nan_actual', 'unsigned_actual', 'wrong_count'];
    packetFaults.push(...faults);
    await until(() => sanitizedFaults.length === faults.length);
    assert.deepEqual(sanitizedFaults, faults);
    const afterFaults = JSON.parse(native.gridJson()).frame_id;
    await until(() => JSON.parse(native.gridJson()).frame_id > afterFaults);
    await until(() => /USB坏包 [1-9]/.test(camera.diagnostics));
    assert.match(camera.diagnostics, /首个异常：包 2 length=3072 actualLength=-1 status=0/);
    await until(() => /包错误 [1-9]/.test(native.cameraStatus().diagnostics));
    assert.equal(camera.callbackErrors, 0, 'packet errors must not become fatal callback exceptions');
    await camera.stop();

    // Runtime stall after valid frames: callbacks can still arrive with no
    // image data. Capture age must advance and the existing five-second
    // monitor must report the interruption rather than keep a false healthy UI.
    assert.equal(await camera.startSubmitTransfer(), '');
    await until(() => native.cameraStatus().receiving);
    deliverPayload = false;
    // The native receiver may still own a previously completed USB batch.
    await pause(100);
    const beforeStall = native.cameraStatus(), callbacksBeforeStall = camera.callbacks;
    await until(() => native.cameraStatus().lastFrameAgeMs >= 700);
    assert.equal(native.cameraStatus().captureFrameId, beforeStall.captureFrameId);
    assert(camera.callbacks > callbacksBeforeStall);
    await until(() => native.cameraStatus().code === 9, 6000);
    assert.match(native.cameraStatus().message, /5 秒没有完整的新帧/);
    assert.equal(native.cameraPreview(0), undefined);
    await camera.stop(); deliverPayload = true;

    // Missing cancellation callbacks must return an error without freeing or
    // reusing in-flight buffers, then allow a later completion and reconnect.
    assert.equal(await camera.startSubmitTransfer(), '');
    await until(() => native.cameraStatus().receiving);
    camera.busy = true; holdCancellation = true;
    const cancelStarted = Date.now(), oldCloses = closes, ticksBeforeCancel = ticks;
    const stopped = await native.cameraOperation('stop', '', true);
    assert.notEqual(stopped.code, 0);
    assert.match(stopped.message, /取消等待超时/);
    assert(Date.now() - cancelStarted < 5000, 'stop must finish before the native bridge timeout');
    assert(ticks > ticksBeforeCancel + 50, 'a missing cancel callback must leave the event loop responsive');
    assert(pending.size > 0 && closes === oldCloses, 'do not close or release system-owned buffers');
    holdCancellation = false;
    for (const complete of heldCancellations.values()) complete();
    heldCancellations.clear(); camera.busy = false;
    assert.equal(await camera.restart(), '');
    await until(() => native.cameraStatus().receiving);
    await camera.stop();

    // A later resubmission failure must also preserve its system error details.
    isoByteLimit = Infinity; submitErrorCode = 14400012;
    assert.equal(await camera.startSubmitTransfer(), '');
    await until(() => native.cameraStatus().receiving);
    failSubmitAt = submitCalls + 1;
    await until(() => native.cameraStatus().code === 9);
    assert.match(native.cameraStatus().message, /14400012.*simulated USB submission failure/);
    await camera.stop();

    // No complete first frame: surface current session USB counters with the error.
    deliverPayload = false; corruptEveryCallback = true;
    assert.equal(await camera.startSubmitTransfer(), '');
    await until(() => native.cameraStatus().code === 9, 6500);
    assert.match(native.cameraStatus().diagnostics, /USB批次 [1-9][0-9]*/);
    assert.match(native.cameraStatus().message, /5 秒没有完整的新帧/);
    await camera.stop();
    await camera.shutdown();
    assert.equal(pending.size, 0);
    assert.equal(opens, closes);
    console.log('CAMERA HOST TEST PASSED: dual capture, drain, restart, recovery rejection, stale epoch, permission cancellation, bounded ISO fallback, partial queue cleanup, corrupt packet recovery, system error preservation, first-frame diagnostics');
  } finally { clearInterval(tick); await camera.shutdown(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
