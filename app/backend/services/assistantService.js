/**
 * services/assistantService.js
 * 语音助手命令解析服务（规则优先 + LLM 预留）
 */

const LLM_SYSTEM_PROMPT_TEMPLATE = `你是智能盲杖系统的命令解析器。
你的任务是把用户自然语言解析成一个 JSON 对象。

严格要求：
1) 只能输出 JSON，不允许输出任何解释、注释、前后缀文本。
2) intent 只能是以下之一：
   - start_navigation
   - cancel_navigation
   - connect_device
   - disconnect_device
   - run_device_diagnostic
   - get_battery_status
   - get_device_status
   - switch_mode
   - open_page
   - set_voice_switch
   - start_demo
3) 字段规则：
   - start_navigation 必须输出 destination（字符串）
   - open_page 必须输出 page（可选值：home, device, diagnostic, navigation）
   - switch_mode 必须输出 mode（可选值：map, zoom）
   - set_voice_switch 必须输出 value（布尔值 true/false）
4) 如果用户意图无法识别，输出：
   {"intent":"unknown"}
5) 不要臆造参数，不要输出 null 字段，不要输出数组。`;

function normalizeText(text) {
  return String(text || '').trim().replace(/\s+/g, '');
}

function extractDestination(normalized) {
  const patterns = [
    /(?:带我去|导航到|前往|去往|去|到)(.+)$/i
  ];

  for (const pattern of patterns) {
    const match = normalized.match(pattern);
    if (match && match[1]) {
      const destination = String(match[1]).trim();
      if (destination) return destination;
    }
  }

  return '';
}

function parseCommandByRule(text) {
  const raw = String(text || '').trim();
  const normalized = normalizeText(raw);

  if (!normalized) {
    return { intent: 'unknown' };
  }

  if (/(打开语音播报|开启语音播报|打开语音提醒|开启语音提醒|恢复语音播报)/.test(normalized)) {
    return { intent: 'set_voice_switch', value: true };
  }

  if (/(关闭语音播报|关闭语音提醒|静音播报|停止语音播报)/.test(normalized)) {
    return { intent: 'set_voice_switch', value: false };
  }

  if (/(打开设备页|跳转到设备页|去设备页|打开设备界面|进入设备页)/.test(normalized)) {
    return { intent: 'open_page', page: 'device' };
  }

  if (/(打开诊断页|跳转到诊断页|去诊断页|打开检测页|进入诊断页|打开设备检测页)/.test(normalized)) {
    return { intent: 'open_page', page: 'diagnostic' };
  }

  if (/(打开首页|回首页|跳转到首页|进入首页|去首页|返回首页)/.test(normalized)) {
    return { intent: 'open_page', page: 'home' };
  }

  if (/(打开导航页|跳转到导航页|去导航页|进入导航页|打开地图页)/.test(normalized)) {
    return { intent: 'open_page', page: 'navigation' };
  }

  if (/(切换到地图模式|打开地图模式|进入地图模式)/.test(normalized)) {
    return { intent: 'switch_mode', mode: 'map' };
  }

  if (/(切换到放大模式|打开放大模式|进入放大模式)/.test(normalized)) {
    return { intent: 'switch_mode', mode: 'zoom' };
  }

  if (/(连接设备|连接盲杖|连接我的设备|连接一下设备|开始连接设备)/.test(normalized)) {
    return { intent: 'connect_device' };
  }

  if (/(断开设备|断开盲杖|断开连接|关闭设备连接)/.test(normalized)) {
    return { intent: 'disconnect_device' };
  }

  if (/(检测设备|开始检测|设备检测|检查设备|检测一下设备|开始设备检测|诊断设备|检查设备状态)/.test(normalized)) {
    return { intent: 'run_device_diagnostic' };
  }

  if (/(设备状态|设备是否正常|设备有没有异常|播报设备状态)/.test(normalized)) {
    return { intent: 'get_device_status' };
  }

  if (/(查看电量|查询电量|设备还有多少电|还有多少电|电池还有多少|剩余电量|当前电量)/.test(normalized)) {
    return { intent: 'get_battery_status' };
  }

  if (/(取消导航|停止导航|结束导航|退出导航)/.test(normalized)) {
    return { intent: 'cancel_navigation' };
  }

  if (/(开始演示|进入演示模式|打开展示模式|打开演示模式)/.test(normalized)) {
    return { intent: 'start_demo' };
  }

  const destination = extractDestination(normalized);
  if (destination) {
    return { intent: 'start_navigation', destination };
  }

  if (/(^医院$|^最近的医院$|^附近的医院$|^附近医院$)/.test(normalized)) {
    return { intent: 'start_navigation', destination: normalized };
  }

  return { intent: 'unknown' };
}

async function parseCommandWithLLM(text) {
  void text;
  return null;
}

function validateLLMResult(result) {
  if (!result || typeof result !== 'object') return null;
  if (!result.intent || typeof result.intent !== 'string') return null;

  const allowedIntents = new Set([
    'start_navigation',
    'cancel_navigation',
    'connect_device',
    'disconnect_device',
    'run_device_diagnostic',
    'get_battery_status',
    'get_device_status',
    'switch_mode',
    'open_page',
    'set_voice_switch',
    'start_demo',
    'unknown'
  ]);

  if (!allowedIntents.has(result.intent)) {
    return null;
  }

  switch (result.intent) {
    case 'start_navigation':
      if (typeof result.destination !== 'string' || !result.destination.trim()) return null;
      return { intent: 'start_navigation', destination: result.destination.trim() };

    case 'open_page':
      if (!['home', 'device', 'diagnostic', 'navigation'].includes(result.page)) return null;
      return { intent: 'open_page', page: result.page };

    case 'switch_mode':
      if (!['map', 'zoom'].includes(result.mode)) return null;
      return { intent: 'switch_mode', mode: result.mode };

    case 'set_voice_switch':
      if (typeof result.value !== 'boolean') return null;
      return { intent: 'set_voice_switch', value: result.value };

    case 'cancel_navigation':
    case 'connect_device':
    case 'disconnect_device':
    case 'run_device_diagnostic':
    case 'get_battery_status':
    case 'get_device_status':
    case 'start_demo':
    case 'unknown':
      return { intent: result.intent };

    default:
      return null;
  }
}

async function parseCommand(text) {
  const ruleResult = parseCommandByRule(text);
  if (ruleResult.intent !== 'unknown') {
    return ruleResult;
  }

  const llmResult = await parseCommandWithLLM(text);
  const validated = validateLLMResult(llmResult);
  if (validated) {
    return validated;
  }

  return { intent: 'unknown' };
}

module.exports = {
  parseCommand,
  parseCommandByRule,
  parseCommandWithLLM,
  validateLLMResult,
  normalizeText,
  extractDestination,
  LLM_SYSTEM_PROMPT_TEMPLATE
};