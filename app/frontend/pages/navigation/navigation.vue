<template>
	<view class="container">
		<!-- 地图层 -->
		<view class="map-layer">
			<view id="amapContainer" class="amap-box"></view>
		</view>

		<!-- 顶部搜索条 -->
		<view class="search-bar">
			<text class="search-icon">🔍</text>
			<input
				class="search-input"
				v-model="searchKeyword"
				type="text"
				placeholder="搜索医院、地铁站、超市、学校..."
				placeholder-class="search-input-placeholder"
				confirm-type="search"
				@confirm="onSearchConfirm"
			/>
			<view class="search-btn" @click="onSearchConfirm">
				<text class="search-btn-text">搜索</text>
			</view>
			<view class="mic-btn" :class="{ 'mic-listening': voiceListening }" @click="handleManualVoice">
				<text class="mic-icon">🎙️</text>
			</view>
		</view>

		<!-- 语音反馈条 -->
		<view class="voice-feedback" v-if="voiceFeedback">
			<text class="voice-feedback-text">{{ voiceFeedback }}</text>
		</view>

		<!-- 定位按钮 -->
		<view class="locate-btn" @click="handleLocate">
			<text class="locate-icon">📍</text>
		</view>

		<!-- 搜索候选列表 -->
		<view class="place-list" v-if="showPlaceList">
			<view class="place-list-header">
				<text class="place-list-title">请选择目的地</text>
				<text class="place-list-close" @click="showPlaceList = false">关闭</text>
			</view>

			<scroll-view class="place-scroll" scroll-y>
				<view
					class="place-item"
					v-for="(item, index) in placeList"
					:key="index"
					@click="handleSelectPlace(item)"
				>
					<view class="place-item-left">
						<text class="place-item-name">{{ item.name }}</text>
						<text class="place-item-address">{{ item.address || '暂无地址信息' }}</text>
					</view>
					<text class="place-item-arrow">›</text>
				</view>
			</scroll-view>
		</view>

		<!-- 状态提示 -->
		<view class="map-status">
			<text class="map-status-text">{{ locationText }}</text>
		</view>

		<!-- 导航信息卡片 -->
		<view class="nav-card" v-if="routeReady">
			<view class="card-top">
				<view class="title-row">
					<text class="destination-title">{{ routeData.destination }}</text>
					<view class="ai-tag">
						<text class="ai-tag-text">AI 推荐路线</text>
					</view>
				</view>

				<text class="route-time">{{ routeData.walking }}</text>
				<text class="route-desc">{{ routeData.description }}</text>
				<text class="route-address" v-if="routeData.address">{{ routeData.address }}</text>
			</view>

			<view class="divider"></view>

			<view class="current-step-box" v-if="currentStep">
				<text class="step-label">当前导航</text>
				<text class="step-instruction">{{ currentStep.instruction }}</text>

				<view class="step-meta">
					<text class="step-meta-item">本段 {{ currentStep.distanceText }}</text>
					<text class="step-meta-dot">·</text>
					<text class="step-meta-item">剩余 {{ currentStepRemainText }}</text>
					<text class="step-meta-dot">·</text>
					<text class="step-meta-item">{{ currentStep.turnText }}</text>
				</view>

				<text class="next-step" v-if="nextStep">
					下一步：{{ nextStep.instruction }}
				</text>
			</view>
		</view>

		<!-- 空态 -->
		<view class="empty-card" v-else>
			<text class="empty-title">开始导航</text>
			<text class="empty-desc">输入目的地并搜索，或直接说"灵触助手"后下达语音指令</text>
		</view>

		<!-- 底部 TabBar -->
		<view class="tabbar">
			<view class="tab-item" @click="handleTabClick('home')">
				<text class="tab-icon">🏠</text>
				<text class="tab-label">出行</text>
			</view>
			<view class="tab-item active" @click="handleTabClick('navigation')">
				<text class="tab-icon">🗺️</text>
				<text class="tab-label">导航</text>
			</view>
			<view class="tab-item" @click="handleTabClick('device')">
				<text class="tab-icon">⚙️</text>
				<text class="tab-label">设备</text>
			</view>
			<view class="tab-item" @click="handleTabClick('diagnostic')">
				<text class="tab-icon">📊</text>
				<text class="tab-label">诊断</text>
			</view>
		</view>
	</view>
</template>

<script setup>
import { ref, computed, nextTick, onBeforeUnmount } from 'vue'
import { onLoad, onReady } from '@dcloudio/uni-app'
import { searchPlace, getWalkRoute, reverseGeocode } from '@/api/map.js'
import { getAssistantSelectedPlaceKey } from '@/utils/globalAssistant.js'

// ======================== 配置 ========================
// 高德 JS API Key（与 REST API 的 Key 不同，需要单独申请 JS API 类型）
// 如果你只申请了 Web服务 Key，需要再申请一个 "Web端(JS API)" Key
const AMAP_JS_KEY = 'd40d91da8f4450f8c9677f3b439c1ff1'         // ← 替换
const AMAP_JS_SECURITY = 'f501d8e9609333da4084a7aafb011071'  // ← 替换（高德安全密钥）

