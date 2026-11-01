/**
 * utils/tts.js
 * 全局语音播报模块（speechSynthesis 封装）
 *
 * 职责：
 * 1. 统一所有语音播报出口（语音助手 / 导航指引 / 危险播报共用一份开关状态）
 * 2. 播报优先级：hazard（危险播报）可打断普通播报；普通播报不会打断 hazard
 * 3. speakText 返回 Promise：播报结束（或按字数估算的超时兜底）后 resolve，
 *    供「播报完再开始语音识别」的互斥流程使用，避免把播报声识别成指令
 *
 * 注意：危险播报（priority: 'hazard'）属于安全功能，不受「语音播报」开关限制。
 */

const VOICE_SWITCH_KEY = 'voiceBroadcastEnabled'

let voiceBroadcastEnabled = true
let currentPriority = 'normal'
let currentUtterance = null

// 模块加载时读取本地开关（uni 在 H5 端可用）
try {
	const stored = uni.getStorageSync(VOICE_SWITCH_KEY)
	if (typeof stored === 'boolean') voiceBroadcastEnabled = stored
} catch (err) {
	console.warn('[tts] 读取语音播报开关失败：', err)
}

const PRIORITY_RANK = {
	normal: 0,
	hazard: 1
}

export const getVoiceBroadcastEnabled = () => voiceBroadcastEnabled

export const setVoiceBroadcastEnabled = (value) => {
	voiceBroadcastEnabled = Boolean(value)
	try {
		uni.setStorageSync(VOICE_SWITCH_KEY, voiceBroadcastEnabled)
	} catch (err) {
		console.warn('[tts] 保存语音播报开关失败：', err)
	}
}

export const voiceSwitchKey = () => VOICE_SWITCH_KEY

/**
 * 语音播报
 * @param {string} text 播报内容
 * @param {object} [opts]
 * @param {'normal'|'hazard'} [opts.priority='normal'] 播报优先级
 * @param {number} [opts.rate=1] 语速
 * @returns {Promise<void>} 播报结束或超时兜底后 resolve
 */
export const speakText = (text, opts = {}) => {
	const content = String(text || '').trim()
	const priority = opts.priority || 'normal'

	if (!content) return Promise.resolve()

	// 普通播报受开关控制；危险播报不受限制（安全功能）
	if (!voiceBroadcastEnabled && priority !== 'hazard') return Promise.resolve()

	// 非浏览器环境或语音不可用
	if (typeof window === 'undefined' || !window.speechSynthesis) {
		console.warn('[tts] 当前环境不支持语音播报：', content)
		return Promise.resolve()
	}

	return new Promise((resolve) => {
		const synth = window.speechSynthesis

		// 正在播报 hazard 时，普通播报直接放弃（不打断危险播报）
		if (currentPriority === 'hazard' && priority !== 'hazard') {
			resolve()
			return
		}

		synth.cancel()
		currentUtterance = null

		const utter = new SpeechSynthesisUtterance(content)
		utter.lang = 'zh-CN'
		utter.rate = opts.rate || 1

		let settled = false
		const finish = () => {
			if (settled) return
			settled = true
			if (currentUtterance === utter) {
				currentUtterance = null
				currentPriority = 'normal'
			}
			resolve()
		}

		utter.onend = finish
		utter.onerror = finish

		currentUtterance = utter
		currentPriority = priority

		try {
			synth.speak(utter)
		} catch (err) {
			console.warn('[tts] 播报失败：', err)
			finish()
			return
		}

		// 超时兜底：Chrome 的 speechSynthesis 偶发不触发 onend，
		// 按字数估算时长（中文约 2~4 字/秒，取保守值）强制结束
		const estimateMs = Math.max(2000, content.length * 450 + 600)
		setTimeout(finish, estimateMs)
	})
}

/**
 * 立即取消当前播报
 */
export const cancelSpeech = () => {
	try {
		if (typeof window !== 'undefined' && window.speechSynthesis) {
			window.speechSynthesis.cancel()
		}
	} catch (err) {
		console.warn('[tts] 取消播报失败：', err)
	}
	currentUtterance = null
	currentPriority = 'normal'
}
