// 在电脑上用 Node 检查 apps/harmony/entry/src/main/cpp/napi_init.cpp（Node-API 与鸿蒙 NAPI 接口相同）。
// 不是鸿蒙真机测试：只验证胶水层的参数、返回值和"启动响应 → 标定 → 按批收包 → 栅格 → 编码"。
//
// 先编译核心（cmake -S core -B build/core && cmake --build build/core），再在仓库根目录：
//   mkdir -p build/napi_shim/napi && printf '#pragma once\n#include <node_api.h>\n' > build/napi_shim/napi/native_api.h
//   g++ -std=c++17 -shared -fPIC -Ibuild/napi_shim -I<node>/include/node -Icore/include -Iperception/native/include \
//     apps/harmony/entry/src/main/cpp/{napi_init,camera_napi,cs30_sensor_adapter,harmony_usb_transport}.cpp -o build/entry.node \
//     -Wl,--whole-archive build/core/liblingtouch_engine.a -Wl,--no-whole-archive \
//     build/core/perception/liblingtouch_perception.a build/core/liblingtouch_base.a -lpthread
//   node apps/harmony/tools/napi_host_test.js build/entry.node .
const core = require(process.argv[2]);
const fs = require('fs');
const root = process.argv[3];
const assert = (c, m) => { if (!c) { console.log('FAIL', m); process.exitCode = 1; } };
assert(core.init() === '', 'init');
const info = core.protocolInfo();
console.log('protocolInfo', info);
const n = core.startupStepCount();
assert(n === 44, 'step count');
const s38 = core.startupStep(38);
assert(s38.kind === 'control' && !s38.isIn && new Uint8Array(s38.data)[19] === 0x60, 'commit step');
assert(core.startupStep(40).kind === 'queue_iso' && core.startupStep(42).settleMs === 270, 'iso/settle');
// 标定分片
function slices(blob) { const out = []; for (let st = 0; st < blob.length; st += 55) { const k = Math.min(55, blob.length - st), end = st + k; const r = new Uint8Array(60); r[0] = blob.length & 255; r[1] = blob.length >> 8; r[2] = end & 255; r[3] = end >> 8; r[4] = k; r.set(blob.subarray(st, end), 5); out.push(r); } return out; }
const s0 = slices(fs.readFileSync(root + '/perception/cs30/calibration_0.bin'));
const s1 = slices(fs.readFileSync(root + '/perception/cs30/calibration_1.bin'));
let k0 = 0, k1 = 0;
for (let i = 0; i < n; i++) { const st = core.startupStep(i); if (!st.isIn) continue;
  if (st.value === 0xc100) assert(core.onStartupResponse(i, s0[k0++].buffer) === '', 'resp c100');
  if (st.value === 0xc200) assert(core.onStartupResponse(i, s1[k1++]) === '', 'resp c200'); }
assert(core.finishStartup() === '', 'finishStartup');
console.log(core.deviceSummary());
// 参考帧切成等时传输
const frame = fs.readFileSync(root + '/perception/cs30/reference_000.bin');
let off = 0, transfers = 0;
while (off < frame.length) {
  const buf = new Uint8Array(32 * 3072); const descs = new Int32Array(32 * 3);
  for (let s = 0; s < 32; s++) { descs[3*s] = 3072; if (off >= frame.length) continue;
    const k = Math.min(3070, frame.length - off); buf[s*3072] = 2; buf[s*3072+1] = (off + k === frame.length) ? 2 : 0;
    buf.set(frame.subarray(off, off + k), s*3072 + 2); descs[3*s+1] = k + 2; off += k; }
  core.pushIsoTransfer(buf.buffer, descs); transfers++;
}
const t0 = Date.now(); let g;
while (Date.now() - t0 < 5000) { g = JSON.parse(core.gridJson()); if (g.frame_id === 1) break; }
console.log('transfers', transfers, 'grid', g.status, g.failure, g.cells);
assert(g.frame_id === 1 && g.status === 'ground_fit_failed' && g.cells === '2'.repeat(54), 'grid');
const stats = JSON.parse(core.statsJson()); console.log('stats', stats);
assert(stats.frames === 1 && stats.incomplete === 0, 'stats');
assert(core.encodeLatest(0) === undefined && core.lastError().length > 0, 'policy required');
const bytes = new Uint8Array(core.encodeLatest(2)); console.log('raised frame', Buffer.from(bytes).toString('hex'));
assert(bytes.length === 15, 'frame len');
console.log('openFd without libusb:', core.openFd(-1));
console.log(process.exitCode ? 'NAPI TEST FAILED' : 'NAPI TEST PASSED');
setTimeout(() => process.exit(process.exitCode || 0), 100);