const DEFAULT_LOCATION = {
	lat: 39.9042,
	lng: 116.4074
}

const searchKeyword = ref('')
const routeReady = ref(false)
const locationText = ref('地图加载中...')
const currentCity = ref('')
const voiceBroadcastEnabled = ref(true)

const placeList = ref([])
const showPlaceList = ref(false)

const currentLocation = ref({
	lat: DEFAULT_LOCATION.lat,
	lng: DEFAULT_LOCATION.lng
})

const selectedDestination = ref({
	lat: '',
	lng: ''
})

const routeData = ref({
	destination: '',
	walking: '',
	description: '',
	address: '',
	distance: 0,
	duration: 0,
	polylinePoints: []
})

const routeSteps = ref([])
const currentStepIndex = ref(0)
const currentStepRemain = ref(0)

const currentStep = computed(() => routeSteps.value[currentStepIndex.value] || null)
const nextStep = computed(() => routeSteps.value[currentStepIndex.value + 1] || null)
const currentStepRemainText = computed(() => `${Math.max(0, Math.round(currentStepRemain.value))} 米`)

let mapInstance = null
let currentMarker = null
let destinationMarker = null
let destinationLabel = null
let routePolyline = null
let activeStepPolyline = null
let locationTimer = null
let lastSpokenStepIndex = -1
let pendingAssistantPlace = null

// ======================== 工具函数（与原版相同） ========================

const sanitizeInstruction = (text = '') => {
	return String(text).replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim()
}

const formatDistance = (distance = 0) => {
	const n = Number(distance) || 0
	if (n >= 1000) return `${(n / 1000).toFixed(1)} 公里`
	return `${Math.round(n)} 米`
}

const getTurnText = (instruction = '') => {
	const text = sanitizeInstruction(instruction)
	if (text.includes('左转')) return '左转'
	if (text.includes('右转')) return '右转'
	if (text.includes('向左前方')) return '左前方'
	if (text.includes('向右前方')) return '右前方'
	if (text.includes('向左后方')) return '左后方'
	if (text.includes('向右后方')) return '右后方'
	if (text.includes('直行')) return '继续前进'
	if (text.includes('到达')) return '到达目的地'
	return '继续前进'
}

const haversineDistance = (lat1, lng1, lat2, lng2) => {
	const toRad = (deg) => (deg * Math.PI) / 180
	const R = 6371000
	const dLat = toRad(lat2 - lat1)
	const dLng = toRad(lng2 - lng1)
	const a =
		Math.sin(dLat / 2) * Math.sin(dLat / 2) +
		Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) * Math.sin(dLng / 2)
	return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

const parsePathStringToPoints = (path = '') => {
	if (!path || typeof path !== 'string') return []
	return path
		.split(';')
		.map((pair) => {
			const [lng, lat] = pair.split(',')
			if (lng === undefined || lat === undefined) return null
			return { lng: Number(lng), lat: Number(lat) }
		})
		.filter(Boolean)
}

const dedupePoints = (points = []) => {
	const result = []
	points.forEach((p) => {
		const last = result[result.length - 1]
		if (!last || last.lat !== p.lat || last.lng !== p.lng) {
			result.push({ lat: Number(p.lat), lng: Number(p.lng) })
		}
	})
	return result
}

const parseWholeRoutePoints = (route) => {
	if (!route || !Array.isArray(route.steps)) return []
	const points = []
	route.steps.forEach((step) => {
		if (step.path) {
			points.push(...parsePathStringToPoints(step.path))
		} else if (Array.isArray(step.points)) {
			step.points.forEach((p) => {
				if (p.lat !== undefined && p.lng !== undefined) {
					points.push({ lat: Number(p.lat), lng: Number(p.lng) })
				}
			})
		}
	})
	return dedupePoints(points)
}

const normalizeRouteSteps = (route) => {
	if (!route || !Array.isArray(route.steps)) return []
	return route.steps.map((step, index) => {
		const points = step.path
			? parsePathStringToPoints(step.path)
			: Array.isArray(step.points)
				? step.points.map((p) => ({ lat: Number(p.lat), lng: Number(p.lng) }))
				: []
		const cleanPoints = dedupePoints(points)
		const endPoint = cleanPoints.length ? cleanPoints[cleanPoints.length - 1] : null
		const instruction = sanitizeInstruction(step.instruction || `第 ${index + 1} 段路线`)
		const distance = Number(step.distance || 0)
		return {
			index,
			instruction,
			distance,
			distanceText: formatDistance(distance),
			duration: Number(step.duration || 0),
			turnText: getTurnText(instruction),
			points: cleanPoints,
			endPoint
		}
	})
}

// ======================== 高德地图 JS API 加载 ========================

const loadAmapScript = () => {
	return new Promise((resolve, reject) => {
		if (window.AMap) {
			resolve(window.AMap)
			return
		}

		// 设置安全密钥
		window._AMapSecurityConfig = {
			securityJsCode: AMAP_JS_SECURITY
		}

		const script = document.createElement('script')
		script.src = `https://webapi.amap.com/maps?v=2.0&key=${AMAP_JS_KEY}`
		script.onload = () => {
			if (window.AMap) {
				resolve(window.AMap)
			} else {
				reject(new Error('高德地图 JS API 加载失败'))
			}
		}
		script.onerror = () => reject(new Error('高德地图脚本加载失败'))
		document.head.appendChild(script)
	})
}

