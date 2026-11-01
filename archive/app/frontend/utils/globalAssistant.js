import { parseAssistantCommand } from '@/api/assistant.js'
import { searchPlace, reverseGeocode } from '@/api/map.js'
import { invokeDeviceHandler } from '@/utils/deviceBridge.js'
import { speakText, setVoiceBroadcastEnabled, getVoiceBroadcastEnabled } from '@/utils/tts.js'
import { wgs84ToBd09, gcj02ToBd09 } from '@/utils/coord.js'

const WAKE_WORD_ALIASES = [
	'灵触助手',
	'灵触随行', // 产品名「灵触·随行智能盲杖」的常见喊法
	'零触助手',
	'领触助手',
	'领处助手',
	'灵处助手','临处助手',
	'零处助手',
	'林处助手'
]

const ASSISTANT_SELECTED_PLACE_KEY = 'assistant_selected_place'

let isRunning = false
let isStopped = false

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms))

const sanitizeText = (text = '') => {
	return String(text).replace(/\s+/g, '').trim()
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
			// 浏览器定位为 WGS84，转换为百度坐标系 BD09
			return wgs84ToBd09(pos.lat, pos.lng)
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
		// uni.getLocation 返回 GCJ02，转换为 BD09
		return gcj02ToBd09(pos.lat, pos.lng)
	} catch (err) {
		console.warn('[globalAssistant] uni 定位失败：', err)
		return wgs84ToBd09(39.9042, 116.4074) // 默认北京，统一到 BD09
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

// ---------- 医院专项流程（「去医院」「最近的医院」等泛化说法） ----------

/**
 * 判断是否为泛化医院请求。
 * 这类说法不能当具体目的地搜索（如直接搜「最近的医院」搜不到），
 * 需走「附近医院列表 → 语音选择」专项流程。
 */
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
		await speakText('附近没有找到医院')
		return
	}

	const parts = list.map((item, index) => `第${index + 1}个，${item.name}`)
	const text = `为您找到附近医院。${parts.join('。')}。请说第几个，或者直接说医院名称。`
	await speakText(text)
}

const handleHospitalFlow = async () => {
	try {
		const hospitalCandidates = await getNearbyHospitals()

		if (!hospitalCandidates.length) {
			await speakText('附近没有找到医院')
			return
		}

		await speakHospitalList(hospitalCandidates)
		await sleep(1000)

		const choiceText = await recognizeSpeechText()
		console.log('[globalAssistant] 医院选择：', choiceText)

		if (!choiceText) {
			await speakText('没有听清您的选择')
			return
		}

		const selectedHospital = parsePlaceChoice(choiceText, hospitalCandidates)

		if (!selectedHospital) {
			await speakText('没有匹配到您选择的医院')
			return
		}

		await navigateByPlaceObject(selectedHospital)
	} catch (err) {
		console.error('[globalAssistant] 医院选择流程失败：', err)
		await speakText('医院选择失败')
	}
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

const parsePlaceChoice = (text = '', list = []) => {
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
		await speakText('目的地信息不完整，无法开始导航')
		return
	}

	try {
		uni.setStorageSync(ASSISTANT_SELECTED_PLACE_KEY, place)
	} catch (err) {
		console.warn('[globalAssistant] 保存选中地点失败：', err)
	}

	await speakText(`正在为您导航到${place.name}`)

	uni.reLaunch({
		url: `/pages/navigation/navigation?assistantPlace=1`
	})
}

/**
 * 通用导航流程（任意 POI 多候选语音选择）：
 * 搜索目的地 → 无结果提示换说法 / 单结果直接导航 / 多结果播报列表语音选择
 */
