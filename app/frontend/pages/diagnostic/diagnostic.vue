<template>
	<view class="container">
		<!-- 顶部导航 -->
		<view class="navbar">
			<view class="navbar-back" @click="handleTabClick('device')">
				<text class="back-arrow">‹</text>
			</view>
			<text class="navbar-title">设备检测</text>
		</view>

		<!-- 可滚动主体 -->
		<scroll-view class="scroll-body" scroll-y="true">
			<!-- 1. 总状态卡 -->
			<view class="card status-card">
				<view class="status-top">
					<view class="status-left">
						<view class="ok-badge"><text class="ok-icon">✓</text></view>
						<view class="status-info">
							<text class="status-title">{{ detectStatusTitle }}</text>
							<text class="status-sub">{{ detectStatusSub }}</text>
						</view>
					</view>
					<view class="battery-info">
						<text class="battery-pct">{{ batteryLevel }}%</text>
						<text class="battery-ico">🔋</text>
					</view>
				</view>
				<view class="progress-bar-wrap">
					<view class="progress-bar-bg">
						<view class="progress-bar-fill" :style="`width:${batteryLevel}%`"></view>
					</view>
				</view>
				<view class="status-bottom">
					<text class="status-hint">{{ isChecking ? '正在检测设备状态' : '预计续航 5 小时' }}</text>
					<text class="status-ble">BLE -72dBm</text>
				</view>
			</view>

			<!-- 2. 实时数据卡 -->
			<view class="section-title">实时数据</view>
			<view class="grid2">
				<view class="metric-card">
					<text class="metric-name">刷新率</text>
					<text class="metric-value">{{ fps }}</text>
					<text class="metric-unit">FPS</text>
					<view class="metric-tag green"><text class="tag-text">达标</text></view>
				</view>
				<view class="metric-card">
					<text class="metric-name">延迟</text>
					<text class="metric-value">{{ latency }}</text>
					<text class="metric-unit">ms</text>
					<view class="metric-tag green"><text class="tag-text">正常</text></view>
				</view>
				<view class="metric-card">
					<text class="metric-name">BLE 信号</text>
					<text class="metric-value">{{ bleSignal }}</text>
					<text class="metric-unit">dBm</text>
					<view class="metric-tag blue"><text class="tag-text">良好</text></view>
				</view>
				<view class="metric-card">
					<text class="metric-name">电池电量</text>
					<text class="metric-value">{{ batteryLevel }}</text>
					<text class="metric-unit">%</text>
					<view class="metric-tag green"><text class="tag-text">正常</text></view>
				</view>
			</view>

			<!-- 3. 延迟明细卡 -->
			<view class="section-title">延迟明细</view>
			<view class="card">
				<view class="latency-row" v-for="(item, index) in latencyDetails" :key="index">
					<text class="latency-label">{{ item.label }}</text>
					<view class="latency-bar-bg">
						<view class="latency-bar" :style="`width:${item.value}%;background:${latencyBarColor(item.value)}`"></view>
					</view>
					<text class="latency-val">{{ item.value }}ms</text>
				</view>
				<view class="latency-total-row">
					<text class="latency-total-label">端到端总延迟</text>
					<text class="latency-total-val">{{ latency }}ms</text>
				</view>
			</view>

			<!-- 4. 硬件检测卡 -->
			<view class="section-title">硬件检测</view>
			<view class="card">
				<view class="hw-item">
					<view class="hw-header">
						<view class="hw-dot green"></view>
						<text class="hw-name">触觉阵列</text>
						<view class="hw-tag green"><text class="tag-text">正常</text></view>
					</view>
					<view class="hw-detail-row">
						<text class="hw-detail">阵列完整性 16/16</text>
						<text class="hw-detail">响应延迟 12ms</text>
					</view>
				</view>
				<view class="hw-divider"></view>
				<view class="hw-item">
					<view class="hw-header">
						<view class="hw-dot green"></view>
						<text class="hw-name">传感器</text>
						<view class="hw-tag green"><text class="tag-text">正常</text></view>
					</view>
					<view class="hw-detail-row">
						<text class="hw-detail">深度摄像头 正常</text>
						<text class="hw-detail">IMU 正常</text>
					</view>
				</view>
				<view class="hw-divider"></view>
				<view class="hw-item">
					<view class="hw-header">
						<view class="hw-dot green"></view>
						<text class="hw-name">控制模块</text>
						<view class="hw-tag green"><text class="tag-text">正常</text></view>
					</view>
					<view class="hw-detail-row">
						<text class="hw-detail">CPU 占用 35%</text>
						<text class="hw-detail">温度 42℃</text>
					</view>
				</view>
				<view class="hw-divider"></view>
				<view class="hw-item">
					<view class="hw-header">
						<view class="hw-dot green"></view>
						<text class="hw-name">电池健康</text>
						<view class="hw-tag yellow"><text class="tag-text">良好</text></view>
					</view>
					<view class="hw-detail-row">
						<text class="hw-detail">循环状态 正常</text>
					</view>
				</view>
			</view>

			<!-- 5. 通信检测卡 -->
			<view class="section-title">通信检测</view>
			<view class="card">
				<view class="comm-row">
					<text class="comm-label">BLE 信号</text>
					<text class="comm-value">{{ bleSignal }} dBm</text>
					<view class="hw-tag blue"><text class="tag-text">良好</text></view>
				</view>
				<view class="comm-row">
					<text class="comm-label">通信延迟</text>
					<text class="comm-value">95 ms</text>
					<view class="hw-tag green"><text class="tag-text">正常</text></view>
				</view>
				<view class="comm-row">
					<text class="comm-label">丢包率</text>
					<text class="comm-value">0.6%</text>
					<view class="hw-tag green"><text class="tag-text">正常</text></view>
				</view>
				<view class="comm-row">
					<text class="comm-label">连接稳定性</text>
					<text class="comm-value">—</text>
					<view class="hw-tag yellow"><text class="tag-text">良好</text></view>
				</view>
			</view>

			<!-- 6. 模块状态卡 -->
			<view class="section-title">模块状态</view>
			<view class="card">
				<view class="comm-row">
					<text class="comm-label">语音模块</text>
					<text class="comm-value">运行中</text>
					<view class="hw-tag green"><text class="tag-text">正常</text></view>
				</view>
				<view class="comm-row">
					<text class="comm-label">导航引导</text>
					<text class="comm-value">就绪</text>
					<view class="hw-tag green"><text class="tag-text">正常</text></view>
				</view>
				<view class="comm-row">
					<text class="comm-label">触觉反馈</text>
					<text class="comm-value">响应正常</text>
					<view class="hw-tag green"><text class="tag-text">正常</text></view>
				</view>
				<view class="comm-row">
					<text class="comm-label">系统状态</text>
					<text class="comm-value">稳定</text>
					<view class="hw-tag green"><text class="tag-text">稳定</text></view>
				</view>
			</view>

			<!-- 7. 风险提醒卡 -->
			<view class="section-title">风险提醒</view>
			<view class="card risk-card">
				<view class="risk-header">
					<view class="ok-badge small"><text class="ok-icon">✓</text></view>
					<text class="risk-all-ok">当前状态稳定，无异常报警</text>
				</view>
				<view class="risk-tips">
					<text class="risk-tip">· 延迟 > 150ms 时将提示“需关注”</text>
					<text class="risk-tip">· 电量 < 20% 时将提示“低电量风险”</text>
					<text class="risk-tip">· BLE < -85dBm 时将提示“信号较弱”</text>
				</view>
			</view>

			<!-- 8. 无障碍检查卡 -->
			<view class="section-title">无障碍检查</view>
			<view class="card">
				<view class="comm-row">
					<text class="comm-label">按钮尺寸</text>
					<text class="comm-value">48×48dp</text>
					<view class="hw-tag green"><text class="tag-text">达标</text></view>
				</view>
				<view class="comm-row">
					<text class="comm-label">文本对比度</text>
					<text class="comm-value">4.8:1</text>
					<view class="hw-tag green"><text class="tag-text">达标</text></view>
				</view>
				<view class="comm-row">
					<text class="comm-label">语音播报</text>
					<text class="comm-value">已启用</text>
					<view class="hw-tag green"><text class="tag-text">正常</text></view>
				</view>
				<view class="comm-row">
					<text class="comm-label">触控区域</text>
					<text class="comm-value">48×48dp</text>
					<view class="hw-tag green"><text class="tag-text">达标</text></view>
				</view>
			</view>

			<!-- 9. 重新检测按钮 -->
			<view class="bottom-action">
				<button class="recheck-btn" @click="recheck" :disabled="isChecking">
					<text class="recheck-btn-text">{{ isChecking ? '检测中...' : '重新检测' }}</text>
				</button>
			</view>

			<!-- 底部占位 -->
			<view style="height:140rpx"></view>
		</scroll-view>

		<!-- 10. 底部 TabBar -->
		<view class="tabbar">
			<view class="tab-item" @click="handleTabClick('home')">
				<text class="tab-icon">🚶</text>
				<text class="tab-label">出行</text>
			</view>
			<view class="tab-item" @click="handleTabClick('navigation')">
				<text class="tab-icon">🧭️</text>
				<text class="tab-label">导航</text>
			</view>
			<view class="tab-item" @click="handleTabClick('device')">
				<text class="tab-icon">⚙️</text>
				<text class="tab-label">设备</text>
			</view>
			<view class="tab-item active" @click="handleTabClick('diagnostic')">
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

