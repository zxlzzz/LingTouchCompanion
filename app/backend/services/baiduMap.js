/**
 * baiduMap.js
 * 封装百度地图 API 调用逻辑
 */

const axios = require('axios');
const config = require('../config/baidu');

// 创建专用 axios 实例
const http = axios.create({
  timeout: config.TIMEOUT,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * 地点关键词检索
 * @param {object} params
 * @param {string} params.query
 * @param {string} params.region
 * @param {number} [params.page_size=10]
 * @param {number} [params.page_num=0]
 * @param {string} [params.output='json']
 * @returns {Promise<object>}
 */
async function searchPlace(params) {
  const { query, region, page_size = 10, page_num = 0, output = 'json' } = params;

  if (!query || !region) {
    throw new Error('参数缺失：query 和 region 为必填项');
  }

  const response = await http.get(config.PLACE_SEARCH_URL, {
    params: {
      query,
      region,
      page_size,
      page_num,
      output,
      ak: config.BAIDU_AK,
    },
  });

  const data = response.data;

  if (data.status !== 0) {
    throw new Error(`百度地图 API 错误 [status=${data.status}]: ${data.message || '未知错误'}`);
  }

  return data;
}

/**
 * 步行路线规划
 * @param {object} params
 * @param {string} params.origin
 * @param {string} params.destination
 * @param {string} [params.coord_type='bd09ll']
 * @param {number} [params.steps_info=1]
 * @returns {Promise<object>}
 */
async function getWalkingRoute(params) {
  const {
    origin,
    destination,
    coord_type = 'bd09ll',
    steps_info = 1,
  } = params;

  if (!origin || !destination) {
    throw new Error('参数缺失：origin 和 destination 为必填项');
  }

  const response = await http.get(config.WALKING_ROUTE_URL, {
    params: {
      origin,
      destination,
      coord_type,
      steps_info,
      ak: config.BAIDU_AK,
    },
  });

  const data = response.data;

  if (data.status !== 0) {
    throw new Error(`百度地图 API 错误 [status=${data.status}]: ${data.message || '未知错误'}`);
  }

  return data;
}

/**
 * 逆地理编码
 * @param {object} params
 * @param {string|number} params.lat
 * @param {string|number} params.lng
 * @param {string} [params.output='json']
 * @returns {Promise<object>}
 */
async function reverseGeocode(params) {
  const { lat, lng, output = 'json' } = params;

  if (lat === undefined || lng === undefined || lat === '' || lng === '') {
    throw new Error('参数缺失：lat 和 lng 为必填项');
  }

  const response = await http.get(config.REVERSE_GEOCODING_URL, {
    params: {
      location: `${lat},${lng}`,
      output,
      ak: config.BAIDU_AK,
    },
  });

  const data = response.data;

  if (data.status !== 0) {
    throw new Error(`百度地图逆地理编码错误 [status=${data.status}]: ${data.message || '未知错误'}`);
  }

  return data.result;
}

module.exports = {
  searchPlace,
  getWalkingRoute,
  reverseGeocode,
};