/**
 * 高德地图 Web服务 REST API
 * 直接从前端调用，替代原百度地图后端代理
 *
 * ⚠️ 将下方 AMAP_KEY 替换为你申请的 Web服务 Key
 * 申请地址: https://lbs.amap.com → 控制台 → 应用管理 → 添加Key → 服务平台选"Web服务"
 */

const AMAP_KEY = '022d2b829219a983cce05c48d2d1db47' // ← 替换为你的 Key

const BASE = 'https://restapi.amap.com'

// ---------- 通用请求 ----------
function amapRequest(url, data = {}) {
  return new Promise((resolve, reject) => {
    uni.request({
      url,
      data: { key: AMAP_KEY, output: 'JSON', ...data },
      method: 'GET',
      success: (res) => {
        if (res.statusCode === 200 && (res.data.status === '1' || res.data.status === 1)) {
          resolve(res.data)
        } else {
          reject({
            errMsg: res.data?.info || '高德API错误',
            infocode: res.data?.infocode,
            raw: res.data
          })
        }
      },
      fail: (err) => reject({ errMsg: err.errMsg || '网络请求失败' })
    })
  })
}

// ---------- 1. 地点搜索 ----------
/**
 * 关键字搜索 POI
 * @param {string} query    搜索关键词
 * @param {string} region   城市名或 adcode
 * @param {number} pageSize 每页数量
 * @param {number} pageNum  页码（从1开始）
 * @returns {Promise} pois 数组（已统一格式）
 */
export const searchPlace = async (query, region = '', pageSize = 10, pageNum = 1) => {
  const res = await amapRequest(`${BASE}/v3/place/text`, {
    keywords: query,
    city: region,
    offset: pageSize,
    page: pageNum,
    extensions: 'all'
  })

  // 将高德格式转换为与原百度接口兼容的格式
  const results = (res.pois || []).map((poi) => {
    const [lng, lat] = (poi.location || '0,0').split(',')
    return {
      name: poi.name,
      address: poi.address || '',
      tel: poi.tel || '',
      type: poi.type || '',
      uid: poi.id,
      location: {
        lat: Number(lat),
        lng: Number(lng)
      }
    }
  })

  return { data: { results } }
}

// ---------- 2. 步行路径规划 ----------
/**
 * @param {string} origin      "纬度,经度" 或 "经度,纬度"
 * @param {string} destination "纬度,经度" 或 "经度,纬度"
 * @returns {Promise} 与原项目兼容的 route 结构
 */
export const getWalkRoute = async (origin, destination) => {
  // 原百度接口用 "lat,lng"，高德要 "lng,lat"，自动转换
  const originParam = flipIfNeeded(origin)
  const destParam = flipIfNeeded(destination)

  const res = await amapRequest(`${BASE}/v3/direction/walking`, {
    origin: originParam,
    destination: destParam
  })

  const path = res.route?.paths?.[0]
  if (!path) {
    return { data: { result: { routes: [] } } }
  }

  // 将高德步行结果转为兼容格式
  const steps = (path.steps || []).map((step) => {
    // 高德 polyline 格式: "lng,lat;lng,lat;..."
    const polyline = step.polyline || ''
    return {
      instruction: step.instruction || '',
      distance: Number(step.distance || 0),
      duration: Number(step.duration || 0),
      path: polyline // 与原项目 parsePathStringToPoints 兼容
    }
  })

  return {
    data: {
      result: {
        routes: [
          {
            distance: Number(path.distance || 0),
            duration: Number(path.duration || 0),
            steps
          }
        ]
      }
    }
  }
}

// ---------- 3. 逆地理编码 ----------
/**
 * @param {number} lat 纬度
 * @param {number} lng 经度
 * @returns {Promise} 兼容格式
 */
export const reverseGeocode = async (lat, lng) => {
  const res = await amapRequest(`${BASE}/v3/geocode/regeo`, {
    location: `${lng},${lat}`,
    extensions: 'base'
  })

  const regeo = res.regeocode || {}
  const comp = regeo.addressComponent || {}

  return {
    data: {
      formatted_address: regeo.formatted_address || '',
      addressComponent: {
        city: comp.city || comp.province || '',
        district: comp.district || '',
        province: comp.province || '',
        street: comp.street || '',
        street_number: comp.streetNumber || ''
      }
    }
  }
}

// ---------- 辅助：坐标顺序检测与翻转 ----------
/**
 * 高德要求 "lng,lat"
 * 如果传入的是 "lat,lng"（纬度在前，即第一个值 > 90 不可能是经度，
 * 或第一个值 < 第二个值 且第二个值看起来像经度），则翻转
 */
function flipIfNeeded(coord) {
  if (!coord || typeof coord !== 'string') return coord
  const parts = coord.split(',').map(Number)
  if (parts.length !== 2) return coord

  const [a, b] = parts
  // 中国范围：经度 73-136，纬度 3-54
  // 如果第一个数字像纬度（3-54）且第二个像经度（73-136），翻转
  if (a >= 3 && a <= 54 && b >= 73 && b <= 136) {
    return `${b},${a}`
  }
  return coord
}