const isChecking = ref(false)
const batteryLevel = ref(78)
const fps = ref(5.2)
const latency = ref(118)
const bleSignal = ref(-72)

const latencyDetails = ref([
	{ label: '图像采集', value: 33 },
	{ label: '图像预处理', value: 18 },
	{ label: '深度估计', value: 45 },
	{ label: '空间映射', value: 12 },
	{ label: 'BLE 传输', value: 28 },
	{ label: '触点驱动', value: 15 }
])

const latencyBarColor = (ms) => {
	if (ms > 40) return '#f44336'
	if (ms >= 20) return '#ff9800'
	return '#4caf50'
}

const autoStart = ref(false)

const detectStatusTitle = computed(() => {
	return isChecking.value ? '设备检测中' : '设备运行正常'
})

const detectStatusSub = computed(() => {
	return isChecking.value ? '正在检查各模块状态' : '所有模块检测通过'
})

const abnormalItems = computed(() => {
	const list = []

	if (fps.value < 4) list.push('刷新率偏低')
	if (latency.value > 150) list.push('总延迟偏高')
	if (bleSignal.value < -85) list.push('蓝牙信号偏弱')
	if (batteryLevel.value < 20) list.push('电池电量偏低')

	return list
})

const wait = (ms) => new Promise(resolve => setTimeout(resolve, ms))

