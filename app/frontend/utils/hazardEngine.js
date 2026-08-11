/**
 * utils/hazardEngine.js
 * 危险播报引擎：危险事件接入 + 播报调度（分级 / 去重 / 间隔 / 优先级打断）
 *
 * 数据源约定：任何数据源（未来 BLE 摄像头、模拟源、网页摄像头识别）只需调用
 * notifyHazard(hazard) 即可接入，播报与 UI 逻辑无需改动。
 *
 * 危险事件模型：
 * {
 *   type: 'vehicle' | 'person' | 'obstacle' | 'stair' | 'pothole' | 'pole' | 'bicycle' | 'curb' | ...,
 *   direction: 'front' | 'front_left' | 'front_right' | 'left' | 'right',
 *   distance: 2.5,        // 米，由深度估计 / 传感器给出
 *   confidence: 0.85,     // 置信度（可选）
 *   timestamp: 1730000000000,
 *   label: '车辆'          // 可选，自定义文案，缺省按 type 映射
 * }
 */

import { speakText } from '@/utils/tts.js'

// ---------- 类型与方位文案映射 ----------

export const TYPE_LABELS = {
	vehicle: '车辆',
	person: '行人',
	obstacle: '障碍物',
	stair: '楼梯',
	pothole: '水坑',
	water: '水坑',
	pole: '电线杆',
	bicycle: '自行车',
	curb: '路缘石'
}

const DIRECTION_LABELS = {
	front: '前方',
	front_left: '左前方',
	front_right: '右前方',
	left: '左侧',
	right: '右侧'
}

// ---------- 播报调度参数 ----------

const URGENT_DISTANCE = 2 // ≤2m：紧急，立即播报（跳过全局间隔）
const MID_DISTANCE = 5 // 2~5m：常规播报；>5m：仅 UI 提示不播报
const MIN_INTERVAL = 3000 // 常规播报全局最小间隔（防播报风暴）
const REPEAT_SUPPRESS = 10000 // 同类型+同方向去重窗口（常规）
const URGENT_SUPPRESS = 5000 // 同类型+同方向去重窗口（紧急）

let lastBroadcastAt = 0
const lastHazardAt = new Map() // `${type}:${direction}` → 上次播报时间

// ---------- UI 订阅（危险横幅等） ----------

const uiListeners = new Set()

/**
 * 订阅危险事件 UI 展示
 * @param {(hazard: object, text: string|null) => void} fn
 * @returns {() => void} 取消订阅函数
 */
export const onHazardUi = (fn) => {
	uiListeners.add(fn)
	return () => {
		uiListeners.delete(fn)
	}
}

const emitUi = (hazard, text) => {
	uiListeners.forEach((fn) => {
		try {
			fn(hazard, text)
		} catch (err) {
			console.warn('[hazardEngine] UI 回调异常：', err)
		}
	})
}

// ---------- 播报文案生成 ----------

export const buildHazardText = (hazard) => {
	const label = hazard.label || TYPE_LABELS[hazard.type] || '障碍物'
	const dirText = DIRECTION_LABELS[hazard.direction] || '前方'
	const distance = Math.max(0, Math.round(hazard.distance || 0))
	const urgent = Number(hazard.distance) <= URGENT_DISTANCE

	if (urgent) {
		return `危险！${dirText}有${label}，距离${distance}米！请小心！`
	}
	return `${dirText}有${label}，距离${distance}米，请小心`
}

// ---------- 播报调度 ----------

/**
 * 上报一条危险事件（由各数据源调用）
 */
export const notifyHazard = (hazard) => {
	if (!hazard || typeof hazard !== 'object') return

	const distance = Number(hazard.distance)
	if (!isFinite(distance) || distance <= 0) return

	// >5m：仅 UI 提示，不语音播报
	if (distance > MID_DISTANCE) {
		emitUi(hazard, null)
		return
	}

	const urgent = distance <= URGENT_DISTANCE
	const now = Date.now()
	const key = `${hazard.type || 'unknown'}:${hazard.direction || 'front'}`
	const lastAt = lastHazardAt.get(key) || 0
	const suppressWindow = urgent ? URGENT_SUPPRESS : REPEAT_SUPPRESS

	// 去重：同类型+同方向在窗口期内不重复播报
	if (now - lastAt < suppressWindow) return

	// 常规播报受全局最小间隔限制；紧急播报可立即打断
	if (!urgent && now - lastBroadcastAt < MIN_INTERVAL) return

	lastHazardAt.set(key, now)
	lastBroadcastAt = now

	const text = buildHazardText(hazard)
	// 危险播报优先级最高，会打断导航/助手播报，且不受语音开关限制
	speakText(text, { priority: 'hazard' })
	emitUi(hazard, text)
}

// ---------- 数据源注册 ----------

let hazardSource = null

/**
 * 注册危险数据源（同一时刻只有一个生效，后者覆盖前者）
 * 数据源需实现 start() / stop() 生命周期（可选）
 */
export const registerHazardSource = (source) => {
	hazardSource = source
}

export const getHazardSource = () => hazardSource

// ---------- 引擎开关 ----------

let monitoring = false

/**
 * 启动危险监听（应用级常驻，独立于语音助手唤醒词）
 */
export const startHazardMonitoring = () => {
	if (monitoring) return
	monitoring = true
	if (hazardSource && typeof hazardSource.start === 'function') {
		hazardSource.start()
	}
}

/**
 * 停止危险监听
 */
export const stopHazardMonitoring = () => {
	if (!monitoring) return
	monitoring = false
	if (hazardSource && typeof hazardSource.stop === 'function') {
		hazardSource.stop()
	}
}

export const isHazardMonitoring = () => monitoring
