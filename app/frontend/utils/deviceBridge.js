let deviceHandlers = {
	connect: null,
	disconnect: null,
	diagnostic: null,
	getBatteryStatus: null,
	getDeviceStatus: null
}

export const registerDeviceHandlers = (handlers = {}) => {
	deviceHandlers = {
		...deviceHandlers,
		...handlers
	}
}

export const unregisterDeviceHandlers = () => {
	deviceHandlers = {
		connect: null,
		disconnect: null,
		diagnostic: null,
		getBatteryStatus: null,
		getDeviceStatus: null
	}
}

export const invokeDeviceHandler = async (name, payload) => {
	const fn = deviceHandlers[name]

	if (typeof fn !== 'function') {
		return {
			success: false,
			message: `未注册设备处理器：${name}`
		}
	}

	try {
		const result = await fn(payload)
		return {
			success: true,
			data: result
		}
	} catch (err) {
		console.error(`[deviceBridge] 执行 ${name} 失败：`, err)
		return {
			success: false,
			message: err?.message || `${name} 执行失败`
		}
	}
}