const handleNavigationFlow = async (destination) => {
	const city = await getCurrentCity()
	let list = []

	try {
		const res = await searchPlace(destination, city)
		list = res?.data?.results || []
	} catch (err) {
		console.error('[globalAssistant] 目的地搜索失败：', err)
	}

	// 搜索失败时兜底：直接跳导航页，由页面手动选择
	if (!list.length) {
		await speakText(`没有找到${destination}，正在打开导航页面，请手动选择目的地`)
		uni.reLaunch({
			url: `/pages/navigation/navigation?keyword=${encodeURIComponent(destination)}`
		})
		return
	}

	const candidates = list.slice(0, 5).map((item) => ({
		name: item.name,
		address: item.address || '',
		location: item.location || { lat: '', lng: '' }
	}))

	if (candidates.length === 1) {
		await navigateByPlaceObject(candidates[0])
		return
	}

	// 多个候选 → 语音播报列表，等用户选择
	const parts = candidates.map((item, index) => `第${index + 1}个，${item.name}`)
	await speakText(`为您找到多个地点。${parts.join('。')}。请说第几个，或直接说地点名称。`)

	const choiceText = await recognizeSpeechText()
	console.log('[globalAssistant] 地点选择：', choiceText)

	if (!choiceText) {
		await speakText('没有听清您的选择，正在打开导航页面')
		uni.reLaunch({
			url: `/pages/navigation/navigation?keyword=${encodeURIComponent(destination)}`
		})
		return
	}

	const selectedPlace = parsePlaceChoice(choiceText, candidates)

	if (!selectedPlace) {
		await speakText('没有匹配到您选择的地点，正在打开导航页面')
		uni.reLaunch({
			url: `/pages/navigation/navigation?keyword=${encodeURIComponent(destination)}`
		})
		return
	}

	await navigateByPlaceObject(selectedPlace)
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
		await speakText('没有听清，请再试一次')
		return
	}

	switch (command.intent) {
		case 'start_navigation': {
			const destination = String(command.destination || '').trim()
			if (!destination) {
				await speakText('没有识别到目的地')
				return
			}

			// 泛化医院说法（去医院/最近的医院等）走专项流程，其他目的地走通用流程
			if (isGenericHospitalRequest(destination)) {
				await handleHospitalFlow()
				return
			}

			await handleNavigationFlow(destination)
			return
		}

		case 'connect_device': {
			const result = await invokeDeviceHandler('connect')
			if (result.success) {
				await speakText('正在连接设备')
			} else {
				await speakText('正在打开设备页进行连接')
				uni.reLaunch({ url: '/pages/device/device?autoConnect=1' })
			}
			return
		}

		case 'disconnect_device': {
			const result = await invokeDeviceHandler('disconnect')
			if (result.success) {
				await speakText('正在断开设备')
			} else {
				await speakText('正在打开设备页进行断开')
				uni.reLaunch({ url: '/pages/device/device?autoDisconnect=1' })
			}
			return
		}

		case 'run_device_diagnostic': {
			await speakText('正在检测设备，请稍候')
			const result = await invokeDeviceHandler('diagnostic')

			if (result.success && result.data) {
				const speakMessage = buildDiagnosticSpeakText(result.data)
				await speakText(speakMessage)
			} else {
				await speakText('设备检测失败，请稍后重试')
			}
			return
		}

		case 'get_battery_status': {
			const result = await invokeDeviceHandler('getBatteryStatus')
			if (result.success && result.data?.message) {
				await speakText(result.data.message)
			} else {
				await speakText('当前暂未接入设备电量读取')
			}
			return
		}

		case 'get_device_status': {
			const result = await invokeDeviceHandler('getDeviceStatus')
			if (result.success && result.data) {
				const speakMessage = buildDiagnosticSpeakText(result.data)
				await speakText(speakMessage)
			} else {
				await speakText('暂时无法获取设备状态')
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
				await speakText('暂不支持打开该页面')
				return
			}
			await speakText('正在打开页面')
			uni.reLaunch({ url })
			return
		}

		case 'set_voice_switch':
			setVoiceBroadcastEnabled(Boolean(command.value))
			await speakText(getVoiceBroadcastEnabled() ? '已打开语音播报' : '已关闭语音播报')
			return

		case 'cancel_navigation':
			await speakText('已取消导航')
			uni.reLaunch({ url: '/pages/home/home' })
			return

		default:
			await speakText('暂不支持该语音指令')
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

	// 互斥：等待播报结束再开始识别，避免把播报声识别成指令
	await speakText('请说')

	if (isStopped) return

	const commandText = await recognizeSpeechText()
	console.log('[globalAssistant] commandText =', commandText)

	if (isStopped) return

	if (!commandText) {
		await speakText('没有听清指令')
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
		// uni.request 网络层失败（errMsg 以 request: 开头）说明后端不可达，
		// 给出可操作的提示，而不是笼统的「处理失败」
		const isNetworkError = String(err?.errMsg || '').startsWith('request:')
		if (isNetworkError) {
			await speakText('无法连接服务器，请确认后端服务已启动后再试')
		} else {
			await speakText('语音指令处理失败，请稍后重试')
		}
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

	isRunning = true
	isStopped = false

	console.log('[globalAssistant] startGlobalAssistant called')
	await speakText('语音助手已就绪')

	runOneRound()
}

export const stopGlobalAssistant = () => {
	console.log('[globalAssistant] stopGlobalAssistant called')
	isStopped = true
	isRunning = false
}

export const getAssistantSelectedPlaceKey = () => ASSISTANT_SELECTED_PLACE_KEY
