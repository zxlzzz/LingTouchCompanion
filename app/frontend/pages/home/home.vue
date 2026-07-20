<template>
	<view class="container">
		<!-- 顶部标题 -->
		<view class="header">
			<text class="title">准备出发</text>
			<text class="subtitle">{{ currentTime }} ｜ 多云 {{ weatherTemp }}℃ ☁️</text>
		</view>

		<!-- 设备卡片 -->
		<view class="device-card">
			<view class="device-top">
				<view class="device-left">
					<view class="device-icon-wrap">
						<text class="icon device-icon">🦯</text>
					</view>
					<view class="device-info">
						<text class="device-title">设备已连接</text>
						<text class="device-subtitle">电量 {{ batteryLevel }}%</text>
					</view>
				</view>

				<view class="mode-switch">
					<view
						class="mode-item"
						:class="{ active: currentMode === 'map' }"
						@click="switchMode('map')"
					>
						<text class="mode-text" :class="{ active: currentMode === 'map' }">地图模式</text>
					</view>

					<view
						class="mode-item"
						:class="{ active: currentMode === 'zoom' }"
						@click="switchMode('zoom')"
					>
						<text class="mode-text" :class="{ active: currentMode === 'zoom' }">放大模式</text>
					</view>
				</view>
			</view>

			<view class="battery-bar">
				<view class="battery-fill" :style="{ width: batteryLevel + '%' }"></view>
			</view>
		</view>

		<!-- 主按钮区 -->
		<view class="action-group">
			<view class="main-btn" @click="goNavigationPage()">
				<text class="main-btn-text">开始导航</text>
			</view>

			<view class="assistant-tip">
				<text class="assistant-tip-title">语音助手已自动待命</text>
				<text class="assistant-tip-text">现在可直接说“灵触助手”</text>
				<text class="assistant-tip-text">再说“带我去威海站”或“去医院”</text>
			</view>
		</view>

		<!-- 最近目的地 -->
		<view class="section">
			<text class="section-title">最近目的地</text>

			<view class="grid">
				<view class="grid-item" @click="goNavigationPage('学校')">
					<view class="grid-left">
						<text class="icon">🏫</text>
						<text class="grid-text">学校</text>
					</view>
					<text class="grid-arrow">›</text>
				</view>

				<view class="grid-item" @click="goNavigationPage('地铁站')">
					<view class="grid-left">
						<text class="icon">🚇</text>
						<text class="grid-text">地铁站</text>
					</view>
					<text class="grid-arrow">›</text>
				</view>

				<view class="grid-item" @click="goNavigationPage('超市')">
					<view class="grid-left">
						<text class="icon">🛒</text>
						<text class="grid-text">超市</text>
					</view>
					<text class="grid-arrow">›</text>
				</view>

				<view class="grid-item" @click="goNavigationPage('医院')">
					<view class="grid-left">
						<text class="icon">🏥</text>
						<text class="grid-text">医院</text>
					</view>
					<text class="grid-arrow">›</text>
				</view>
			</view>
		</view>

		<!-- 快速场景 -->
		<view class="section">
			<text class="section-title">快速场景</text>

			<view class="grid">
				<view class="grid-item" @click="goNavigationPage('回家')">
					<view class="grid-left">
						<text class="icon">🏠</text>
						<text class="grid-text">回家</text>
					</view>
					<text class="grid-arrow">›</text>
				</view>

				<view class="grid-item" @click="goNavigationPage('最近卫生间')">
					<view class="grid-left">
						<text class="icon">🚻</text>
						<text class="grid-text">最近卫生间</text>
					</view>
					<text class="grid-arrow">›</text>
				</view>

				<view class="grid-item" @click="goNavigationPage('公交站')">
					<view class="grid-left">
						<text class="icon">🚌</text>
						<text class="grid-text">公交站</text>
					</view>
					<text class="grid-arrow">›</text>
				</view>

				<view class="grid-item" @click="goNavigationPage('服务台')">
					<view class="grid-left">
						<text class="icon">🔔</text>
						<text class="grid-text">服务台</text>
					</view>
					<text class="grid-arrow">›</text>
				</view>
			</view>
		</view>

		<!-- 底部 tabbar -->
		<view class="tabbar">
			<view class="tab-item active">
				<text class="tab-icon active-icon">🚶</text>
				<text class="tab-label active-label">出行</text>
			</view>

			<view class="tab-item" @click="switchTab('navigation')">
				<text class="tab-icon">🧭</text>
				<text class="tab-label">导航</text>
			</view>

			<view class="tab-item" @click="switchTab('device')">
				<text class="tab-icon">⚙️</text>
				<text class="tab-label">设备</text>
			</view>

			<view class="tab-item" @click="switchTab('diagnostic')">
				<text class="tab-icon">📊</text>
				<text class="tab-label">诊断</text>
			</view>
		</view>
	</view>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { startGlobalAssistant, stopGlobalAssistant } from '@/utils/globalAssistant.js'

