<template>
	<view class="hazard-banner" v-if="show">
		<text class="hazard-icon">⚠️</text>
		<text class="hazard-text">{{ text }}</text>
	</view>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { onHazardUi } from '@/utils/hazardEngine.js'

const show = ref(false)
const text = ref('')

let timer = null
let unsubscribe = null

const buildShortText = (hazard) => {
	const label = hazard?.label || ''
	const distance = Math.round(Number(hazard?.distance) || 0)
	return `检测到${label}，约${distance}米`
}

onMounted(() => {
	unsubscribe = onHazardUi((hazard, hazardText) => {
		text.value = hazardText || buildShortText(hazard)
		show.value = true
		clearTimeout(timer)
		timer = setTimeout(() => {
			show.value = false
		}, 4000)

		// 紧急危险（≤2m）触发震动反馈
		if (hazard && Number(hazard.distance) <= 2) {
			try {
				if (navigator.vibrate) navigator.vibrate(300)
			} catch (err) {
				// 浏览器不支持震动则忽略
			}
		}
	})
})

onBeforeUnmount(() => {
	clearTimeout(timer)
	if (unsubscribe) unsubscribe()
})
</script>

<style scoped>
.hazard-banner {
	position: fixed;
	left: 50%;
	transform: translateX(-50%);
	top: 20rpx;
	z-index: 9999;
	max-width: 86vw;
	display: flex;
	align-items: center;
	gap: 12rpx;
	padding: 16rpx 28rpx;
	border-radius: 44rpx;
	background: linear-gradient(135deg, #e53935 0%, #c62828 100%);
	box-shadow: 0 10rpx 30rpx rgba(198, 40, 40, 0.35);
	animation: hazardDropIn 0.25s ease-out;
}

.hazard-icon {
	font-size: 30rpx;
	flex-shrink: 0;
}

.hazard-text {
	font-size: 26rpx;
	font-weight: 600;
	color: #ffffff;
	line-height: 1.5;
}

@keyframes hazardDropIn {
	from {
		opacity: 0;
		transform: translateX(-50%) translateY(-16rpx);
	}
	to {
		opacity: 1;
		transform: translateX(-50%) translateY(0);
	}
}
</style>