// ======================== 地图操作（百度→高德） ========================

const initMap = async () => {
	// #ifdef H5
	await nextTick()

	const mapDom = document.getElementById('amapContainer')
	if (!mapDom) {
		locationText.value = '地图容器不存在'
		return
	}

	try {
		await loadAmapScript()
	} catch (err) {
		locationText.value = '高德地图加载失败'
		console.error(err)
		return
	}

	if (mapInstance) return

	mapInstance = new window.AMap.Map('amapContainer', {
		zoom: 16,
		center: [currentLocation.value.lng, currentLocation.value.lat],
		resizeEnable: true
	})

	drawCurrentMarker(currentLocation.value.lng, currentLocation.value.lat, true)
	locationText.value = `当前位置：${currentLocation.value.lat.toFixed(5)}, ${currentLocation.value.lng.toFixed(5)}`
	// #endif
}

const clearRouteOverlays = () => {
	if (!mapInstance) return

	if (routePolyline) {
		mapInstance.remove(routePolyline)
		routePolyline = null
	}
	if (activeStepPolyline) {
		mapInstance.remove(activeStepPolyline)
		activeStepPolyline = null
	}
	if (destinationMarker) {
		mapInstance.remove(destinationMarker)
		destinationMarker = null
	}
	if (destinationLabel) {
		mapInstance.remove(destinationLabel)
		destinationLabel = null
	}
}

const drawCurrentMarker = (lng, lat, centerMap = false) => {
	if (!mapInstance || !window.AMap) return

	const position = new window.AMap.LngLat(Number(lng), Number(lat))

	if (currentMarker) {
		currentMarker.setPosition(position)
	} else {
		currentMarker = new window.AMap.Marker({
			position,
			map: mapInstance,
			icon: new window.AMap.Icon({
				size: new window.AMap.Size(25, 34),
				imageSize: new window.AMap.Size(25, 34)
			})
		})
	}

	if (centerMap) {
		mapInstance.setCenter(position)
	}
}

const drawDestinationMarker = (lng, lat, name) => {
	if (!mapInstance || !window.AMap) return

	const position = new window.AMap.LngLat(Number(lng), Number(lat))

	if (destinationMarker) {
		mapInstance.remove(destinationMarker)
	}
	if (destinationLabel) {
		mapInstance.remove(destinationLabel)
	}

	destinationMarker = new window.AMap.Marker({
		position,
		map: mapInstance
	})

	destinationLabel = new window.AMap.Text({
		text: name || '目的地',
		position,
		offset: new window.AMap.Pixel(12, -24),
		style: {
			color: '#d32f2f',
			fontSize: '12px',
			border: '1px solid #f5d5d5',
			borderRadius: '8px',
			padding: '4px 8px',
			backgroundColor: '#fff',
			boxShadow: '0 2px 10px rgba(0,0,0,0.08)'
		},
		map: mapInstance
	})
}

const drawWholeRouteOnMap = (points) => {
	if (!mapInstance || !window.AMap || !Array.isArray(points) || points.length < 2) return

	if (routePolyline) {
		mapInstance.remove(routePolyline)
	}

	const path = points.map((p) => new window.AMap.LngLat(Number(p.lng), Number(p.lat)))

	routePolyline = new window.AMap.Polyline({
		path,
		strokeColor: '#90caf9',
		strokeWeight: 6,
		strokeOpacity: 0.88,
		map: mapInstance
	})
}

const drawActiveStepOnMap = (points) => {
	if (!mapInstance || !window.AMap || !Array.isArray(points) || points.length < 2) return

	if (activeStepPolyline) {
		mapInstance.remove(activeStepPolyline)
	}

	const path = points.map((p) => new window.AMap.LngLat(Number(p.lng), Number(p.lat)))

	activeStepPolyline = new window.AMap.Polyline({
		path,
		strokeColor: '#1976d2',
		strokeWeight: 8,
		strokeOpacity: 1,
		map: mapInstance
	})
}

const updateMapFollow = () => {
	if (!mapInstance) return
	mapInstance.setCenter([currentLocation.value.lng, currentLocation.value.lat])
}

// ======================== 定位（保持原逻辑） ========================

