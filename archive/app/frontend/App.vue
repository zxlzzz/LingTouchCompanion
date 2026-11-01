<script>
import { registerHazardSource, startHazardMonitoring } from '@/utils/hazardEngine.js'
import { mockHazardSource } from '@/utils/hazardMockSource.js'

export default {
	onLaunch() {
		console.log('App Launch')

		// 启动危险播报引擎（应用级常驻，独立于语音助手唤醒词）：
		// 当前注册模拟数据源（演示开关打开时才生成事件），
		// 真实 BLE 摄像头数据源就绪后替换注册即可
		registerHazardSource(mockHazardSource)
		startHazardMonitoring()
	},
	onShow() {
		console.log('App Show')
	},
	onHide() {
		console.log('App Hide')
	},
	onUnload() {
		console.log('App Unload')
	}
}
</script>

<style>
page {
	background: #f5f6f8;
}
</style>
