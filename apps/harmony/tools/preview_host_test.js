// Run the production ArkTS controller with independently delayed SDK operations.
// Virtual 200 ms ticks exercise long-run resource bounds, not real-device timing.
// node apps/harmony/tools/preview_host_test.js <repo root>
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { stripTypeScriptTypes } = require('node:module');
const root = process.argv[2] || '.';
let source = fs.readFileSync(root + '/apps/harmony/entry/src/main/ets/camera/CameraPreview.ets', 'utf8');
source = source.replace(/^import .*;\r?$/gm, '').replace(/^export /gm, '') +
  '\nglobalThis.CameraPreview = CameraPreview;';
source = stripTypeScriptTypes(source);
const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; }
function harness() {
  const h = { now: 1000, id: 1, state: { receiving: true, previewEpoch: 1 },
    maps: [], sources: [], updates: [], requests: [], colorJobs: 0, depthJobs: 0,
    colorHook: null, depthHook: null, sourceReleaseHook: null, mapReleaseHook: null,
    rejectColor: false, rejectDepth: false, live: 0, maxLive: 0 };
  function pixelMap(lane, id) {
    h.live++; h.maxLive = Math.max(h.maxLive, h.live);
    const map = { lane, id, releases: 0, released: false, release: async () => {
      map.releases++;
      if (h.mapReleaseHook) await h.mapReleaseHook(map);
      map.released = true; h.live--;
    } };
    h.maps.push(map); return map;
  }
  const core = {
    cameraStatus: () => ({ ...h.state }),
    cameraPreview: (after, channels = 3) => {
      h.requests.push(channels);
      return h.id > after ? { epoch: h.state.previewEpoch, frameId: h.id,
        colorJpeg: new ArrayBuffer(channels & 1 ? 4 : 0),
        depthRgba: new ArrayBuffer(channels & 2 ? 16 : 0), depthWidth: 2, depthHeight: 2 } : undefined;
    }
  };
  const image = {
    PixelMapFormat: { RGBA_8888: 3 }, AlphaType: { OPAQUE: 1 },
    createImageSource: () => {
      const id = h.id;
      const s = { releases: 0, createPixelMap: async () => {
        h.colorJobs++;
        if (h.colorHook) await h.colorHook();
        if (h.rejectColor) throw new Error('bad JPEG');
        return pixelMap('color', id);
      }, release: async () => { s.releases++; if (h.sourceReleaseHook) await h.sourceReleaseHook(); } };
      h.sources.push(s); return s;
    },
    createPixelMap: async () => {
      const id = h.id; h.depthJobs++;
      if (h.depthHook) await h.depthHook();
      if (h.rejectDepth) throw new Error('bad RGBA');
      return pixelMap('depth', id);
    }
  };
  const context = { core, image, Date: { now: () => h.now } };
  vm.runInNewContext(source, context);
  h.preview = new context.CameraPreview((images, message) => h.updates.push({ images, message }));
  h.last = () => h.updates.at(-1);
  h.render = () => { h.preview.colorDisplayed(); h.preview.depthDisplayed(); };
  h.tick = async (render = true) => {
    h.now += 200; h.id++;
    await h.preview.update();
    if (render) h.render();
    await flush();
  };
  h.finish = async () => {
    h.preview.stop(); await flush();
    assert(h.maps.every(m => m.releases === 1 && m.released), 'every PixelMap must be released exactly once');
    assert(h.sources.every(s => s.releases === 1), 'every ImageSource must be released once');
    assert.equal(h.live, 0);
  };
  return h;
}
(async () => {
  {
    const h = harness();
    await h.preview.update(); assert.equal(h.colorJobs, 0);
    h.preview.start(); await h.preview.update(); h.render(); await flush();
    const first = h.last().images;
    await h.preview.update(); assert.equal(h.colorJobs, 1, 'deduplicate each capture group');
    await h.tick(false);
    assert.equal(first.color.releases, 0, 'keep previous images until the renderer consumes replacements');
    h.render(); await flush(); assert.equal(first.color.releases, 1);
    await h.finish();
  }
  // A never-resolving color decoder used to hold the shared busy flag and
  // prevent depth creation. Depth must continue with no additional color jobs.
  for (const blocked of ['color', 'depth']) {
    const h = harness(), gate = deferred(); h.preview.start();
    h[blocked + 'Hook'] = () => gate.promise;
    const work = h.preview.update(); await flush(); h.render(); await flush();
    const other = blocked === 'color' ? 'depth' : 'color';
    assert.equal(h.last().images[other].id, 1);
    for (let i = 0; i < 40; i++) {
      await h.tick();
      assert.equal(h.last().images[other].id, h.id, 'one stalled lane must not stop the other');
    }
    assert.equal(h[blocked + 'Jobs'], 2, 'one quarantined job and one replacement, never a third stuck job');
    assert(h.updates.some(u => /超时/.test(u.message)));
    assert.equal(h.requests.at(-1), blocked === 'color' ? 2 : 1, 'do not copy the blocked lane data');
    h[blocked + 'Hook'] = null; gate.resolve(); await work; await flush();
    assert(h.maps.filter(m => m.lane === blocked).every(m => m.released), 'discard late timed-out results');
    await h.tick(); assert.equal(h.last().images[blocked].id, h.id, 'resume after the real SDK job finishes');
    await h.finish();
  }
  {
    const h = harness(), gate = deferred(); h.preview.start();
    h.sourceReleaseHook = () => gate.promise;
    const work = h.preview.update(); await flush(); h.render(); await flush();
    assert(h.last().images.color, 'present a decoded map before waiting for source cleanup');
    for (let i = 0; i < 40; i++) await h.tick();
    assert.equal(h.colorJobs, 2); assert.equal(h.last().images.depth.id, h.id);
    assert(h.updates.some(u => /隔离旧任务/.test(u.message)));
    h.sourceReleaseHook = null; gate.resolve(); await work; await flush();
    await h.tick(); await h.finish();
  }
  {
    const h = harness(), gate = deferred(); h.preview.start();
    h.colorHook = h.depthHook = () => gate.promise;
    const old = h.preview.update(); await flush();
    h.state = { receiving: false, previewEpoch: 2 }; await h.preview.update();
    assert.equal(h.last().images, undefined);
    h.state = { receiving: true, previewEpoch: 3 }; await h.preview.update();
    gate.resolve(); await old; await flush();
    assert.equal(h.last().images, undefined, 'reconnect cannot revive old decoded maps');
    h.colorHook = h.depthHook = null; await h.tick();
    h.colorHook = () => (h.hideGate = deferred()).promise;
    h.id++; const hideWork = h.preview.update(); await flush();
    h.preview.stop(); h.hideGate.resolve(); await hideWork; await flush();
    assert.equal(h.last().images, undefined, 'late decode cannot revive a hidden page');
    h.colorHook = null; h.preview.start(); await h.tick(); await h.finish();
  }
  {
    const h = harness(); h.preview.start(); h.rejectColor = true;
    await h.tick(); assert(h.last().images.depth); assert.equal(h.last().images.color, undefined);
    assert.match(h.last().message, /彩色预览解码失败/);
    h.rejectColor = false; h.rejectDepth = true; await h.tick();
    assert(h.last().images.color); assert.match(h.last().message, /深度预览生成失败/);
    await h.finish();
  }
  // 30 virtual minutes at five updates per second with renderer completions.
  {
    const h = harness(); h.preview.start();
    for (let i = 0; i < 9000; i++) await h.tick();
    assert.equal(h.colorJobs, 9000); assert.equal(h.depthJobs, 9000);
    assert(h.maxLive <= 4, 'long runs must not retain a growing list of PixelMaps');
    await h.finish();
  }
  // Lost Image.onComplete callbacks must stay bounded and periodically recover.
  {
    const h = harness(); h.preview.start();
    for (let i = 0; i < 400; i++) await h.tick(false);
    assert(h.maxLive <= 4); assert(h.colorJobs > 10, 'missing renderer completion must not freeze forever');
    assert.match(h.preview.diagnostics(), /显示重置 [1-9]/);
    await h.finish();
  }
  // Even a stuck PixelMap.release must not cause unlimited native allocation.
  {
    const h = harness(), gate = deferred(); h.preview.start();
    h.mapReleaseHook = m => m.lane === 'color' ? gate.promise : Promise.resolve();
    for (let i = 0; i < 100; i++) await h.tick();
    assert(h.colorJobs <= 6); assert.equal(h.last().images.depth.id, h.id);
    assert(h.maxLive <= 8); assert.match(h.last().message, /释放较慢/);
    h.mapReleaseHook = null; gate.resolve(); await flush();
    await h.tick(); await h.finish();
  }
  // One permanently stuck decoder must not freeze that channel forever.
  {
    const h = harness(), gate = deferred(); h.preview.start();
    h.colorHook = () => gate.promise;
    await h.tick(); h.colorHook = null;
    for (let i = 0; i < 100; i++) await h.tick();
    assert.equal(h.last().images.color.id, h.id);
    assert.equal(h.last().images.depth.id, h.id);
    assert.match(h.preview.diagnostics(), /预览重建 1\/0/);
    h.state.previewEpoch++; await h.tick();
    gate.resolve(); await flush(); await h.tick(); await h.finish();
  }
  console.log('PREVIEW HOST TEST PASSED: bounded replacement, independent lanes, SDK stalls, reconnect/hide isolation, render watchdog, 9000-frame virtual run');
})().catch(error => { console.error(error); process.exitCode = 1; });
