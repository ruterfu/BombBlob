// 登录（游客 / 8 位 ID / GitHub）+ WebSocket 实时通信（自动重连）
//
// 不做自动登录：localStorage 不保存任何登录凭证，只记住上次的 8 位游客 ID，
// 下次打开时填回输入框，仍然要玩家自己点「登录」。GitHub 每次都要授权一次。
// 登录请求与响应经过 RSA + AES-128-GCM 加密；登录后拿到的 AES-128 会话密钥只存在内存中，
// WebSocket 上的所有消息都用它加密（见 secure.js）。
import { sealedPost, Channel, cryptoAvailable } from './secure.js';

const LAST_ID_KEY = 'bb_last_id';
localStorage.removeItem('bb_token'); // 清掉旧版本保存的自动登录 token

/** 上次登录的 8 位游客 ID（只用于填回输入框） */
export function savedId() {
  const id = localStorage.getItem(LAST_ID_KEY) || '';
  return id.length === 8 && [...id].every((c) => c >= '0' && c <= '9') ? id : '';
}

function rememberId(user) {
  if (user?.provider === 'guest') localStorage.setItem(LAST_ID_KEY, user.id);
}

/** 服务器返回的错误：只有错误码（code），文字由 i18n 翻译 */
export class ApiError extends Error {
  constructor(code, status) {
    super(code);
    this.code = code;
    this.status = status;
  }
}
export class UnknownIdError extends ApiError {}

/** 全局文本规则（与服务器 backend/textrule.py 一致）：去掉所有空白后，只能是中文、英文字母、数字 */
function charOk(ch) {
  const o = ch.codePointAt(0);
  return (o >= 0x30 && o <= 0x39) || (o >= 0x41 && o <= 0x5a) || (o >= 0x61 && o <= 0x7a)
    || (o >= 0x4e00 && o <= 0x9fff) || (o >= 0x3400 && o <= 0x4dbf) || (o >= 0xf900 && o <= 0xfaff)
    || (o >= 0x20000 && o <= 0x323af);
}
/** 去掉所有空白（空格、全角空格、换行……） */
export const stripSpaces = (s) => Array.from(String(s ?? '').normalize('NFKC')).filter((ch) => ch.trim() !== '').join('');
/** 聊天消息：不限制字符，只合并多余空白、去掉首尾（服务器还会去掉不可见的控制字符）。只当作纯文本显示 */
export function cleanChat(s) {
  return String(s ?? '').split(/\s+/u).filter(Boolean).join(' ');
}
/** 返回清理后的文本；含不允许的字符时返回 null */
export function cleanText(s) {
  const v = stripSpaces(s);
  return Array.from(v).every(charOk) ? v : null;
}

/** 上报前把协议值转成符合文本规则的形式：zh-HK → zhHK */
function wire(msg) {
  if (typeof msg.lang === 'string' && msg.lang.includes('-')) msg = { ...msg, lang: wireLang(msg.lang) };
  return msg;
}
export const wireLang = (l) => String(l || '').split('-').join('');

async function postJson(url, body) {
  if (!cryptoAvailable()) throw new ApiError('insecure_context', 0);
  try {
    const { status, data } = await sealedPost(url, wire(body));
    return { r: { ok: status >= 200 && status < 300, status }, data };
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError('network', 0);
  }
}

/** 新建游客账号 */
export async function guestLogin({ name, skin, hat, lang }) {
  const { r, data } = await postJson('/api/guest', { name, skin, hat, lang });
  if (!r.ok) throw new ApiError(data.code || 'unknown', r.status);
  rememberId(data.user);
  return data; // { session, key, user }
}

/** 凭 8 位 ID 登录已有的游客账号 */
export async function idLogin(id, lang) {
  const { r, data } = await postJson('/api/login', { id, lang });
  if (data.code === 'unknown_id') throw new UnknownIdError(data.code, r.status);
  if (!r.ok) throw new ApiError(data.code || 'unknown', r.status);
  rememberId(data.user);
  return data;
}

/** 服务器开启了哪些登录方式：{ guest, github }（进入登录页时请求 /login-info） */
export async function fetchLoginConfig() {
  const r = await fetch('/api/login-info');
  return r.json();
}

