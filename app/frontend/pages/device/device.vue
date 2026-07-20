<template>
	<view class="container">
		<!-- 顶部导航 -->
		<view class="navbar">
			<view class="navbar-back" @click="handleTabClick('home')">
				<text class="back-arrow">‹</text>
			</view>
			<text class="navbar-title">设备</text>
		</view>

		<!-- 主内容区 -->
		<view class="main-content">
			<!-- 未连接状态 -->
			<template v-if="!isConnected">
				<view class="device-illustration">
					<view class="device-circle">
						<text class="device-main-icon">🦯</text>
						<view class="disconnect-badge">
							<text class="badge-icon">✕</text>
						</view>
					</view>
				</view>

				<text class="main-title">设备未连接</text>
				<text class="sub-title">请先连接您的智能设备</text>

				<button class="primary-btn" @click="connectDevice" :disabled="isBusy">
					<text class="primary-btn-text">{{ isBusy ? '连接中...' : '连接设备' }}</text>
				</button>

				<view class="text-btn" @click="refreshDevice">
					<text class="text-btn-icon">↻</text>
					<text class="text-btn-label">刷新</text>
				</view>
			</template>

			<!-- 已连接状态 -->
			<template v-else>
				<view class="device-illustration">
					<view class="device-circle connected">
						<text class="device-main-icon">🦯</text>
						<view class="connect-badge">
							<text class="badge-icon">✓</text>
						</view>
					</view>
				</view>

				<text class="main-title">设备已连接</text>
				<text class="sub-title">设备运行正常</text>

				<view class="device-status-card">
					<view class="status-row">
						<text class="status-label">设备名称</text>
						<text class="status-value">{{ deviceName }}</text>
					</view>
					<view class="status-row">
						<text class="status-label">连接状态</text>
						<text class="status-value success">已连接</text>
					</view>
					<view class="status-row">
						<text class="status-label">电池电量</text>
						<text class="status-value">{{ batteryLevel }}%</text>
					</view>
					<view class="status-row">
						<text class="status-label">蓝牙信号</text>
						<text class="status-value">{{ bleSignal }} dBm</text>
					</view>
					<view class="status-row">
						<text class="status-label">设备状态</text>
						<text class="status-value" :class="deviceStatusColorClass">{{ deviceStatusText }}</text>
					</view>
				</view>

				<button class="primary-btn" @click="detectDevice" :disabled="isBusy">
					<text class="primary-btn-text">{{ isBusy ? '处理中...' : '设备检测' }}</text>
				</button>

				<view class="action-row">
					<view class="text-btn" @click="reconnectDevice">
						<text class="text-btn-icon">⟳</text>
						<text class="text-btn-label">重新连接</text>
					</view>

					<view class="text-btn" @click="queryBattery">
						<text class="text-btn-icon">🔋</text>
						<text class="text-btn-label">查询电量</text>
					</view>

					<view class="text-btn danger-btn" @click="disconnectDevice">
						<text class="text-btn-icon">⨯</text>
						<text class="text-btn-label danger-text">断开设备</text>
					</view>
				</view>
			</template>
		</view>

		<!-- 底部 TabBar -->
		<view class="tabbar">
			<view class="tab-item" @click="handleTabClick('home')">
				<text class="tab-icon">🚶</text>
				<text class="tab-label">出行</text>
			</view>
			<view class="tab-item" @click="handleTabClick('navigation')">
				<text class="tab-icon">🧭️</text>
				<text class="tab-label">导航</text>
			</view>
			<view class="tab-item active" @click="handleTabClick('device')">
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
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { registerDeviceHandlers, unregisterDeviceHandlers } from '@/utils/deviceBridge.js'

const isConnected = ref(false)
const isBusy = ref(false)
const batteryLevel = ref(78)
const bleSignal = ref(-72)
const deviceName = ref('灵触·随行智能盲杖')

const autoConnect = ref(false)
const autoDisconnect = ref(false)

const wait = (ms) => new Promise(resolve => setTimeout(resolve, ms))

const deviceStatusText = computed(() => {
	if (!isConnected.value) return '未连接'
	if (batteryLevel.value < 20) return '低电量'
	if (bleSignal.value < -85) return '信号较弱'
	return '正常'
})

const deviceStatusColorClass = computed(() => {
	if (!isConnected.value) return 'danger'
	if (batteryLevel.value < 20 || bleSignal.value < -85) return 'warning'
	return 'success'
})

const buildDeviceStatusResult = () => {
	const abnormalItems = []

	if (!isConnected.value) abnormalItems.push('设备未连接')
	if (batteryLevel.value < 20) abnormalItems.push('电池电量偏低')
	if (bleSignal.value < -85) abnormalItems.push('蓝牙信号偏弱')

	return {
		isNormal: abnormalItems.length === 0,
		abnormalItems,
		summary: abnormalItems.length === 0 ? '设备状态正常' : `发现 ${abnormalItems.length} 项异常`,
		batteryLevel: batteryLevel.value,
		bleSignal: bleSignal.value,
		isConnected: isConnected.value,
		deviceName: deviceName.value
	}
}