const currentMode = ref('map')
const batteryLevel = ref(78)
const weatherTemp = ref(24)
const currentTime = ref('12:45')

let timer = null

const updateTime = () => {
	const now = new Date()
	const h = String(now.getHours()).padStart(2, '0')
	const m = String(now.getMinutes()).padStart(2, '0')
	currentTime.value = `${h}:${m}`
}

const switchMode = (mode) => {
	currentMode.value = mode

	uni.showToast({
		title: mode === 'map' ? '已切换到地图模式' : '已切换到放大模式',
		icon: 'none'
	})
}

const goNavigationPage = (keyword = '') => {
	const url = keyword
		? `/pages/navigation/navigation?keyword=${encodeURIComponent(keyword)}`
		: '/pages/navigation/navigation'

	uni.reLaunch({ url })
}

const switchTab = (type) => {
	const routes = {
		navigation: '/pages/navigation/navigation',
		device: '/pages/device/device',
		diagnostic: '/pages/diagnostic/diagnostic'
	}

	if (!routes[type]) return
	uni.reLaunch({ url: routes[type] })
}

onMounted(async () => {
	updateTime()
	timer = setInterval(updateTime, 30000)

	// 页面进入后自动启动语音助手
	try {
		await startGlobalAssistant()
	} catch (err) {
		console.error('[home] 自动启动语音助手失败：', err)
	}
})

onUnmounted(() => {
	if (timer) {
		clearInterval(timer)
		timer = null
	}

	// 离开首页时不强制停止，保留全局待命能力
})
</script>

<style scoped>
/* 通用图标样式 */
.icon {
  font-size: 32rpx;
  color: #409EFF;
  margin-right: 12rpx;
  vertical-align: middle;
}

/* 设备卡片图标单独调整 */
.device-icon {
  font-size: 40rpx;
  color: #409EFF;
}

/* 底部导航图标 */
.tab-icon {
  font-size: 34rpx;
  color: #9aa8b5;
}
.active-icon {
  color: #409EFF;
}

