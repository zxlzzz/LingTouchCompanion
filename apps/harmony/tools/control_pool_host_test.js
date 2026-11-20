// Run with UV_THREADPOOL_SIZE=1. A stalled shared worker must not delay camera
// control. The crypto job occupies that pool without relying on wall-clock FPS.
const assert = require('node:assert/strict');
const { pbkdf2 } = require('node:crypto');
const core = require(process.argv[2]);
(async () => {
  assert.equal(core.init(), '');
  let sharedDone = false;
  const sharedWork = new Promise((resolve, reject) => {
    pbkdf2('control-test', 'salt', 2000000, 16, 'sha256', error => {
      sharedDone = true;
      if (error) reject(error); else resolve();
    });
  });
  const result = await core.cameraOperation('stop', '', true);
  assert.equal(result.code, 0);
  assert.equal(sharedDone, false, 'camera control must not wait for the shared worker pool');
  await sharedWork;
  console.log('CONTROL POOL TEST PASSED: camera operation bypassed an occupied shared worker');
})().catch(error => { console.error(error); process.exitCode = 1; });