const connectDevice = async () => {
	if (isBusy.value) {
		return {
			success: false,
			message: '当前正在处理，请稍候'
		}
	}

	isBusy.value = true
	try {
		uni.showLoading({
			title: '连接中...'
		})

		// TODO: 替换成真实蓝牙连接逻辑
		await wait(1200)

		isConnected.value = true
		bleSignal.value = -72
		batteryLevel.value = 78

		uni.showToast({
			title: '设备连接成功',
			icon: 'none'
		})

		return {
			success: true,
			message: '设备连接成功'
		}
	} catch (err) {
		console.error('connectDevice failed:', err)
		uni.showToast({
			title: '设备连接失败',
			icon: 'none'
		})
		return {
			success: false,
			message: err?.message || '设备连接失败'
		}
	} finally {
		isBusy.value = false
		uni.hideLoading()
	}
}

const disconnectDevice = async () => {
	if (isBusy.value) {
		return {
			success: false,
			message: '当前正在处理，请稍候'
		}
	}

	isBusy.value = true
	try {
		uni.showLoading({
			title: '断开中...'
		})

		// TODO: 替换成真实蓝牙断开逻辑
		await wait(700)

		isConnected.value = false

		uni.showToast({
			title: '设备已断开',
			icon: 'none'
		})

		return {
			success: true,
			message: '设备已断开'
		}
	} catch (err) {
		console.error('disconnectDevice failed:', err)
		uni.showToast({
			title: '断开失败',
			icon: 'none'
		})
		return {
			success: false,
			message: err?.message || '设备断开失败'
		}
	} finally {
		isBusy.value = false
		uni.hideLoading()
	}
}

const reconnectDevice = async () => {
	if (isBusy.value) return

	await disconnectDevice()
	await wait(500)
	await connectDevice()
}

const detectDevice = async () => {
	if (isBusy.value) {
		return {
			success: false,
			message: '当前正在处理，请稍候'
		}
	}

	uni.reLaunch({
		url: '/pages/diagnostic/diagnostic?autoStart=1'
	})

	return {
		success: true,
		message: '正在打开设备检测'
	}
}

const getBatteryStatus = async () => {
	const message = isConnected.value
		? `当前设备电量为${batteryLevel.value}%`
		: '当前设备未连接，无法读取电量'

	if (isConnected.value) {
		uni.showToast({
			title: `电量 ${batteryLevel.value}%`,
			icon: 'none'
		})
	}

	return {
		success: isConnected.value,
		message,
		batteryLevel: batteryLevel.value
	}
}

const getDeviceStatus = async () => {
	return buildDeviceStatusResult()
}

const queryBattery = async () => {
	await getBatteryStatus()
}

const refreshDevice = async () => {
	uni.showToast({
		title: '刷新中',
		icon: 'none'
	})

	await wait(400)

	if (isConnected.value) {
		batteryLevel.value = Math.max(15, Math.min(100, batteryLevel.value))
	}
}

const registerAssistantBridge = () => {
	registerDeviceHandlers({
		connect: async () => {
			return await connectDevice()
		},
		disconnect: async () => {
			return await disconnectDevice()
		},
		diagnostic: async () => {
			return await detectDevice()
		},
		getBatteryStatus: async () => {
			return await getBatteryStatus()
		},
		getDeviceStatus: async () => {
			return await getDeviceStatus()
		}
	})
}