const getBrowserLocation = () => {
	return new Promise((resolve, reject) => {
		// #ifdef H5
		if (!navigator.geolocation) {
			reject(new Error('当前浏览器不支持定位'))
			return
		}
		navigator.geolocation.getCurrentPosition(
			(position) => {
				resolve({
					lat: position.coords.latitude,
					lng: position.coords.longitude
				})
			},
			(error) => reject(error),
			{ enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
		)
		// #endif
		// #ifndef H5
		reject(new Error('非 H5 环境跳过浏览器定位'))
		// #endif
	})
}

const getUniLocation = () => {
	return new Promise((resolve, reject) => {
		uni.getLocation({
			type: 'gcj02',
			isHighAccuracy: true,
			highAccuracyExpireTime: 10000,
			success: (res) => resolve({ lat: res.latitude, lng: res.longitude }),
			fail: (err) => reject(err)
		})
	})
}

const getCurrentLocation = async (showToast = true, centerMap = true) => {
	locationText.value = '正在获取当前位置...'

	try {
		const browserPos = await getBrowserLocation()
		currentLocation.value = browserPos
		locationText.value = `当前位置：${browserPos.lat.toFixed(5)}, ${browserPos.lng.toFixed(5)}`

		if (mapInstance) drawCurrentMarker(browserPos.lng, browserPos.lat, centerMap)
		if (showToast) uni.showToast({ title: '定位成功', icon: 'none' })
		return browserPos
	} catch (browserErr) {
		console.warn('浏览器定位失败：', browserErr)

		try {
			const uniPos = await getUniLocation()
			currentLocation.value = uniPos
			locationText.value = `当前位置：${uniPos.lat.toFixed(5)}, ${uniPos.lng.toFixed(5)}`

			if (mapInstance) drawCurrentMarker(uniPos.lng, uniPos.lat, centerMap)
			if (showToast) uni.showToast({ title: '定位成功', icon: 'none' })
			return uniPos
		} catch (uniErr) {
			console.warn('uni 定位失败：', uniErr)
			currentLocation.value = { ...DEFAULT_LOCATION }
			locationText.value = '获取位置失败，当前使用默认位置'

			if (mapInstance) drawCurrentMarker(currentLocation.value.lng, currentLocation.value.lat, centerMap)
			if (showToast) uni.showToast({ title: '定位失败，使用默认位置', icon: 'none' })
			return currentLocation.value
		}
	}
}

const updateCurrentCity = async () => {
	try {
		const res = await reverseGeocode(currentLocation.value.lat, currentLocation.value.lng)
		const city = res?.data?.addressComponent?.city || ''
		currentCity.value = city
		return city
	} catch (err) {
		console.error('获取当前城市失败：', err)
		currentCity.value = ''
		return ''
	}
}

// ======================== 语音 & 导航追踪（保持原逻辑） ========================

const speakText = (text) => {
	const content = sanitizeInstruction(text)
	if (!content || !voiceBroadcastEnabled.value) return

	// #ifdef H5
	try {
		if (window.speechSynthesis) {
			window.speechSynthesis.cancel()
			const utter = new SpeechSynthesisUtterance(content)
			utter.lang = 'zh-CN'
			window.speechSynthesis.speak(utter)
			return
		}
	} catch (err) {
		console.warn('浏览器语音播报失败：', err)
	}
	// #endif

	uni.showToast({ title: content, icon: 'none', duration: 2000 })
}

// ======================== 语音识别 ========================

const voiceListening = ref(false)
const voiceFeedback = ref('')
let voiceFeedbackTimer = null
let recognizerInstance = null

const showVoiceFeedback = (msg, duration = 2500) => {
	voiceFeedback.value = msg
	clearTimeout(voiceFeedbackTimer)
	voiceFeedbackTimer = setTimeout(() => { voiceFeedback.value = '' }, duration)
}

// 规则匹配 → 结构化指令
const parseVoiceCommand = (text) => {
	const t = text.trim()

	// 帮助
	if (/帮助|怎么用|能做什么/.test(t)) return { action: 'help' }

	// 放大
	if (/放大|拉近/.test(t)) return { action: 'zoomIn' }

	// 缩小
	if (/缩小|拉远/.test(t)) return { action: 'zoomOut' }

	// 当前位置 / 我在哪
	if (/我在哪|当前位置|回到起点|重新定位/.test(t)) return { action: 'locate' }

	// 清除路线
	if (/清除|取消|结束/.test(t) && /路线|导航/.test(t)) return { action: 'clearRoute' }
	if (/^清除$|^取消导航$|^结束导航$/.test(t)) return { action: 'clearRoute' }

	// 导航到 / 前往 / 去
	const navMatch = t.match(/(?:导航到|导航至|前往|去往?|带我去|去一下)\s*(.+)/)
	if (navMatch) return { action: 'navigate', keyword: navMatch[1].trim() }

	// 搜索 / 查找 / 找
	const searchMatch = t.match(/(?:搜索|查找|查一下|找(?:一下)?|搜一下)\s*(.+)/)
	if (searchMatch) return { action: 'search', keyword: searchMatch[1].trim() }

	// 兜底：2~15字视为搜索关键词
	if (t.length >= 2 && t.length <= 15) return { action: 'search', keyword: t }

	return { action: 'unknown', raw: t }
}

const executeVoiceCommand = async (cmd) => {
	switch (cmd.action) {
		case 'zoomIn':
			if (mapInstance) mapInstance.zoomIn()
			showVoiceFeedback('🔍 已放大')
			break

		case 'zoomOut':
			if (mapInstance) mapInstance.zoomOut()
			showVoiceFeedback('🔍 已缩小')
			break

		case 'locate':
			showVoiceFeedback('📍 正在重新定位...')
			await handleLocate()
			break

		case 'clearRoute':
			resetRouteState()
			showVoiceFeedback('🗑 已清除路线')
			break

		case 'navigate':
		case 'search':
			searchKeyword.value = cmd.keyword
			showVoiceFeedback(
				cmd.action === 'navigate' ? `🗺 导航到：${cmd.keyword}` : `🔍 搜索：${cmd.keyword}`,
				3000
			)
			await handleSearch(cmd.action === 'navigate')
			break

		case 'help':
			uni.showToast({
				title: '可说：搜索XX / 导航到XX / 放大 / 缩小 / 清除路线 / 当前位置',
				icon: 'none',
				duration: 4000
			})
			break

		default:
			showVoiceFeedback(`🤔 未识别：${cmd.raw || ''}`)
	}
}

const handleManualVoice = () => {
	// #ifdef H5
	const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
	if (!SpeechRecognition) {
		uni.showToast({ title: '当前浏览器不支持语音识别', icon: 'none' })
		return
	}

	// 点击时如果正在录音则停止
	if (voiceListening.value) {
		if (recognizerInstance) recognizerInstance.stop()
		voiceListening.value = false
		voiceFeedback.value = ''
		return
	}

	const recognizer = new SpeechRecognition()
	recognizerInstance = recognizer
	recognizer.lang = 'zh-CN'
	recognizer.continuous = false
	recognizer.interimResults = false
	recognizer.maxAlternatives = 1

	recognizer.onstart = () => {
		voiceListening.value = true
		showVoiceFeedback('🎙 请说话...', 8000)
	}

	recognizer.onresult = (e) => {
		const text = e.results[0][0].transcript
		showVoiceFeedback(`识别：${text}`, 1500)
		setTimeout(() => executeVoiceCommand(parseVoiceCommand(text)), 400)
	}

	recognizer.onerror = (e) => {
		const errMap = { 'no-speech': '没有检测到语音', 'not-allowed': '麦克风权限被拒绝', 'network': '网络错误' }
		showVoiceFeedback(`⚠️ ${errMap[e.error] || e.error}`)
	}

	recognizer.onend = () => {
		voiceListening.value = false
		recognizerInstance = null
	}

	try {
		recognizer.start()
	} catch (err) {
		uni.showToast({ title: '语音启动失败', icon: 'none' })
		voiceListening.value = false
	}
	// #endif
	// #ifndef H5
	uni.showToast({ title: '语音识别仅支持 H5 端', icon: 'none' })
	// #endif
}

const updateCurrentStepByLocation = () => {
	if (!routeReady.value || !routeSteps.value.length) return

	const lat = currentLocation.value.lat
	const lng = currentLocation.value.lng

	let bestIndex = currentStepIndex.value
	let bestDistance = Number.POSITIVE_INFINITY

	routeSteps.value.forEach((step, index) => {
		if (!step.endPoint) return
		const d = haversineDistance(lat, lng, step.endPoint.lat, step.endPoint.lng)
		if (d < bestDistance) {
			bestDistance = d
			bestIndex = index
		}
	})

	if (bestIndex < currentStepIndex.value) bestIndex = currentStepIndex.value

	currentStepIndex.value = bestIndex
	currentStepRemain.value = bestDistance === Number.POSITIVE_INFINITY ? 0 : bestDistance

	if (currentStep.value?.points?.length > 1) drawActiveStepOnMap(currentStep.value.points)

	if (lastSpokenStepIndex !== currentStepIndex.value) {
		lastSpokenStepIndex = currentStepIndex.value
		speakText(currentStep.value.instruction)
	}

	if (bestDistance <= 18 && currentStepIndex.value < routeSteps.value.length - 1) {
		currentStepIndex.value += 1
		currentStepRemain.value = routeSteps.value[currentStepIndex.value]?.distance || 0

		if (currentStep.value?.points?.length > 1) drawActiveStepOnMap(currentStep.value.points)

		if (lastSpokenStepIndex !== currentStepIndex.value) {
			lastSpokenStepIndex = currentStepIndex.value
			speakText(currentStep.value.instruction)
		}
	}

	if (currentStepIndex.value >= routeSteps.value.length - 1 && bestDistance <= 15) {
		locationText.value = '已接近目的地'
	}
}

const startNavigationWatcher = () => {
	stopNavigationWatcher()
	locationTimer = setInterval(async () => {
		if (!routeReady.value) return
		try {
			await getCurrentLocation(false, true)
			updateCurrentStepByLocation()
			updateMapFollow()
		} catch (err) {
			console.warn('导航定位更新失败：', err)
		}
	}, 5000)
}

const stopNavigationWatcher = () => {
	if (locationTimer) {
		clearInterval(locationTimer)
		locationTimer = null
	}
}

const resetRouteState = () => {
	routeReady.value = false
	routeData.value = {
		destination: '', walking: '', description: '', address: '',
		distance: 0, duration: 0, polylinePoints: []
	}
	routeSteps.value = []
	currentStepIndex.value = 0
	currentStepRemain.value = 0
	lastSpokenStepIndex = -1
	selectedDestination.value = { lat: '', lng: '' }
	clearRouteOverlays()
	stopNavigationWatcher()
}

// ======================== 搜索 & 路线规划（接口兼容，逻辑不变） ========================

const handleSearch = async (autoPickFirst = false) => {
	try {
		uni.showLoading({ title: '搜索中...' })
		showPlaceList.value = false
		placeList.value = []
		resetRouteState()

		await getCurrentLocation(false, true)
		await updateCurrentCity()

		const keyword = (searchKeyword.value || '医院').trim()
		const region = currentCity.value || '全国'

		const res = await searchPlace(keyword, region)
		const resultList = res?.data?.results || []

		if (!resultList.length) {
			uni.showToast({ title: '未找到结果', icon: 'none' })
			return
		}

		placeList.value = resultList

		if (autoPickFirst) {
			await handleSelectPlace(resultList[0])
			return
		}

		if (resultList.length === 1) {
			await handleSelectPlace(resultList[0])
			return
		}

		showPlaceList.value = true
		uni.showToast({ title: '请选择目的地', icon: 'none' })
	} catch (err) {
		console.error('搜索失败详情：', err)
		uni.showToast({ title: '搜索失败', icon: 'none' })
	} finally {
		uni.hideLoading()
	}
}

const handleSelectPlace = async (place) => {
	try {
		uni.showLoading({ title: '规划路线...' })
		showPlaceList.value = false

		routeData.value.destination = place.name || '搜索结果'
		routeData.value.address = place.address || ''

		selectedDestination.value = {
			lat: place.location.lat,
			lng: place.location.lng
		}

		const origin = `${currentLocation.value.lat},${currentLocation.value.lng}`
		const destination = `${place.location.lat},${place.location.lng}`

		const routeRes = await getWalkRoute(origin, destination)
		const route = routeRes?.data?.result?.routes?.[0]

		if (!route) {
			uni.showToast({ title: '路线获取失败', icon: 'none' })
			return
		}

		const minutes = Math.max(1, Math.ceil((route.duration || 0) / 60))
		const polylinePoints = parseWholeRoutePoints(route)
		const steps = normalizeRouteSteps(route)

		routeData.value.walking = `步行 ${minutes} 分钟`
		routeData.value.distance = Number(route.distance || 0)
		routeData.value.duration = Number(route.duration || 0)
		routeData.value.description = `全程约 ${formatDistance(route.distance || 0)} · 推荐更平稳步行路线`
		routeData.value.polylinePoints =
			polylinePoints.length > 1
				? polylinePoints
				: [
					{ lat: currentLocation.value.lat, lng: currentLocation.value.lng },
					{ lat: place.location.lat, lng: place.location.lng }
				]

		routeSteps.value = steps
		currentStepIndex.value = 0
		currentStepRemain.value = steps[0]?.distance || 0
		lastSpokenStepIndex = -1
		routeReady.value = true

		drawCurrentMarker(currentLocation.value.lng, currentLocation.value.lat, true)
		drawDestinationMarker(place.location.lng, place.location.lat, place.name)
		drawWholeRouteOnMap(routeData.value.polylinePoints)

		if (steps[0]?.points?.length > 1) drawActiveStepOnMap(steps[0].points)

		updateCurrentStepByLocation()
		startNavigationWatcher()

		uni.showToast({ title: '路线已更新', icon: 'none' })
	} catch (err) {
		console.error('路线规划失败详情：', err)
		uni.showToast({ title: '路线规划失败', icon: 'none' })
	} finally {
		uni.hideLoading()
	}
}

const handleLocate = async () => {
	await getCurrentLocation(true, true)
	await updateCurrentCity()
	if (routeReady.value) updateCurrentStepByLocation()
}

const handleTabClick = (type) => {
	const currentPath = '/pages/navigation/navigation'
	const routes = {
		home: '/pages/home/home',
		navigation: '/pages/navigation/navigation',
		device: '/pages/device/device',
		diagnostic: '/pages/diagnostic/diagnostic'
	}
	const target = routes[type]
	if (!target || target === currentPath) return
	uni.reLaunch({ url: target })
}

const onSearchConfirm = async () => {
	await handleSearch(false)
}

// ======================== 生命周期 ========================

onLoad((options) => {
	if (options && options.keyword) {
		searchKeyword.value = decodeURIComponent(options.keyword)
	}

	const localVoiceSwitch = uni.getStorageSync('voiceBroadcastEnabled')
	if (typeof localVoiceSwitch === 'boolean') {
		voiceBroadcastEnabled.value = localVoiceSwitch
	}

	if (options && options.assistantPlace) {
		try {
			const key = getAssistantSelectedPlaceKey()
			pendingAssistantPlace = uni.getStorageSync(key) || null
			uni.removeStorageSync(key)
		} catch (err) {
			console.warn('读取助手选中地点失败：', err)
			pendingAssistantPlace = null
		}
	}
})

onReady(async () => {
	// #ifdef H5
	try {
		await nextTick()
		await getCurrentLocation(false, true)
		await nextTick()
		await initMap()
		await updateCurrentCity()

		if (pendingAssistantPlace) {
			await handleSelectPlace(pendingAssistantPlace)
			pendingAssistantPlace = null
			return
		}

		if (searchKeyword.value) {
			await handleSearch(true)
		}
	} catch (err) {
		console.error('地图初始化失败：', err)
		locationText.value = '地图初始化失败，请检查高德地图配置'
	}
	// #endif
	// #ifndef H5
	locationText.value = '请在浏览器端使用地图功能'
	// #endif
})

onBeforeUnmount(() => {
	stopNavigationWatcher()
	clearTimeout(voiceFeedbackTimer)
	if (recognizerInstance) { try { recognizerInstance.stop() } catch(e) {} recognizerInstance = null }
	if (mapInstance) {
		mapInstance.destroy()
	}
	mapInstance = null
	currentMarker = null
	destinationMarker = null
	destinationLabel = null
	routePolyline = null
	activeStepPolyline = null
})
</script>

<style scoped>
.container {
	position: relative;
	width: 100%;
	height: 100vh;
	max-width: 750rpx;
	margin: 0 auto;
	background: #f5f6f8;
	overflow: hidden;
}

.map-layer {
	position: absolute;
	top: 0;
	left: 0;
	right: 0;
	bottom: 120rpx;
	z-index: 1;
	background: #e9eef3;
}

.amap-box {
	width: 100%;
	height: 100%;
}

.search-bar {
	position: absolute;
	top: 48rpx;
	left: 24rpx;
	right: 24rpx;
	z-index: 100;
	display: flex;
	align-items: center;
	background: rgba(255,255,255,0.98);
	border-radius: 48rpx;
	padding: 18rpx 20rpx;
	box-shadow: 0 4rpx 20rpx rgba(26,58,82,0.12);
	gap: 12rpx;
}

.search-icon {
	font-size: 32rpx;
	line-height: 32rpx;
	flex-shrink: 0;
}

.search-input {
	flex: 1;
	height: 56rpx;
	font-size: 26rpx;
	color: #1a3a52;
	background: transparent;
	min-width: 0;
}

.search-input-placeholder {
	color: #aab5c0;
	font-size: 24rpx;
}

.search-btn {
	padding: 10rpx 18rpx;
	background: #e3f2fd;
	border-radius: 24rpx;
	display: flex;
	align-items: center;
	justify-content: center;
	flex-shrink: 0;
}

.search-btn-text {
	font-size: 22rpx;
	color: #1565c0;
	font-weight: 600;
}

.mic-btn {
	width: 72rpx;
	height: 72rpx;
	border-radius: 36rpx;
	background: linear-gradient(135deg, #2196f3 0%, #1976d2 100%);
	display: flex;
	align-items: center;
	justify-content: center;
	box-shadow: 0 4rpx 12rpx rgba(33,150,243,0.35);
	flex-shrink: 0;
	transition: background 0.2s, box-shadow 0.2s;
}

.mic-btn.mic-listening {
	background: linear-gradient(135deg, #e53935 0%, #c62828 100%);
	box-shadow: 0 0 0 6rpx rgba(229,57,53,0.20), 0 4rpx 12rpx rgba(229,57,53,0.40);
	animation: micPulse 1.1s ease-in-out infinite;
}

@keyframes micPulse {
	0%, 100% { box-shadow: 0 0 0 6rpx rgba(229,57,53,0.20), 0 4rpx 12rpx rgba(229,57,53,0.40); }
	50%       { box-shadow: 0 0 0 14rpx rgba(229,57,53,0.08), 0 4rpx 12rpx rgba(229,57,53,0.40); }
}

.voice-feedback {
	position: absolute;
	left: 50%;
	bottom: 180rpx;
	transform: translateX(-50%);
	z-index: 160;
	background: rgba(20,20,30,0.80);
	border-radius: 40rpx;
	padding: 14rpx 28rpx;
	max-width: 80vw;
	pointer-events: none;
}

.voice-feedback-text {
	font-size: 24rpx;
	color: #fff;
	white-space: nowrap;
	overflow: hidden;
	text-overflow: ellipsis;
}

.mic-icon {
	font-size: 32rpx;
	line-height: 32rpx;
}

.locate-btn {
	position: absolute;
	top: 154rpx;
	right: 12rpx;
	z-index: 150;
	width: 84rpx;
	height: 84rpx;
	border-radius: 42rpx;
	background: rgba(255,255,255,0.98);
	display: flex;
	align-items: center;
	justify-content: center;
	box-shadow: 0 4rpx 16rpx rgba(26,58,82,0.15);
}

.locate-icon {
	font-size: 40rpx;
	line-height: 40rpx;
}

.place-list {
	position: absolute;
	left: 24rpx;
	right: 24rpx;
	top: 170rpx;
	z-index: 180;
	background: rgba(255,255,255,0.98);
	border-radius: 24rpx;
	box-shadow: 0 8rpx 28rpx rgba(26,58,82,0.14);
	overflow: hidden;
}

.place-list-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 22rpx 24rpx 18rpx;
	border-bottom: 1rpx solid #eef2f5;
}

.place-list-title {
	font-size: 28rpx;
	font-weight: 700;
	color: #1a3a52;
}

.place-list-close {
	font-size: 24rpx;
	color: #2196f3;
}

.place-scroll {
	max-height: 480rpx;
}

.place-item {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 22rpx 24rpx;
	border-bottom: 1rpx solid #f2f4f7;
}

.place-item:last-child {
	border-bottom: none;
}

.place-item-left {
	flex: 1;
	padding-right: 20rpx;
}

.place-item-name {
	display: block;
	font-size: 28rpx;
	font-weight: 700;
	color: #1a3a52;
}

.place-item-address {
	display: block;
	margin-top: 8rpx;
	font-size: 22rpx;
	color: #8a9bb0;
	line-height: 1.5;
}

.place-item-arrow {
	font-size: 34rpx;
	color: #c7d0d8;
}

.map-status {
	position: absolute;
	left: 24rpx;
	right: 24rpx;
	top: 262rpx;
	z-index: 120;
	display: flex;
	justify-content: center;
}

.map-status-text {
	padding: 10rpx 16rpx;
	background: rgba(255,255,255,0.88);
	border-radius: 20rpx;
	font-size: 22rpx;
	color: #60788f;
	max-width: 620rpx;
	text-align: center;
}

.nav-card {
	position: absolute;
	left: 24rpx;
	right: 24rpx;
	bottom: 144rpx;
	z-index: 130;
	background: rgba(255,255,255,0.98);
	border-radius: 28rpx;
	box-shadow: 0 10rpx 36rpx rgba(26,58,82,0.16);
	padding: 28rpx 24rpx;
	max-height: calc(50vh - 40rpx);
	overflow: hidden;
	box-sizing: border-box;
}

.card-top {
	display: block;
}

.title-row {
	display: flex;
	align-items: center;
	gap: 12rpx;
	flex-wrap: wrap;
}

.destination-title {
	font-size: 30rpx;
	font-weight: 700;
	color: #17324d;
	line-height: 1.4;
	flex: 1;
	min-width: 0;
}

.ai-tag {
	background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
	border-radius: 999rpx;
	padding: 6rpx 14rpx;
	flex-shrink: 0;
}

.ai-tag-text {
	font-size: 20rpx;
	color: #1565c0;
	font-weight: 600;
}

.route-time {
	display: block;
	margin-top: 12rpx;
	font-size: 26rpx;
	color: #2196f3;
	font-weight: 700;
}

.route-desc {
	display: block;
	margin-top: 8rpx;
	font-size: 22rpx;
	color: #8093a7;
	line-height: 1.5;
}

.route-address {
	display: block;
	margin-top: 8rpx;
	font-size: 20rpx;
	color: #a0acb8;
	line-height: 1.5;
}

.divider {
	height: 1rpx;
	background: #edf2f6;
	margin: 22rpx 0;
}

.current-step-box {
	display: block;
}

.step-label {
	display: block;
	font-size: 22rpx;
	color: #1976d2;
	font-weight: 700;
}

.step-instruction {
	display: block;
	margin-top: 14rpx;
	font-size: 30rpx;
	font-weight: 700;
	color: #17324d;
	line-height: 1.5;
	display: -webkit-box;
	-webkit-line-clamp: 3;
	-webkit-box-orient: vertical;
	overflow: hidden;
}

.step-meta {
	display: flex;
	align-items: center;
	flex-wrap: wrap;
	gap: 8rpx;
	margin-top: 14rpx;
}

.step-meta-item {
	font-size: 22rpx;
	color: #7e91a4;
}

.step-meta-dot {
	font-size: 22rpx;
	color: #c0cad3;
}

.next-step {
	display: block;
	margin-top: 14rpx;
	font-size: 22rpx;
	color: #95a5b5;
	line-height: 1.5;
	display: -webkit-box;
	-webkit-line-clamp: 2;
	-webkit-box-orient: vertical;
	overflow: hidden;
}

.empty-card {
	position: absolute;
	left: 24rpx;
	right: 24rpx;
	bottom: 144rpx;
	z-index: 130;
	background: rgba(255,255,255,0.95);
	border-radius: 28rpx;
	padding: 32rpx 28rpx;
	box-shadow: 0 10rpx 36rpx rgba(26,58,82,0.14);
}

.empty-title {
	display: block;
	font-size: 30rpx;
	font-weight: 700;
	color: #17324d;
}

.empty-desc {
	display: block;
	margin-top: 10rpx;
	font-size: 22rpx;
	color: #8a9bb0;
	line-height: 1.6;
}

.tabbar {
	position: absolute;
	left: 0;
	right: 0;
	bottom: 0;
	height: 120rpx;
	background: rgba(255,255,255,0.98);
	display: flex;
	justify-content: space-around;
	align-items: center;
	box-shadow: 0 -2rpx 16rpx rgba(26,58,82,0.08);
	border-top: 1rpx solid #f0f0f0;
	z-index: 200;
}

.tab-item {
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	gap: 6rpx;
	flex: 1;
	height: 100%;
}

.tab-icon {
	font-size: 36rpx;
	line-height: 36rpx;
	color: #9e9e9e;
}

.tab-item.active .tab-icon {
	color: #2196f3;
	font-size: 40rpx;
}

.tab-label {
	font-size: 20rpx;
	font-weight: 500;
	color: #9e9e9e;
}

.tab-item.active .tab-label {
	color: #2196f3;
	font-weight: 600;
}
</style>
