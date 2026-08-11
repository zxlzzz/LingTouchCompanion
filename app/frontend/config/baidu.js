/**
 * 百度地图 AK 统一配置
 *
 * 两个 AK 分属不同应用类型，不可混用：
 * - BAIDU_JS_AK：Web端(JS API) Key，仅用于页面地图渲染（BMap），已校验可用
 * - BAIDU_SERVER_AK：服务端 AK，配置在 backend/.env 的 BAIDU_AK，
 *   用于 REST 接口（地点搜索 / 步行路线 / 逆地理编码），
 *   由后端代理调用，不暴露到前端代码中
 */

export const BAIDU_JS_AK = 'XkyY4z1bG6iRfPXcGeyuPokCcyNlBiVx'
