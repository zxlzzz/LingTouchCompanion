import { parseAssistantCommand } from '@/api/assistant.js'
import { searchPlace, reverseGeocode } from '@/api/map.js'
import { invokeDeviceHandler } from '@/utils/deviceBridge.js'

const WAKE_WORD_ALIASES = [
	'灵触助手',
	'零触助手',
	'领触助手',
	'领处助手',
	'灵处助手','临处助手',
	'零处助手',
	'林处助手'
]



const ASSISTANT_SELECTED_PLACE_KEY = 'assistant_selected_place'
const VOICE_SWITCH_KEY = 'voiceBroadcastEnabled'

let isRunning = false
let isStopped = false
let voiceBroadcastEnabled = true

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms))

const sanitizeText = (text = '') => {
	return String(text).replace(/\s+/g, '').trim()
}

const speakText = (text) => {
	const content = String(text || '').trim()
	if (!content) return
	if (!voiceBroadcastEnabled) return

	try {
		if (typeof window !== 'undefined' && window.speechSynthesis) {
			window.speechSynthesis.cancel()
			const utter = new SpeechSynthesisUtterance(content)
			utter.lang = 'zh-CN'
			window.speechSynthesis.speak(utter)
		}
	} catch (err) {
		console.warn('[globalAssistant] 语音播报失败：', err)
	}
}

const recognizeSpeechText = async () => {
	return new Promise((resolve) => {
		if (typeof window === 'undefined') {
			resolve('')
			return
		}

		const SpeechRecognition =
			window.SpeechRecognition || window.webkitSpeechRecognition

		if (!SpeechRecognition) {
			console.warn('[globalAssistant] 当前浏览器不支持语音识别')
			resolve('')
			return
		}

		const recognition = new SpeechRecognition()
		recognition.lang = 'zh-CN'
		recognition.continuous = false
		recognition.interimResults = false
		recognition.maxAlternatives = 1

		let finished = false

		const safeResolve = (value) => {
			if (finished) return
			finished = true
			resolve(String(value || '').trim())
		}

		recognition.onstart = () => {
			console.log('[globalAssistant] 语音识别已开始')
		}

		recognition.onresult = (event) => {
			const text = event?.results?.[0]?.[0]?.transcript || ''
			console.log('[globalAssistant] 识别结果：', text)
			safeResolve(text)
		}

		recognition.onerror = (event) => {
			console.warn('[globalAssistant] 语音识别失败：', event)
			safeResolve('')
		}

		recognition.onend = () => {
			safeResolve('')
		}

		try {
			recognition.start()
		} catch (err) {
			console.warn('[globalAssistant] 启动语音识别失败：', err)
			safeResolve('')
		}
	})
}

const matchWakeWord = (text = '') => {
	const normalized = sanitizeText(text)
	if (!normalized) return false
	return WAKE_WORD_ALIASES.some(word => normalized.includes(sanitizeText(word)))
}

const extractCommandData = (res) => {
	if (!res) return {}
	if (res.intent) return res
	if (res.data && res.data.intent) return res.data
	return {}
}

const getCurrentPosition = async () => {
	try {
		if (typeof navigator !== 'undefined' && navigator.geolocation) {
			const pos = await new Promise((resolve, reject) => {
				navigator.geolocation.getCurrentPosition(
					(position) => {
						resolve({
							lat: position.coords.latitude,
							lng: position.coords.longitude
						})
					},
					reject,
					{
						enableHighAccuracy: true,
						timeout: 12000,
						maximumAge: 0
					}
				)
			})
			return pos
		}
	} catch (err) {
		console.warn('[globalAssistant] 浏览器定位失败：', err)
	}

	try {
		const pos = await new Promise((resolve, reject) => {
			uni.getLocation({
				type: 'gcj02',
				isHighAccuracy: true,
				highAccuracyExpireTime: 10000,
				success: (res) => {
					resolve({
						lat: res.latitude,
						lng: res.longitude
					})
				},
				fail: reject
			})
		})
		return pos
	} catch (err) {
		console.warn('[globalAssistant] uni 定位失败：', err)
		return {
			lat: 39.9042,
			lng: 116.4074
		}
	}
}

const getCurrentCity = async () => {
	try {
		const pos = await getCurrentPosition()
		const res = await reverseGeocode(pos.lat, pos.lng)
		return res?.data?.addressComponent?.city || res?.addressComponent?.city || '全国'
	} catch (err) {
		console.warn('[globalAssistant] 获取当前城市失败：', err)
		return '全国'
	}
}

const isGenericHospitalRequest = (destination = '') => {
	const text = sanitizeText(destination)
	if (!text) return false

	const exactMatches = [
		'医院',
		'去医院',
		'最近的医院',
		'附近的医院',
		'附近医院',
		'去最近的医院',
		'去附近的医院'
	]

	if (exactMatches.includes(text)) return true
	if (text.includes('最近') && text.includes('医院')) return true
	if (text.includes('附近') && text.includes('医院')) return true

	return false
}