const handleTabClick = (type) => {
	const currentPath = '/pages/device/device'
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

onLoad(async (options) => {
	if (options?.autoConnect === '1') {
		autoConnect.value = true
	}

	if (options?.autoDisconnect === '1') {
		autoDisconnect.value = true
	}
})

onMounted(async () => {
	registerAssistantBridge()

	if (autoDisconnect.value) {
		await disconnectDevice()
		return
	}

	if (autoConnect.value) {
		await connectDevice()
	}
})

onBeforeUnmount(() => {
	unregisterDeviceHandlers()
})
</script>

<style scoped>
.container {
	display: flex;
	flex-direction: column;
	min-height: 100vh;
	background: #f5f6f8;
	max-width: 750rpx;
	margin: 0 auto;
	position: relative;
}

.navbar {
	display: flex;
	flex-direction: row;
	align-items: center;
	padding: 48rpx 24rpx 24rpx 24rpx;
	background: #ffffff;
	border-bottom: 1rpx solid #f0f0f0;
}

.navbar-back {
	width: 64rpx;
	height: 64rpx;
	display: flex;
	align-items: center;
	justify-content: center;
	border-radius: 12rpx;
	background: #f5f6f8;
	margin-right: 16rpx;
	transition: all 0.2s ease;
}

.navbar-back:active {
	background: #e8eaed;
}

.back-arrow {
	font-size: 48rpx;
	color: #1a3a52;
	line-height: 48rpx;
	font-weight: 300;
}

.navbar-title {
	font-size: 34rpx;
	font-weight: 700;
	color: #1a3a52;
	letter-spacing: 1rpx;
}

.main-content {
	flex: 1;
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	padding: 60rpx 48rpx 160rpx 48rpx;
	min-height: 900rpx;
}

.device-illustration {
	margin-bottom: 48rpx;
}

.device-circle {
	width: 240rpx;
	height: 240rpx;
	border-radius: 120rpx;
	background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
	display: flex;
	align-items: center;
	justify-content: center;
	position: relative;
	box-shadow: 0 8rpx 32rpx rgba(33, 150, 243, 0.12);
	transition: background 0.4s ease, box-shadow 0.4s ease;
}

.device-circle.connected {
	background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
	box-shadow: 0 8rpx 32rpx rgba(76, 175, 80, 0.15);
}

.device-main-icon {
	font-size: 96rpx;
	line-height: 96rpx;
}

.disconnect-badge,
.connect-badge {
	position: absolute;
	bottom: 12rpx;
	right: 12rpx;
	width: 56rpx;
	height: 56rpx;
	border-radius: 28rpx;
	display: flex;
	align-items: center;
	justify-content: center;
	border: 4rpx solid #ffffff;
}

.disconnect-badge {
	background: #ff5252;
	box-shadow: 0 2rpx 8rpx rgba(255, 82, 82, 0.35);
}

.connect-badge {
	background: #4caf50;
	box-shadow: 0 2rpx 8rpx rgba(76, 175, 80, 0.35);
}

.badge-icon {
	font-size: 24rpx;
	color: #ffffff;
	font-weight: 700;
	line-height: 24rpx;
}

.main-title {
	font-size: 44rpx;
	font-weight: 700;
	color: #1a3a52;
	text-align: center;
	letter-spacing: 1rpx;
	margin-bottom: 16rpx;
	display: block;
}

.sub-title {
	font-size: 28rpx;
	color: #8a9bb0;
	text-align: center;
	margin-bottom: 48rpx;
	display: block;
	line-height: 1.6;
}

.device-status-card {
	width: 560rpx;
	background: #ffffff;
	border-radius: 20rpx;
	padding: 24rpx;
	box-shadow: 0 2rpx 10rpx rgba(26,58,82,0.07);
	margin-bottom: 40rpx;
}

.status-row {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 12rpx 0;
	border-bottom: 1rpx solid #f0f0f0;
}

.status-row:last-child {
	border-bottom: none;
}

.status-label {
	font-size: 24rpx;
	color: #8a9bb0;
}

.status-value {
	font-size: 24rpx;
	color: #1a3a52;
	font-weight: 600;
}

.status-value.success {
	color: #2e7d32;
}

.status-value.warning {
	color: #e65100;
}

.status-value.danger {
	color: #d32f2f;
}

.primary-btn {
	width: 560rpx;
	height: 96rpx;
	background: linear-gradient(135deg, #2196f3 0%, #1976d2 100%);
	border-radius: 48rpx;
	border: none;
	display: flex;
	align-items: center;
	justify-content: center;
	box-shadow: 0 8rpx 24rpx rgba(33, 150, 243, 0.35);
	transition: all 0.3s ease;
	margin-bottom: 32rpx;
}

.primary-btn:active {
	transform: scale(0.97);
	box-shadow: 0 4rpx 12rpx rgba(33, 150, 243, 0.2);
}

.primary-btn[disabled] {
	opacity: 0.65;
}

.primary-btn-text {
	font-size: 32rpx;
	color: #ffffff;
	font-weight: 600;
	letter-spacing: 2rpx;
}

.action-row {
	display: flex;
	flex-wrap: wrap;
	flex-direction: row;
	align-items: center;
	justify-content: center;
	gap: 24rpx;
}

.text-btn {
	display: flex;
	flex-direction: row;
	align-items: center;
	justify-content: center;
	gap: 8rpx;
	padding: 16rpx 28rpx;
	transition: opacity 0.2s ease;
}

.text-btn:active {
	opacity: 0.5;
}

.text-btn-icon {
	font-size: 26rpx;
	color: #64b5f6;
	line-height: 26rpx;
}

.text-btn-label {
	font-size: 26rpx;
	color: #64b5f6;
	font-weight: 500;
	letter-spacing: 1rpx;
}

.danger-text {
	color: #f44336;
}

.tabbar {
	position: fixed;
	bottom: 0;
	left: 50%;
	transform: translateX(-50%);
	width: 750rpx;
	height: 120rpx;
	background: #ffffff;
	display: flex;
	flex-direction: row;
	justify-content: space-around;
	align-items: center;
	box-shadow: 0 -2rpx 16rpx rgba(26, 58, 82, 0.08);
	border-top: 1rpx solid #f0f0f0;
}

.tab-item {
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	gap: 6rpx;
	flex: 1;
	height: 100%;
	transition: all 0.2s ease;
}

.tab-item:active {
	background: #f8f9fa;
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