.container {
	min-height: 100vh;
	background: linear-gradient(180deg, #f7fbff 0%, #f3f6fa 100%);
	max-width: 750rpx;
	margin: 0 auto;
	padding: 34rpx 24rpx 150rpx;
	box-sizing: border-box;
}

.header {
	padding-top: 20rpx;
	align-items: center;
	justify-content: center;
	margin-bottom: 28rpx;
}

.title {
	display: block;
	text-align: center;
	font-size: 58rpx;
	font-weight: 700;
	color: #183b56;
	letter-spacing: 2rpx;
}

.subtitle {
	display: block;
	text-align: center;
	margin-top: 16rpx;
	font-size: 28rpx;
	color: #7c93a8;
}

.device-card {
	background: #ffffff;
	border-radius: 30rpx;
	padding: 28rpx 24rpx 22rpx;
	box-shadow: 0 10rpx 28rpx rgba(26, 58, 82, 0.08);
}

.device-top {
	display: flex;
	flex-direction: row;
	justify-content: space-between;
	align-items: flex-start;
	gap: 20rpx;
}

.device-left {
	flex: 1;
	display: flex;
	flex-direction: row;
	align-items: center;
	min-width: 0;
}

.device-icon-wrap {
	width: 84rpx;
	height: 84rpx;
	border-radius: 22rpx;
	background: #eaf4ff;
	display: flex;
	align-items: center;
	justify-content: center;
	margin-right: 18rpx;
	flex-shrink: 0;
}

.device-info {
	flex: 1;
	min-width: 0;
}

.device-title {
	display: block;
	font-size: 32rpx;
	font-weight: 700;
	color: #183b56;
}

.device-subtitle {
	display: block;
	margin-top: 8rpx;
	font-size: 26rpx;
	color: #7c93a8;
}

.mode-switch {
	display: flex;
	flex-direction: column;
	gap: 12rpx;
	flex-shrink: 0;
}

.mode-item {
	min-width: 150rpx;
	height: 52rpx;
	padding: 0 20rpx;
	border-radius: 26rpx;
	background: #eef4f8;
	display: flex;
	align-items: center;
	justify-content: center;
}

.mode-item.active {
	background: linear-gradient(135deg, #4da3ff 0%, #2f7fe8 100%);
	box-shadow: 0 6rpx 16rpx rgba(47, 127, 232, 0.22);
}

.mode-text {
	font-size: 22rpx;
	font-weight: 600;
	color: #6c8196;
}

.mode-text.active {
	color: #ffffff;
}

.battery-bar {
	margin-top: 22rpx;
	width: 100%;
	height: 12rpx;
	border-radius: 12rpx;
	background: #e6edf2;
	overflow: hidden;
}

.battery-fill {
	height: 100%;
	border-radius: 12rpx;
	background: linear-gradient(90deg, #63b746 0%, #7ccc52 100%);
}

.action-group {
	margin-top: 24rpx;
}

.main-btn {
	height: 96rpx;
	border-radius: 24rpx;
	display: flex;
	align-items: center;
	justify-content: center;
	background: linear-gradient(135deg, #2f93ea 0%, #2478d8 100%);
	box-shadow: 0 10rpx 22rpx rgba(33, 150, 243, 0.16);
}

.main-btn-text {
	font-size: 34rpx;
	font-weight: 700;
	color: #ffffff;
}

.assistant-tip {
	margin-top: 18rpx;
	padding: 22rpx 20rpx;
	background: #eef7ff;
	border-radius: 20rpx;
	border: 1rpx solid #d8eafc;
}

.assistant-tip-title {
	display: block;
	font-size: 26rpx;
	font-weight: 700;
	color: #183b56;
	margin-bottom: 10rpx;
}

.assistant-tip-text {
	display: block;
	font-size: 24rpx;
	color: #2478d8;
	line-height: 1.7;
}

.section {
	margin-top: 34rpx;
}

.section-title {
	display: block;
	font-size: 34rpx;
	font-weight: 700;
	color: #183b56;
	margin-bottom: 18rpx;
}

.grid {
	display: flex;
	flex-wrap: wrap;
	justify-content: space-between;
	row-gap: 18rpx;
}

.grid-item {
	width: 48%;
	min-height: 110rpx;
	box-sizing: border-box;
	background: #ffffff;
	border-radius: 22rpx;
	padding: 0 20rpx;
	display: flex;
	flex-direction: row;
	align-items: center;
	justify-content: space-between;
	box-shadow: 0 6rpx 18rpx rgba(26, 58, 82, 0.06);
}

.grid-left {
	display: flex;
	flex-direction: row;
	align-items: center;
	flex: 1;
	min-width: 0;
}

.grid-text {
	font-size: 30rpx;
	font-weight: 600;
	color: #183b56;
}

.grid-arrow {
	font-size: 34rpx;
	color: #c4ced6;
	margin-left: 12rpx;
}

.tabbar {
	position: fixed;
	bottom: 0;
	left: 50%;
	transform: translateX(-50%);
	width: 100%;
	max-width: 750rpx;
	height: 122rpx;
	background: rgba(255, 255, 255, 0.98);
	display: flex;
	align-items: center;
	justify-content: space-around;
	box-shadow: 0 -4rpx 18rpx rgba(26, 58, 82, 0.08);
	border-top: 1rpx solid #eef2f5;
	padding-bottom: env(safe-area-inset-bottom);
}

.tab-item {
	flex: 1;
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
}

.tab-label {
	margin-top: 6rpx;
	font-size: 22rpx;
	color: #9aa8b5;
}

.active-label {
	color: #2196f3;
	font-weight: 700;
}
</style>