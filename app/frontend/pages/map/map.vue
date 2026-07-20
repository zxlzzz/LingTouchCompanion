<template>
	<view class="page">
		<web-view :src="mapUrl"></web-view>
	</view>
</template>

<script setup>
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'

const mapUrl = ref('/static/map/baidu-map.html')

onLoad((options) => {
	const params = new URLSearchParams()

	if (options.originLat) params.append('originLat', options.originLat)
	if (options.originLng) params.append('originLng', options.originLng)
	if (options.destLat) params.append('destLat', options.destLat)
	if (options.destLng) params.append('destLng', options.destLng)
	if (options.destName) params.append('destName', decodeURIComponent(options.destName))
	if (options.polyline) params.append('polyline', decodeURIComponent(options.polyline))

	mapUrl.value = `/static/map/baidu-map.html?${params.toString()}`
})
</script>

<style scoped>
.page {
	width: 100%;
	height: 100vh;
	background: #f5f6f8;
}
</style>