const getNearbyHospitals = async () => {
	const city = await getCurrentCity()
	const res = await searchPlace('医院', city)
	const list = res?.data?.results || []

	return list.slice(0, 5).map((item) => ({
		name: item.name,
		address: item.address || '',
		location: item.location || { lat: '', lng: '' }
	}))
}

const speakHospitalList = async (list = []) => {
	if (!list.length) {
		speakText('附近没有找到医院')
		return
	}

	const parts = list.map((item, index) => `第${index + 1}个，${item.name}`)
	const text = `为您找到附近医院。${parts.join('。')}。请说第几个，或者直接说医院名称。`
	speakText(text)
}

const chineseNumberMap = {
	一: 1,
	二: 2,
	两: 2,
	三: 3,
	四: 4,
	五: 5,
	六: 6,
	七: 7,
	八: 8,
	九: 9,
	十: 10
}

const parseHospitalChoice = (text = '', list = []) => {
	const normalized = sanitizeText(text)
	if (!normalized || !list.length) return null

	const matchDigit = normalized.match(/第?(\d+)个?/)
	if (matchDigit) {
		const idx = Number(matchDigit[1]) - 1
		if (idx >= 0 && idx < list.length) return list[idx]
	}

	const matchChinese = normalized.match(/第?([一二两三四五六七八九十])个?/)
	if (matchChinese) {
		const idx = (chineseNumberMap[matchChinese[1]] || 0) - 1
		if (idx >= 0 && idx < list.length) return list[idx]
	}

	const exact = list.find(item => sanitizeText(item.name) === normalized)
	if (exact) return exact

	const fuzzy = list.find(item => sanitizeText(item.name).includes(normalized) || normalized.includes(sanitizeText(item.name)))
	if (fuzzy) return fuzzy

	return null
}

const navigateByPlaceObject = async (place) => {
	if (!place || !place.location?.lat || !place.location?.lng) {
		speakText('目的地信息不完整，无法开始导航')
		return
	}

	try {
		uni.setStorageSync(ASSISTANT_SELECTED_PLACE_KEY, place)
	} catch (err) {
		console.warn('[globalAssistant] 保存选中地点失败：', err)
	}

	speakText(`正在为您导航到${place.name}`)
	await sleep(300)

	uni.reLaunch({
		url: `/pages/navigation/navigation?assistantPlace=1`
	})
}

const handleHospitalFlow = async () => {
	try {
		const hospitalCandidates = await getNearbyHospitals()

		if (!hospitalCandidates.length) {
			speakText('附近没有找到医院')
			return
		}

		await speakHospitalList(hospitalCandidates)
		await sleep(1000)

		const choiceText = await recognizeSpeechText()
		console.log('[globalAssistant] 医院选择：', choiceText)

		if (!choiceText) {
			speakText('没有听清您的选择')
			return
		}

		const selectedHospital = parseHospitalChoice(choiceText, hospitalCandidates)

		if (!selectedHospital) {
			speakText('没有匹配到您选择的医院')
			return
		}

		await navigateByPlaceObject(selectedHospital)
	} catch (err) {
		console.error('[globalAssistant] 医院选择流程失败：', err)
		speakText('医院选择失败')
	}
}

const buildDiagnosticSpeakText = (diagnosticResult) => {
	if (!diagnosticResult) {
		return '暂未获取到设备诊断结果'
	}

	const abnormalItems = diagnosticResult.abnormalItems || []
	if (!abnormalItems.length) {
		return '设备状态正常，各项检测均无异常'
	}

	return `设备存在异常，异常项包括：${abnormalItems.join('，')}`
}

