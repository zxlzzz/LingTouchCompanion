require('dotenv').config();

module.exports = {
  BAIDU_AK: process.env.BAIDU_AK,
  BASE_URL: 'https://api.map.baidu.com',
  PLACE_SEARCH_URL: 'https://api.map.baidu.com/place/v2/search',
  WALKING_ROUTE_URL: 'https://api.map.baidu.com/directionlite/v1/walking',
  REVERSE_GEOCODING_URL: 'https://api.map.baidu.com/reverse_geocoding/v3',
  TIMEOUT: 8000,
};