/** GitHub 回跳后，用一次性交换码换取登录凭证 */
export async function oauthExchange(code) {
  const { r, data } = await postJson('/api/oauth/exchange', { code });
  if (!r.ok) throw new ApiError(data.code || 'unknown', r.status);
  return data;
}

export class Connection {
  static STALL_MS = 4000;
  /** login = 登录响应：{ session, key }（key 是 AES-128 会话密钥，base64） */
  constructor(login, handlers) {
    this.session = login.session;
    this.key = login.key;
    this.handlers = handlers; // { message(msg), open(), close(code) }
    this.ws = null;
    this.retry = 0;
    this.closedByUser = false;
    this.ping = 0;
    this.lastMsgAt = performance.now();
    this.connect();
    this.pingTimer = setInterval(() => this.send({ t: 'ping', ts: performance.now() }), 1000);
    // 卡顿检测：每秒都有 ping/pong，超过 STALL_MS 没收到任何消息就认为连接已断，主动断开并重连
    this.watchdog = setInterval(() => {
      const ws = this.ws;
      if (ws && ws.readyState === WebSocket.OPEN && this.channel && performance.now() - this.lastMsgAt > Connection.STALL_MS) {
        ws.close(4003, 'stall');
        this.onDrop(ws, 4003);
      }
    }, 500);
  }

  connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/api/gamesocket?session=${encodeURIComponent(this.session)}`);
    ws.binaryType = 'arraybuffer';
    this.ws = ws;
    this.channel = null;
    this.tx = Promise.resolve();
    this.rx = Promise.resolve();
    let channelP = null; // 握手完成前到达的加密帧排队等待，不能丢（丢一帧后续序号就全错了）
    ws.onmessage = (ev) => {
      // 第一帧（明文）：{t:'hello', c:连接号}，据此建立加密通道；之后只接受加密的二进制帧
      if (typeof ev.data === 'string') {
        let hello;
        try { hello = JSON.parse(ev.data); } catch { return; }
        if (hello.t !== 'hello' || channelP) return;
        channelP = Channel.create(this.key, hello.c);
        this.rx = this.rx.then(() => channelP).then((ch) => {
          if (this.ws !== ws) return;
          this.channel = ch;
          this.retry = 0;
          this.lastMsgAt = performance.now();
          this.online = true;
          this.send({ t: 'ping', ts: performance.now() });
          this.handlers.open?.();
        });
        return;
      }
      if (!channelP) return;
      const data = ev.data;
      this.lastMsgAt = performance.now();
      // 按到达顺序串行解密（帧序号随顺序递增）
      this.rx = this.rx.then(() => channelP).then((ch) => ch.open(data)).then((text) => {
        if (this.ws !== ws) return;
        const msg = JSON.parse(text);
        if (msg.t === 'pong') {
          this.ping = Math.round(performance.now() - msg.ts);
          return;
        }
        this.handlers.message(msg);
      }).catch(() => { if (this.ws === ws) ws.close(4002); }); // 解密失败：断开后自动重连
    };
    ws.onclose = (ev) => this.onDrop(ws, ev.code);
  }

  /** 连接断开（网络断开 / 卡顿超时）：通知界面进入重连状态，按退避间隔重连 */
  onDrop(ws, code) {
    if (this.ws !== ws || ws.dropped) return;
    ws.dropped = true;
    this.online = false;
    this.channel = null;
    if (this.closedByUser) return; // 主动关闭（退出登录等）：不是断线，不通知界面、不重连
    this.handlers.close?.(code, this.retry);
    if (code === 4001 || code === 4000) return;
    const delay = Math.min(4000, 400 * 2 ** this.retry++);
    setTimeout(() => { if (!this.closedByUser) this.connect(); }, delay);
  }

  send(msg) {
    const ws = this.ws, ch = this.channel;
    if (!ws || ws.readyState !== WebSocket.OPEN || !ch) return;
    const p = ch.seal(JSON.stringify(msg.lang ? wire(msg) : msg)); // 序号在此同步分配
    this.tx = this.tx.then(() => p).then((buf) => {
      if (this.ws === ws && ws.readyState === WebSocket.OPEN) ws.send(buf);
    }).catch(() => {});
  }

  close() {
    this.closedByUser = true;
    clearInterval(this.pingTimer);
    clearInterval(this.watchdog);
    this.ws?.close();
  }
}
