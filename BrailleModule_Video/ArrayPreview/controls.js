
"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const view = $("view"), canvas = $("canvas"), message = $("message");
  const defaults = { peak_mm: .7, hold_mm: .45, rise_ms: 100 / 3, peak_pause_ms: 200 / 3, settle_ms: 50, retract_ms: 50, curve: "linear", pose_sampling: "nearest" };
  let motion = defaults, viewer, ready = false, request = 0;
  let records = [], current = -1, playing = false, manual = true, clockStart = 0, sequenceStart = 0, resumeTime = null, speed = 1;
  const states = Array.from({ length: 90 }, () => ({ target: false, height: 0, phase: "idle", startHeight: 0, started: 0 }));
  const buttons = new Array(90), cells = [], byteLabels = [];
  const phaseNames = { idle: "未凸起", rise: "凸起中", peak: "高位凸起", settle: "回落中", hold: "低位维持", retract: "收回中" };
  const clamp = value => Math.max(0, Math.min(1, value));
  const indexAt = (r, c) => (Math.floor(r / 2) * 3 + Math.floor(c / 3)) * 6 + (r % 2) * 3 + 2 - c % 3;
  const emptyGrid = () => Array.from({ length: 10 }, () => Array(9).fill(0));
  const copyGrid = grid => grid.map(row => [...row]);
  const currentGrid = () => Array.from({ length: 10 }, (_, r) => Array.from({ length: 9 }, (_, c) => Number(states[indexAt(r, c)].target)));
  const gridToBytes = grid => Array.from({ length: 15 }, (_, m) => {
    const r = Math.floor(m / 3) * 2, c = m % 3 * 3;
    let value = 0;
    for (let dr = 0; dr < 2; dr++) for (let dc = 0; dc < 3; dc++) value |= Number(Boolean(grid[r + dr][c + dc])) << (dr * 3 + 2 - dc);
    return value;
  });
  const bytesToGrid = bytes => {
    if (!Array.isArray(bytes) && !(bytes instanceof Uint8Array)) throw new Error("需要 15 个模组字节。");
    if (bytes.length !== 15 || !Array.from(bytes).every(x => Number.isInteger(x) && x >= 0 && x <= 63)) throw new Error("每个模组字节应为 0–63，共 15 个。");
    const grid = emptyGrid();
    for (let r = 0; r < 10; r++) for (let c = 0; c < 9; c++) {
      const index = indexAt(r, c); grid[r][c] = bytes[Math.floor(index / 6)] >> (index % 6) & 1;
    }
    return grid;
  };

  for (let r = 0; r < 10; r++) for (let c = 0; c < 9; c++) {
    const index = indexAt(r, c), button = document.createElement("button");
    button.type = "button"; button.className = "cell";
    Object.assign(button.dataset, { row: String(r), col: String(c), module: String(Math.floor(index / 6) + 1), dot: String(index % 6 + 1), target: "0", phase: "idle", height: "0.0000" });
    button.setAttribute("aria-pressed", "false"); button.setAttribute("aria-label", `第 ${r + 1} 行第 ${c + 1} 列，模组 ${Math.floor(index / 6) + 1} 点 ${index % 6 + 1}，未凸起`);
    button.title = `M${Math.floor(index / 6) + 1} · 点 ${index % 6 + 1}`;
    button.addEventListener("click", () => { enterManual(); setTarget(index, !states[index].target); });
    $("grid").appendChild(button); buttons[index] = button; cells.push(button);
  }
  for (let m = 0; m < 15; m++) {
    const span = document.createElement("span"); span.className = "byte"; span.textContent = `M${m + 1}: 00`;
    span.dataset.module = String(m + 1); $("bytes").appendChild(span); byteLabels.push(span);
  }

  function updateMotion(state, now) {
    if (state.phase === "idle" || state.phase === "hold") return;
    const elapsed = Math.max(0, now - state.started);
    if (!state.target) {
      state.height = state.startHeight * (1 - clamp(elapsed / motion.retract_ms));
      if (elapsed >= motion.retract_ms) { state.height = 0; state.phase = "idle"; }
      return;
    }
    const pauseEnd = motion.rise_ms + motion.peak_pause_ms, end = pauseEnd + motion.settle_ms;
    if (elapsed < motion.rise_ms) { state.phase = "rise"; state.height = state.startHeight + (motion.peak_mm - state.startHeight) * clamp(elapsed / motion.rise_ms); }
    else if (elapsed < pauseEnd) { state.phase = "peak"; state.height = motion.peak_mm; }
    else if (elapsed < end) { state.phase = "settle"; state.height = motion.peak_mm + (motion.hold_mm - motion.peak_mm) * clamp((elapsed - pauseEnd) / motion.settle_ms); }
    else { state.phase = "hold"; state.height = motion.hold_mm; }
  }

  function setTarget(index, target, now = performance.now(), refresh = true) {
    const state = states[index];
    if (state.target === Boolean(target)) return;
    updateMotion(state, now); state.startHeight = state.height; state.target = Boolean(target); state.started = now;
    state.phase = state.target ? "rise" : state.height > 0 ? "retract" : "idle";
    if (refresh) { updateControls(); requestFrame(); }
  }

  function applyGrid(grid, now = performance.now()) {
    for (let r = 0; r < 10; r++) for (let c = 0; c < 9; c++) setTarget(indexAt(r, c), grid[r][c], now, false);
    updateControls(); requestFrame();
  }

  function updateControls() {
    let count = 0;
    states.forEach((state, index) => {
      const button = buttons[index], name = phaseNames[state.phase];
      button.dataset.target = state.target ? "1" : "0"; button.dataset.phase = state.phase; button.dataset.height = state.height.toFixed(4);
      button.setAttribute("aria-pressed", String(state.target));
      const label = `第 ${Number(button.dataset.row) + 1} 行第 ${Number(button.dataset.col) + 1} 列，模组 ${button.dataset.module} 点 ${button.dataset.dot}，${name}`;
      if (button.getAttribute("aria-label") !== label) button.setAttribute("aria-label", label);
      if (state.target) count++;
    });
    const summary = `${count} / 90 个触点凸起`;
    if ($("summary").textContent !== summary) $("summary").textContent = summary;
    gridToBytes(currentGrid()).forEach((byte, m) => {
      const text = `M${m + 1}: ${byte.toString(16).toUpperCase().padStart(2, "0")}`;
      if (byteLabels[m].textContent !== text) byteLabels[m].textContent = text;
      byteLabels[m].classList.toggle("active", byte !== 0); byteLabels[m].dataset.byte = String(byte);
    });
  }

  function enterManual() { pause(); manual = true; updateTimeline(); }
  function feedback(text, error = false) { $("feedback").textContent = text; $("feedback").classList.toggle("error", error); }
  function validateGrid(value, label = "frame") {
    if (!Array.isArray(value) || value.length !== 10 || !value.every(row => Array.isArray(row) && row.length === 9)) throw new Error(`${label} 应为 10 行，每行 9 个点。`);
    return value.map((row, r) => row.map((value, c) => {
      if (typeof value !== "boolean" && !(typeof value === "number" && Number.isFinite(value))) throw new Error(`${label} 的第 ${r + 1} 行第 ${c + 1} 列应为 0 或 1。`);
      return Number(Boolean(value));
    }));
  }

  function parseRecords(text) {
    if (typeof text !== "string" || !text.trim()) throw new Error("请先粘贴 JSON 或选择文件。");
    let value;
    try { value = JSON.parse(text); }
    catch (_) {
      try { value = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean).map(line => JSON.parse(line)); }
      catch (_) { throw new Error("JSON 格式不完整，请检查括号、逗号和引号。"); }
    }
    const matrix = Array.isArray(value) && value.length === 10 && value.every(row => Array.isArray(row) && row.length === 9 && !row.some(cell => Array.isArray(cell) || typeof cell === "object" && cell !== null));
    if (matrix) value = [{ seq: 0, ts: 0, mode: "LOCAL_ZOOM", frame: value }];
    else if (value && typeof value === "object" && !Array.isArray(value) && Array.isArray(value.frames)) value = value.frames;
    else if (!Array.isArray(value)) value = [value];
    if (!value.length) throw new Error("帧序列为空。");
    if (value.length > 100000) throw new Error("帧数超过 100000，请拆分后载入。");
    let previous = -Infinity;
    return value.map((item, i) => {
      if (!item || typeof item !== "object" || Array.isArray(item)) throw new Error(`第 ${i + 1} 帧应为包含 frame 的对象。`);
      const grid = validateGrid(item.frame, `第 ${i + 1} 帧`), ts = item.ts ?? i * 500, seq = item.seq ?? i;
      if (typeof ts !== "number" || !Number.isFinite(ts) || ts < 0) throw new Error(`第 ${i + 1} 帧的 ts 应为非负毫秒数。`);
      if (ts < previous) throw new Error(`第 ${i + 1} 帧的 ts 小于前一帧，请按时间排列。`);
      if (typeof seq !== "number" || !Number.isFinite(seq)) throw new Error(`第 ${i + 1} 帧的 seq 应为数字。`);
      if (item.mode != null && typeof item.mode !== "string") throw new Error(`第 ${i + 1} 帧的 mode 应为文字。`);
      previous = ts;
      return { ...item, seq, ts, mode: item.mode ?? "LOCAL_ZOOM", frame: grid };
    });
  }

  function loadRecords(text, source) {
    try {
      const nextRecords = parseRecords(text);
      pause(); records = nextRecords; current = 0; manual = false;
      $("sourceLabel").textContent = source; $("timeline").max = String(records.length - 1);
      applyRecord(0); feedback(`已载入 ${records.length} 帧 · ${(Math.max(0, records.at(-1).ts - records[0].ts) / 1000).toFixed(2)} 秒`);
      return true;
    } catch (error) { feedback(error.message, true); return false; }
  }

  function applyRecord(index, now = performance.now()) {
    if (index < 0 || index >= records.length) return;
    current = index; manual = false; resumeTime = null; applyGrid(records[index].frame, now); updateTimeline();
  }

  function updateTimeline() {
    $("play").textContent = playing ? "暂停" : "播放";
    $("play").disabled = records.length < 2;
    $("previous").disabled = !records.length || current <= 0;
    $("next").disabled = !records.length || current >= records.length - 1;
    $("rewind").disabled = !records.length;
    $("timeline").disabled = records.length < 2;
    $("timeline").value = String(Math.max(current, 0));
    $("frameInfo").textContent = records.length ? `${manual ? "手动 · " : ""}第 ${current + 1} / ${records.length} 帧` : "手动控制";
    $("timeInfo").textContent = records.length ? `${records[current]?.ts ?? 0} ms` : "0 ms";
  }

  function play() {
    if (records.length < 2) return;
    if (playing) { pause(); return; }
    if (current < 0 || current >= records.length - 1) applyRecord(0);
    else if (manual) applyRecord(current);
    playing = true; clockStart = performance.now(); sequenceStart = resumeTime ?? records[current].ts; resumeTime = null; manual = false;
    updateTimeline(); requestFrame();
  }

  function pause() {
    if (playing) { resumeTime = sequenceStart + (performance.now() - clockStart) * speed; playing = false; }
    updateTimeline();
  }

  function updatePlayback(now) {
    if (!playing) return;
    const time = sequenceStart + (now - clockStart) * speed;
    while (current < records.length - 1 && records[current + 1].ts <= time) {
      const scheduled = now - (time - records[current + 1].ts) / speed;
      applyRecord(current + 1, scheduled);
    }
    if (current >= records.length - 1) { playing = false; updateTimeline(); }
  }

  function demoRecords() {
    const patterns = [emptyGrid(), Array.from({ length: 10 }, (_, r) => Array.from({ length: 9 }, (_, c) => Number((r + c) % 2 === 0))), Array.from({ length: 10 }, (_, r) => Array.from({ length: 9 }, (_, c) => Number(c === 4 || r === 4 || r === 5))), Array.from({ length: 10 }, () => Array(9).fill(1)), emptyGrid()];
    return patterns.map((frame, seq) => ({ seq, ts: seq * 1000, mode: "LOCAL_ZOOM", frame }));
  }

  function appendFrame() {
    const interval = Number($("interval").value);
    if (!Number.isFinite(interval) || interval < 1 || interval > 60000) { feedback("帧间隔应为 1–60000 ms。", true); return; }
    const grid = currentGrid(); pause();
    const seq = records.length, ts = records.length ? records.at(-1).ts + interval : 0;
    records.push({ seq, ts, mode: "LOCAL_ZOOM", frame: copyGrid(grid) }); current = records.length - 1; manual = false;
    $("timeline").max = String(current); $("sourceLabel").textContent = "编辑序列"; updateTimeline();
    feedback(`已添加第 ${records.length} 帧 · ${ts} ms`);
  }

  function saveJSON() {
    const output = records.length ? records.map(record => ({ ...record, frame: copyGrid(record.frame) })) : [{ seq: 0, ts: 0, mode: "LOCAL_ZOOM", frame: currentGrid() }];
    const blob = new Blob([JSON.stringify(output, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob), a = document.createElement("a");
    a.href = url; a.download = `braille_array_${new Date().toISOString().replace(/[:.]/g, "-")}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    feedback(`已导出 ${output.length} 帧。`);
  }

  function requestFrame() { if (!request) request = requestAnimationFrame(render); }
  function render(now) {
    request = 0; updatePlayback(now);
    let moving = playing;
    states.forEach(state => { updateMotion(state, now); if (state.phase !== "idle" && state.phase !== "hold") moving = true; });
    updateControls();
    if (ready && viewer.draw(states.map(state => state.height))) moving = true;
    if (moving) requestFrame();
  }
  function resize() { if (viewer) viewer.resize(); requestFrame(); }

  async function start() {
    try {
      const embedded = JSON.parse($("sceneAssets").textContent);
      motion = { ...defaults, ...embedded.motion };
      if (!(Number.isFinite(motion.peak_mm) && Number.isFinite(motion.hold_mm) && motion.peak_mm > motion.hold_mm && motion.hold_mm > 0 && motion.peak_mm <= 1)
        || ![motion.rise_ms, motion.settle_ms, motion.retract_ms].every(x => Number.isFinite(x) && x > 0)
        || !(Number.isFinite(motion.peak_pause_ms) && motion.peak_pause_ms >= 0) || motion.curve !== "linear") throw new Error("INVALID_MOTION");
      viewer = await Braille3D.createViewer({
        canvas, view, labels: $("labels"), assets: embedded, onChange: requestFrame,
        onPin: index => { enterManual(); setTarget(index, !states[index].target); }
      });
      ready = true; message.hidden = true; $("resetView").disabled = false; $("viewMode").disabled = false; $("enclosureVisible").disabled = false; resize();
    } catch (error) {
      console.error(error); message.hidden = false;
      message.textContent = "3D 预览未能加载，请用启用图形加速的 Chrome 或 Edge 打开后重试。";
    }
  }

  $("allOn").addEventListener("click", () => { enterManual(); applyGrid(Array.from({ length: 10 }, () => Array(9).fill(1))); });
  $("allOff").addEventListener("click", () => { enterManual(); applyGrid(emptyGrid()); });
  $("invert").addEventListener("click", () => { enterManual(); applyGrid(currentGrid().map(row => row.map(value => 1 - value))); });
  $("checker").addEventListener("click", () => { enterManual(); applyGrid(Array.from({ length: 10 }, (_, r) => Array.from({ length: 9 }, (_, c) => Number((r + c) % 2 === 0)))); });
  $("loadText").addEventListener("click", () => loadRecords($("jsonInput").value, "粘贴的 JSON"));
  $("fileInput").addEventListener("change", async event => {
    const file = event.target.files[0]; if (!file) return;
    try { const text = await file.text(); if (loadRecords(text, file.name)) $("jsonInput").value = text; }
    catch (_) { feedback("文件读取失败，请重新选择。", true); }
    event.target.value = "";
  });
  $("demo").addEventListener("click", () => { $("jsonInput").value = JSON.stringify(demoRecords(), null, 2); loadRecords($("jsonInput").value, "示例 · 棋盘 / 十字 / 全凸起"); });
  $("play").addEventListener("click", play);
  $("previous").addEventListener("click", () => { pause(); applyRecord(current - 1); });
  $("next").addEventListener("click", () => { pause(); applyRecord(current + 1); });
  $("rewind").addEventListener("click", () => { pause(); applyRecord(0); });
  $("timeline").addEventListener("input", event => { pause(); applyRecord(Number(event.target.value)); });
  $("speed").addEventListener("change", event => {
    const now = performance.now(); if (playing) { sequenceStart += (now - clockStart) * speed; clockStart = now; }
    speed = Number(event.target.value);
  });
  $("append").addEventListener("click", appendFrame); $("save").addEventListener("click", saveJSON);
  $("numbering").addEventListener("change", () => { $("labels").hidden = !$("numbering").checked; requestFrame(); });
  $("resetView").addEventListener("click", () => { if (viewer) viewer.reset(); });
  $("viewMode").addEventListener("change", event => { if (viewer) viewer.setView(event.target.value); });
  $("enclosureVisible").addEventListener("change", event => { if (viewer) viewer.setEnclosureVisible(event.target.checked); });
  function capture(value) { document.body.classList.toggle("capture", value); resize(); if (value) view.focus({ preventScroll: true }); }
  $("capture").addEventListener("click", () => capture(true)); $("exitCapture").addEventListener("click", () => capture(false));
  window.addEventListener("keydown", event => { if (event.key === "Escape" && document.body.classList.contains("capture")) { event.preventDefault(); capture(false); } });
  window.addEventListener("resize", resize);
  canvas.addEventListener("webglcontextlost", event => { event.preventDefault(); ready = false; message.hidden = false; message.textContent = "画面暂停，请刷新页面继续。"; });
  window.arrayPreview = Object.freeze({
    getState: () => states.map((state, index) => ({ index, module: Math.floor(index / 6) + 1, number: index % 6 + 1, target: state.target, height_mm: state.height, phase: state.phase })),
    getGrid: () => currentGrid(), getBytes: () => gridToBytes(currentGrid()),
    getSequence: () => records.map(record => ({ ...record, frame: copyGrid(record.frame) })),
    gridToBytes, bytesToGrid, parseRecords,
    setGrid: value => { const grid = validateGrid(value); enterManual(); applyGrid(grid); },
    loadJSON: text => loadRecords(text, "JSON"),
    toggleDot: (module, number) => { if (!Number.isInteger(module) || module < 1 || module > 15 || !Number.isInteger(number) || number < 1 || number > 6) throw new Error("模组 1–15，触点 1–6。"); enterManual(); const index = (module - 1) * 6 + number - 1; setTarget(index, !states[index].target); }
  });
  updateControls(); updateTimeline(); start();
})();

