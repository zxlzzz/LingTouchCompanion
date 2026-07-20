/**
 * routes/map.js
 * 地图相关路由
 *
 * GET  /api/map/search           - 地点关键词检索
 * POST /api/map/walk-route       - 步行路线规划
 * GET  /api/map/reverse-geocode  - 逆地理编码
 */

const express = require('express');
const router = express.Router();
const baiduMap = require('../services/baiduMap');

/**
 * GET /api/map/search
 * Query:
 *   query      {string} 必填
 *   region     {string} 必填
 *   page_size  {number} 可选
 *   page_num   {number} 可选
 */
router.get('/search', async (req, res) => {
  try {
    const { query, region, page_size, page_num } = req.query;

    if (!query || !region) {
      return res.status(400).json({
        code: 400,
        message: '参数错误：query 和 region 为必填项',
        data: null,
      });
    }

    const result = await baiduMap.searchPlace({
      query,
      region,
      page_size: page_size ? parseInt(page_size, 10) : 10,
      page_num: page_num ? parseInt(page_num, 10) : 0,
    });

    return res.json({
      code: 200,
      message: 'success',
      data: result,
    });
  } catch (err) {
    console.error('[GET /api/map/search] 错误:', err.message);
    return res.status(500).json({
      code: 500,
      message: err.message || '服务器内部错误',
      data: null,
    });
  }
});

/**
 * POST /api/map/walk-route
 * Body:
 *   origin       {string} 必填，格式 "纬度,经度"
 *   destination  {string} 必填，格式 "纬度,经度"
 *   coord_type   {string} 可选，默认 "bd09ll"
 *   steps_info   {number} 可选，默认 1
 */
router.post('/walk-route', async (req, res) => {
  try {
    const { origin, destination, coord_type, steps_info } = req.body;

    if (!origin || !destination) {
      return res.status(400).json({
        code: 400,
        message: '参数错误：origin 和 destination 为必填项',
        data: null,
      });
    }

    const result = await baiduMap.getWalkingRoute({
      origin,
      destination,
      coord_type: coord_type || 'bd09ll',
      steps_info: steps_info === undefined ? 1 : Number(steps_info),
    });

    return res.json({
      code: 200,
      message: 'success',
      data: result,
    });
  } catch (err) {
    console.error('[POST /api/map/walk-route] 错误:', err.message);
    return res.status(500).json({
      code: 500,
      message: err.message || '服务器内部错误',
      data: null,
    });
  }
});

/**
 * GET /api/map/reverse-geocode
 * Query:
 *   lat {string|number} 必填
 *   lng {string|number} 必填
 */
router.get('/reverse-geocode', async (req, res) => {
  try {
    const { lat, lng } = req.query;

    if (!lat || !lng) {
      return res.status(400).json({
        code: 400,
        message: '参数错误：lat 和 lng 为必填项',
        data: null,
      });
    }

    const result = await baiduMap.reverseGeocode({
      lat,
      lng,
    });

    return res.json({
      code: 200,
      message: 'success',
      data: result,
    });
  } catch (err) {
    console.error('[GET /api/map/reverse-geocode] 错误:', err.message);
    return res.status(500).json({
      code: 500,
      message: err.message || '服务器内部错误',
      data: null,
    });
  }
});

module.exports = router;