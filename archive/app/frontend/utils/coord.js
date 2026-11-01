/**
 * utils/coord.js
 * 国内坐标系转换工具
 *
 * 背景：百度地图 API 使用 BD09 坐标系，浏览器 Geolocation 返回 WGS84，
 * uni.getLocation 返回 GCJ02。若不做转换直接混用，在国内会有 300~500 米偏差。
 *
 * 转换链：WGS84 → GCJ02（火星坐标系）→ BD09（百度坐标系）
 */

const PI = 3.1415926535897932384626
const A = 6378245.0
const EE = 0.00669342162296594323

const outOfChina = (lat, lng) => {
  return lng < 72.004 || lng > 137.8347 || lat < 0.8293 || lat > 55.8271
}

const transformLat = (x, y) => {
  let ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x))
  ret += ((20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0) / 3.0
  ret += ((20.0 * Math.sin(y * PI) + 40.0 * Math.sin((y / 3.0) * PI)) * 2.0) / 3.0
  ret += ((160.0 * Math.sin((y / 12.0) * PI) + 320 * Math.sin((y * PI) / 30.0)) * 2.0) / 3.0
  return ret
}

const transformLng = (x, y) => {
  let ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x))
  ret += ((20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0) / 3.0
  ret += ((20.0 * Math.sin(x * PI) + 40.0 * Math.sin((x / 3.0) * PI)) * 2.0) / 3.0
  ret += ((150.0 * Math.sin((x / 12.0) * PI) + 300.0 * Math.sin((x / 30.0) * PI)) * 2.0) / 3.0
  return ret
}

/**
 * WGS84 → GCJ02
 */
export const wgs84ToGcj02 = (lat, lng) => {
  if (outOfChina(lat, lng)) return { lat, lng }
  let dLat = transformLat(lng - 105.0, lat - 35.0)
  let dLng = transformLng(lng - 105.0, lat - 35.0)
  const radLat = (lat / 180.0) * PI
  let magic = Math.sin(radLat)
  magic = 1 - EE * magic * magic
  const sqrtMagic = Math.sqrt(magic)
  dLat = (dLat * 180.0) / (((A * (1 - EE)) / (magic * sqrtMagic)) * PI)
  dLng = (dLng * 180.0) / ((A / sqrtMagic) * Math.cos(radLat) * PI)
  return { lat: lat + dLat, lng: lng + dLng }
}

/**
 * GCJ02 → BD09
 */
export const gcj02ToBd09 = (lat, lng) => {
  const x = lng
  const y = lat
  const z = Math.sqrt(x * x + y * y) + 0.00002 * Math.sin(y * PI)
  const theta = Math.atan2(y, x) + 0.000003 * Math.cos(x * PI)
  return {
    lat: z * Math.sin(theta) + 0.006,
    lng: z * Math.cos(theta) + 0.0065
  }
}

/**
 * WGS84 → BD09（浏览器定位 → 百度地图）
 */
export const wgs84ToBd09 = (lat, lng) => {
  const gcj = wgs84ToGcj02(lat, lng)
  return gcj02ToBd09(gcj.lat, gcj.lng)
}
