/**
 * utils/hazardMockSource.js
 * 危险播报模拟数据源（演示用）
 *
 * 在没有摄像头/BLE 硬件时，模拟盲杖摄像头识别结果：
 * 启用后周期性随机生成「车辆 / 水坑 / 楼梯…」等危险事件，
 * 完整走通「数据源 → 播报调度 → 语音播报 + UI 横幅」链路。
 *
 * 真实数据源（BLE 摄像头）就绪后，在 App.vue 中把
 * registerHazardSource(mockHazardSource) 换成真实源即可，其余逻辑零改动。
 */

import { notifyHazard } from '@/utils/hazardEngine.js'

const DEMO_SWITCH_KEY = 'hazardDemoEnabled'
const MIN_GAP = 6000 // 相邻两轮生成的最短间隔 ms
const MAX_GAP = 16000 // 最长间隔 ms

const TYPES = ['vehicle', 'vehicle', 'person', 'obstacle', 'pothole', 'stair', 'pole', 'bicycle']
const DIRECTIONS = ['front', 'front_left', 'front_right', 'left', 'right']

let enabled = false
let timer = null

// ---------- 开关（持久化到本地，重启后保持） ----------

export const isDemoEnabled = () => enabled

export const setDemoEnabled = (value) => {
	enabled = Boolean(value)
	try {
		uni.setStorageSync(DEMO_SWITCH_KEY, enabled)
	} catch (err) {
		console.warn('[hazardMockSource] 保存演示开关失败：', err)
	}

	if (!enabled) {
		clearTimer()
		return
	}
	// 开启后尽快产生第一条事件，方便演示
	scheduleNext(1500)
}

const initMockSource = () => {
	try {
		const stored = uni.getStorageSync(DEMO_SWITCH_KEY)
		if (typeof stored === 'boolean') enabled = stored
	} catch (err) {
		console.warn('[hazardMockSource] 读取演示开关失败：', err)
	}
	if (enabled) scheduleNext(2000)
}

// ---------- 定时生成 ----------

const clearTimer = () => {
	if (timer) {
		clearTimeout(timer)
		timer = null
	}
}

const scheduleNext = (gap) => {
	clearTimer()
	if (!enabled) return
	timer = setTimeout(emitRandomHazards, gap)
}

const randomOf = (arr) => arr[Math.floor(Math.random() * arr.length)]
const randomBetween = (min, max) => min + Math.random() * (max - min)

const emitRandomHazards = () => {
	if (!enabled) return

	// 35% 概率一次出两条（同一帧的多目标场景）
	const count = Math.random() < 0.35 ? 2 : 1

	for (let i = 0; i < count; i++) {
		notifyHazard({
			type: randomOf(TYPES),
			direction: randomOf(DIRECTIONS),
			// 距离加权：55% 落在 1~5m（可播报区间），其余更远（仅 UI 提示）
			distance: Math.round((Math.random() < 0.55 ? randomBetween(1, 5) : randomBetween(5, 8)) * 10) / 10,
			confidence: Math.round((0.6 + Math.random() * 0.35) * 100) / 100,
			timestamp: Date.now(),
			source: 'mock'
		})
	}

	scheduleNext(randomBetween(MIN_GAP, MAX_GAP))
}

// ---------- 生命周期（供引擎调用） ----------

export const mockHazardSource = {
	start() {
		initMockSource()
	},
	stop() {
		clearTimer()
	},
	setEnabled: setDemoEnabled,
	isEnabled: isDemoEnabled
}
