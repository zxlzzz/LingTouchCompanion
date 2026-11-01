/**
 * 百度地图 REST API（经后端代理调用）
 *
 * 统一走后端 /api/map/* 接口：
 * - 服务端 AK 配置在 backend/.env 的 BAIDU_AK，不暴露到前端
 * - 所有坐标均为 BD09（百度坐标系）
 */

import request from '@/utils/request.js'

// ---------- 1. 地点搜索 ----------
/**
 * 关键字搜索 POI
 * @param {string} query     搜索关键词
 * @param {string} region    城市名（如「威海」），空则全国
 * @param {number} pageSize  每页数量
 * @param {number} pageNum   页码（从0开始）
 * @returns {Promise} res.data.results: [{name, location:{lat,lng}, address, ...}]
 */
export const searchPlace = async (query, region = '', pageSize = 10, pageNum = 0) => {
  return request({
    url: '/api/map/search',
    method: 'GET',
    data: {
      query,
      region,
      page_size: pageSize,
      page_num: pageNum
    }
  })
}

// ---------- 2. 步行路径规划 ----------
/**
 * @param {string} origin      "纬度,经度"（BD09）
 * @param {string} destination "纬度,经度"（BD09）
 * @returns {Promise} res.data.result.routes[0]: {distance, duration, steps:[{instruction, distance, duration, path, turn_type}]}
 *   path 为 "lng,lat;lng,lat;..." 折线串
 */
export const getWalkRoute = async (origin, destination) => {
  return request({
    url: '/api/map/walk-route',
    method: 'POST',
    data: {
      origin,
      destination
    }
  })
}

// ---------- 3. 逆地理编码 ----------
/**
 * @param {number} lat 纬度（BD09）
 * @param {number} lng 经度（BD09）
 * @returns {Promise} res.data: {formatted_address, addressComponent:{city, district, province, ...}}
 */
export const reverseGeocode = async (lat, lng) => {
  return request({
    url: '/api/map/reverse-geocode',
    method: 'GET',
    data: {
      lat,
      lng
    }
  })
}
