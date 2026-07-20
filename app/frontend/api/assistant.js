import request from '@/utils/request.js'

/**
 * 语音助手命令解析
 * @param {string} text 用户语音识别后的文本
 * @returns {Promise<Object>} 结构化命令
 */
export const parseAssistantCommand = (text) => {
	return request({
		url: '/api/assistant/parse-command',
		method: 'POST',
		data: {
			text
		}
	})
}