const buildDeviceStatusResult = () => {
	return {
		isNormal: abnormalItems.value.length === 0,
		abnormalItems: abnormalItems.value,
		summary: abnormalItems.value.length === 0
			? '设备状态正常，各项检测均无异常'
			: `设备存在异常，异常项包括：${abnormalItems.value.join('，')}`,
		batteryLevel: batteryLevel.value,
		fps: fps.value,
		latency: latency.value,
		bleSignal: bleSignal.value
	}
}

const performDiagnostic = async () => {
	if (isChecking.value) {
		return buildDeviceStatusResult()
	}

	isChecking.value = true

	try {
		uni.showLoading({
			title: '检测中...'
		})

		// TODO: 这里替换成真实检测逻辑
		await wait(1600)

		// 模拟数据，可按实际检测逻辑替换
		fps.value = 5.2
		latency.value = 118
		bleSignal.value = -72
		batteryLevel.value = 78
		latencyDetails.value = [
			{ label: '图像采集', value: 33 },
			{ label: '图像预处理', value: 18 },
			{ label: '深度估计', value: 45 },
			{ label: '空间映射', value: 12 },
			{ label: 'BLE 传输', value: 28 },
			{ label: '触点驱动', value: 15 }
		]

		uni.showToast({
			title: abnormalItems.value.length === 0 ? '设备状态正常' : '检测到异常项',
			icon: 'none'
		})

		return buildDeviceStatusResult()
	} catch (err) {
		console.error('performDiagnostic failed:', err)
		uni.showToast({
			title: '检测失败',
			icon: 'none'
		})

		return {
			isNormal: false,
			abnormalItems: ['检测失败'],
			summary: '设备检测失败',
			batteryLevel: batteryLevel.value,
			fps: fps.value,
			latency: latency.value,
			bleSignal: bleSignal.value
		}
	} finally {
		isChecking.value = false
		uni.hideLoading()
	}
}

const getDeviceStatus = async () => {
	return buildDeviceStatusResult()
}

const recheck = async () => {
	await performDiagnostic()
}