const handleAssistantCommand = async (command) => {
	if (!command || !command.intent) {
		speakText('没有听清，请再试一次')
		return
	}

	switch (command.intent) {
		case 'start_navigation': {
			const destination = String(command.destination || '').trim()
			if (!destination) {
				speakText('没有识别到目的地')
				return
			}

			if (isGenericHospitalRequest(destination)) {
				await handleHospitalFlow()
				return
			}

			speakText(`正在为您导航到${destination}`)
			await sleep(300)

			uni.reLaunch({
				url: `/pages/navigation/navigation?keyword=${encodeURIComponent(destination)}`
			})
			return
		}

		case 'connect_device': {
			const result = await invokeDeviceHandler('connect')
			if (result.success) {
				speakText('正在连接设备')
			} else {
				speakText('正在打开设备页进行连接')
				await sleep(300)
				uni.reLaunch({ url: '/pages/device/device?autoConnect=1' })
			}
			return
		}

		case 'disconnect_device': {
			const result = await invokeDeviceHandler('disconnect')
			if (result.success) {
				speakText('正在断开设备')
			} else {
				speakText('正在打开设备页进行断开')
				await sleep(300)
				uni.reLaunch({ url: '/pages/device/device?autoDisconnect=1' })
			}
			return
		}

		case 'run_device_diagnostic': {
			speakText('正在检测设备，请稍候')
			const result = await invokeDeviceHandler('diagnostic')

			if (result.success && result.data) {
				const speakMessage = buildDiagnosticSpeakText(result.data)
				await sleep(500)
				speakText(speakMessage)
			} else {
				speakText('设备检测失败，请稍后重试')
			}
			return
		}

		case 'get_battery_status': {
			const result = await invokeDeviceHandler('getBatteryStatus')
			if (result.success && result.data?.message) {
				speakText(result.data.message)
			} else {
				speakText('当前暂未接入设备电量读取')
			}
			return
		}

		case 'get_device_status': {
			const result = await invokeDeviceHandler('getDeviceStatus')
			if (result.success && result.data) {
				const speakMessage = buildDiagnosticSpeakText(result.data)
				speakText(speakMessage)
			} else {
				speakText('暂时无法获取设备状态')
			}
			return
		}

		case 'open_page': {
			const pageMap = {
				home: '/pages/home/home',
				navigation: '/pages/navigation/navigation',
				device: '/pages/device/device',
				diagnostic: '/pages/diagnostic/diagnostic'
			}
			const page = String(command.page || '').trim()
			const url = pageMap[page]
			if (!url) {
				speakText('暂不支持打开该页面')
				return
			}
			speakText('正在打开页面')
			await sleep(300)
			uni.reLaunch({ url })
			return
		}

		case 'set_voice_switch':
			voiceBroadcastEnabled = Boolean(command.value)
			try {
				uni.setStorageSync(VOICE_SWITCH_KEY, voiceBroadcastEnabled)
			} catch (err) {
				console.warn('[globalAssistant] 保存语音播报开关失败：', err)
			}
			speakText(voiceBroadcastEnabled ? '已打开语音播报' : '已关闭语音播报')
			return

		case 'cancel_navigation':
			speakText('已取消导航')
			await sleep(300)
			uni.reLaunch({ url: '/pages/home/home' })
			return

		default:
			speakText('暂不支持该语音指令')
	}
}

const runOneRound = async () => {
	if (isStopped) return
	if (typeof window === 'undefined' || (!window.SpeechRecognition && !window.webkitSpeechRecognition)) return

	console.log('[globalAssistant] waiting wake word...')
	const wakeText = await recognizeSpeechText()
	console.log('[globalAssistant] wakeText =', wakeText)

	if (isStopped) return

	if (!wakeText) {
		await sleep(800)
		if (!isStopped) runOneRound()
		return
	}

	if (!matchWakeWord(wakeText)) {
		await sleep(800)
		if (!isStopped) runOneRound()
		return
	}

	speakText('请说')
	await sleep(1000)

	const commandText = await recognizeSpeechText()
	console.log('[globalAssistant] commandText =', commandText)

	if (isStopped) return

	if (!commandText) {
		speakText('没有听清指令')
		await sleep(1200)
		if (!isStopped) runOneRound()
		return
	}

	try {
		const parsedRes = await parseAssistantCommand(commandText)
		const command = extractCommandData(parsedRes)
		console.log('[globalAssistant] command =', command)
		await handleAssistantCommand(command)
	} catch (err) {
		console.error('[globalAssistant] 命令解析失败：', err)
		speakText('语音指令处理失败')
	}

	await sleep(1200)
	if (!isStopped) runOneRound()
}

export const startGlobalAssistant = async () => {
	if (isRunning) return

	if (typeof window === 'undefined') {
		console.warn('[globalAssistant] 非浏览器环境，语音助手不启动')
		return
	}
	if (!window.SpeechRecognition && !window.webkitSpeechRecognition) {
		console.warn('[globalAssistant] 当前环境不支持语音识别，语音助手不启动')
		return
	}

	try {
		const localVoiceSwitch = uni.getStorageSync(VOICE_SWITCH_KEY)
		if (typeof localVoiceSwitch === 'boolean') {
			voiceBroadcastEnabled = localVoiceSwitch
		}
	} catch (err) {
		console.warn('[globalAssistant] 读取语音播报开关失败：', err)
	}

	isRunning = true
	isStopped = false

	console.log('[globalAssistant] startGlobalAssistant called')
	speakText('语音助手已就绪')
	await sleep(1200)

	runOneRound()
}

export const stopGlobalAssistant = () => {
	console.log('[globalAssistant] stopGlobalAssistant called')
	isStopped = true
	isRunning = false
}

export const getAssistantSelectedPlaceKey = () => ASSISTANT_SELECTED_PLACE_KEY