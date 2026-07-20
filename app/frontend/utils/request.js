/**
 * utils/request.js
 * 封装 uni.request（调用本地 Node 服务）
 */

const BASE_URL = 'http://localhost:3000'; 

const request = ({ url, method = 'GET', data = {}, header = {} }) => {
	return new Promise((resolve, reject) => {
		uni.request({
			url: BASE_URL + url,
			method,
			data,
			header: {
				'Content-Type': 'application/json',
				...header
			},
			success: (res) => {
				if (res.statusCode === 200) {
					resolve(res.data);
				} else {
					reject(new Error(`HTTP ${res.statusCode}`));
				}
			},
			fail: (err) => {
				console.error('请求失败:', err);
				reject(err);
			}
		});
	});
};

export default request;