const handleTabClick = (type) => {
	const currentPath = '/pages/diagnostic/diagnostic'
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

const registerAssistantBridge = () => {
	registerDeviceHandlers({
		diagnostic: async () => {
			return await performDiagnostic()
		},
		getDeviceStatus: async () => {
			return await getDeviceStatus()
		}
	})
}

onLoad((options) => {
	if (options?.autoStart === '1') {
		autoStart.value = true
	}
})

onMounted(async () => {
	registerAssistantBridge()

	if (autoStart.value) {
		await performDiagnostic()
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
	height: 100vh;
	background: #f5f6f8;
	max-width: 750rpx;
	margin: 0 auto;
	position: relative;
}

.scroll-body {
	flex: 1;
	scrollbar-width: none;
	-ms-overflow-style: none;
}

.scroll-body::-webkit-scrollbar {
	display: none;
	width: 0;
}

.navbar {
	display: flex;
	flex-direction: row;
	align-items: center;
	padding: 48rpx 24rpx 24rpx 24rpx;
	background: #ffffff;
	border-bottom: 1rpx solid #f0f0f0;
	flex-shrink: 0;
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

.scroll-body {
	flex: 1;
	height: 0;
}

.card {
	margin: 0 24rpx 0 24rpx;
	background: #ffffff;
	border-radius: 20rpx;
	padding: 28rpx 24rpx;
	box-shadow: 0 2rpx 10rpx rgba(26,58,82,0.07);
}

.section-title {
	font-size: 28rpx;
	font-weight: 700;
	color: #1a3a52;
	padding: 28rpx 24rpx 12rpx 24rpx;
	display: block;
}

.status-card {
	margin-top: 24rpx;
}

.status-top {
	display: flex;
	flex-direction: row;
	align-items: center;
	justify-content: space-between;
	margin-bottom: 20rpx;
}

.status-left {
	display: flex;
	flex-direction: row;
	align-items: center;
	gap: 16rpx;
}

.ok-badge {
	width: 56rpx;
	height: 56rpx;
	border-radius: 28rpx;
	background: #4caf50;
	display: flex;
	align-items: center;
	justify-content: center;
	box-shadow: 0 2rpx 8rpx rgba(76,175,80,0.3);
}

.ok-badge.small {
	width: 40rpx;
	height: 40rpx;
	border-radius: 20rpx;
}

.ok-icon {
	font-size: 26rpx;
	color: #ffffff;
	font-weight: 700;
}

.status-info {
	display: flex;
	flex-direction: column;
	gap: 4rpx;
}

.status-title {
	font-size: 30rpx;
	font-weight: 700;
	color: #1a3a52;
}

.status-sub {
	font-size: 22rpx;
	color: #8a9bb0;
}

.battery-info {
	display: flex;
	flex-direction: row;
	align-items: center;
	gap: 6rpx;
}

.battery-pct {
	font-size: 28rpx;
	font-weight: 700;
	color: #4caf50;
}

.battery-ico {
	font-size: 28rpx;
}

.progress-bar-wrap {
	margin-bottom: 16rpx;
}

.progress-bar-bg {
	width: 100%;
	height: 10rpx;
	background: #e8f5e9;
	border-radius: 5rpx;
	overflow: hidden;
}

.progress-bar-fill {
	height: 100%;
	background: linear-gradient(90deg, #4caf50, #8bc34a);
	border-radius: 5rpx;
}

.status-bottom {
	display: flex;
	flex-direction: row;
	justify-content: space-between;
}

.status-hint {
	font-size: 22rpx;
	color: #8a9bb0;
}

.status-ble {
	font-size: 22rpx;
	color: #2196f3;
}

.grid2 {
	display: flex;
	flex-wrap: wrap;
	justify-content: space-between;
	row-gap: 16rpx;
	padding: 0 24rpx;
}

.metric-card {
	width: 48%;
	box-sizing: border-box;
	background: #ffffff;
	border-radius: 16rpx;
	padding: 20rpx;
	box-shadow: 0 2rpx 10rpx rgba(26,58,82,0.07);
	display: flex;
	flex-direction: column;
	gap: 6rpx;
	min-height: 140rpx;
}

.metric-name {
	font-size: 22rpx;
	color: #8a9bb0;
	font-weight: 500;
}

.metric-value {
	font-size: 48rpx;
	font-weight: 700;
	color: #1a3a52;
	line-height: 1.1;
}

.metric-unit {
	font-size: 20rpx;
	color: #8a9bb0;
}

.metric-tag {
	align-self: flex-start;
	padding: 6rpx 16rpx;
	border-radius: 20rpx;
	font-size: 20rpx;
	font-weight: 600;
	margin-top: 6rpx;
}

.metric-tag.green {
	background: #e6f4ea;
	color: #2e7d32;
}

.metric-tag.blue {
	background: #e3f2fd;
	color: #1976d2;
}

.hw-tag, .metric-tag {
	padding: 4rpx 14rpx;
	border-radius: 20rpx;
	align-self: flex-start;
}

.hw-tag.green, .metric-tag.green {
	background: #e8f5e9;
}

.hw-tag.blue, .metric-tag.blue {
	background: #e3f2fd;
}

.hw-tag.yellow, .metric-tag.yellow {
	background: #fff8e1;
}

.tag-text {
	font-size: 20rpx;
	font-weight: 600;
	color: #1a3a52;
}

.hw-tag.green .tag-text { color: #2e7d32; }
.hw-tag.blue .tag-text { color: #1565c0; }
.hw-tag.yellow .tag-text { color: #e65100; }
.metric-tag.green .tag-text { color: #2e7d32; }
.metric-tag.blue .tag-text { color: #1565c0; }

.latency-row {
	display: flex;
	flex-direction: row;
	align-items: center;
	gap: 12rpx;
	margin-bottom: 18rpx;
}

.latency-label {
	width: 140rpx;
	font-size: 22rpx;
	color: #5a7a8f;
	flex-shrink: 0;
}

.latency-bar-bg {
	flex: 1;
	height: 10rpx;
	background: #f0f0f0;
	border-radius: 5rpx;
	overflow: hidden;
}

.latency-bar {
	height: 100%;
	border-radius: 5rpx;
}

.latency-val {
	width: 70rpx;
	font-size: 22rpx;
	color: #1a3a52;
	font-weight: 600;
	text-align: right;
	flex-shrink: 0;
}

.latency-total-row {
	display: flex;
	flex-direction: row;
	justify-content: space-between;
	align-items: center;
	padding-top: 16rpx;
	border-top: 1rpx solid #f0f0f0;
	margin-top: 4rpx;
}

.latency-total-label {
	font-size: 24rpx;
	font-weight: 600;
	color: #1a3a52;
}

.latency-total-val {
	font-size: 28rpx;
	font-weight: 700;
	color: #2196f3;
}

.hw-item {
	padding: 8rpx 0;
}

.hw-header {
	display: flex;
	flex-direction: row;
	align-items: center;
	gap: 12rpx;
	margin-bottom: 10rpx;
}

.hw-dot {
	width: 14rpx;
	height: 14rpx;
	border-radius: 7rpx;
	flex-shrink: 0;
}

.hw-dot.green { background: #4caf50; }
.hw-dot.yellow { background: #ff9800; }
.hw-dot.red { background: #f44336; }

.hw-name {
	flex: 1;
	font-size: 26rpx;
	font-weight: 600;
	color: #1a3a52;
}

.hw-detail-row {
	display: flex;
	flex-direction: row;
	gap: 24rpx;
	padding-left: 26rpx;
}

.hw-detail {
	font-size: 22rpx;
	color: #8a9bb0;
}

.hw-divider {
	height: 1rpx;
	background: #f0f0f0;
	margin: 14rpx 0;
}

.comm-row {
	display: flex;
	flex-direction: row;
	align-items: center;
	gap: 12rpx;
	padding: 10rpx 0;
	border-bottom: 1rpx solid #f5f6f8;
}

.comm-row:last-child {
	border-bottom: none;
}

.comm-label {
	flex: 1;
	font-size: 26rpx;
	color: #1a3a52;
	font-weight: 500;
}

.comm-value {
	font-size: 24rpx;
	color: #5a7a8f;
	margin-right: 8rpx;
}

.risk-card {
	background: #f9fbe7;
}

.risk-header {
	display: flex;
	flex-direction: row;
	align-items: center;
	gap: 12rpx;
	margin-bottom: 16rpx;
}

.risk-all-ok {
	font-size: 26rpx;
	font-weight: 600;
	color: #2e7d32;
}

.risk-tips {
	display: flex;
	flex-direction: column;
	gap: 10rpx;
	padding-left: 8rpx;
}

.risk-tip {
	font-size: 22rpx;
	color: #8a9bb0;
	line-height: 1.6;
}

.bottom-action {
	padding: 40rpx 24rpx 0 24rpx;
	display: flex;
	align-items: center;
	justify-content: center;
}

.recheck-btn {
	width: 560rpx;
	height: 96rpx;
	background: linear-gradient(135deg, #2196f3 0%, #1976d2 100%);
	border-radius: 48rpx;
	border: none;
	display: flex;
	align-items: center;
	justify-content: center;
	box-shadow: 0 8rpx 24rpx rgba(33,150,243,0.3);
	transition: all 0.3s ease;
}

.recheck-btn:active {
	transform: scale(0.97);
	box-shadow: 0 4rpx 12rpx rgba(33,150,243,0.2);
}

.recheck-btn[disabled] {
	opacity: 0.65;
}

.recheck-btn-text {
	font-size: 32rpx;
	color: #ffffff;
	font-weight: 600;
	letter-spacing: 2rpx;
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
	box-shadow: 0 -2rpx 16rpx rgba(26,58,82,0.08);
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