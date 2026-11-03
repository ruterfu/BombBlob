// 游客登录（一次性 token）+ WebSocket 实时通信（自动重连）
//
// localStorage 里只保存一个「一次性登录 token」。每次用它登录后，服务器都会作废它
// 并返回一个新的 token，我们立刻覆盖保存。
// 登录请求与响应经过 RSA + AES-128-GCM 加密；登录后拿到的 AES-128 会话密钥只存在内存中，
// WebSocket 上的所有消息都用它加密（见 secure.js）。
import { sealedPost, Channel, cryptoAvailable } from './secure.js';

const TOKEN_KEY = 'bb_token';

export function savedToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function forgetToken() {
  localStorage.removeItem(TOKEN_KEY);
}

/** 服务器返回的错误：只有错误码（code），文字由 i18n 翻译 */
export class ApiError extends Error {
  constructor(code, status) {
    super(code);
    this.code = code;
    this.status = status;
  }
}
export class TokenInvalidError extends ApiError {}
export class UnknownIdError extends ApiError {}

async function postJson(url, body) {
  if (!cryptoAvailable()) throw new ApiError('insecure_context', 0);
  try {
    const { status, data } = await sealedPost(url, body);
    return { r: { ok: status >= 200 && status < 300, status }, data };
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError('network', 0);
  }
}

export async function guestLogin({ name, skin, hat, token, lang }) {
  const { r, data } = await postJson('/api/guest', { name, skin, hat, token, lang });
  if (data.code === 'token_invalid' || data.code === 'provider_disabled') {
    forgetToken();
    throw new TokenInvalidError(data.code, r.status);
  }
  if (!r.ok) throw new ApiError(data.code || 'unknown', r.status);
  localStorage.setItem(TOKEN_KEY, data.token); // 旧 token 已失效，保存新的
  return data; // { token, session, user }
}

/** 凭 8 位 ID 登录已有的游客账号 */
export async function idLogin(id, lang) {
  const { r, data } = await postJson('/api/login', { id, lang });
  if (data.code === 'unknown_id') throw new UnknownIdError(data.code, r.status);
  if (!r.ok) throw new ApiError(data.code || 'unknown', r.status);
  localStorage.setItem(TOKEN_KEY, data.token);
  return data;
}

/** 服务器开启了哪些登录方式：{ guest, github } */
export async function fetchLoginConfig() {
  const r = await fetch('/api/config');
  return r.json();
}

/** GitHub 回跳后，用一次性交换码换取登录凭证 */
export async function oauthExchange(code) {
  const { r, data } = await postJson('/api/oauth/exchange', { code });
  if (!r.ok) throw new ApiError(data.code || 'unknown', r.status);
  localStorage.setItem(TOKEN_KEY, data.token);
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
    const ws = new WebSocket(`${proto}://${location.host}/gamesocket?session=${encodeURIComponent(this.session)}`);
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
    this.handlers.close?.(code, this.retry);
    if (this.closedByUser || code === 4001 || code === 4000) return;
    const delay = Math.min(4000, 400 * 2 ** this.retry++);
    setTimeout(() => { if (!this.closedByUser) this.connect(); }, delay);
  }

  send(msg) {
    const ws = this.ws, ch = this.channel;
    if (!ws || ws.readyState !== WebSocket.OPEN || !ch) return;
    const p = ch.seal(JSON.stringify(msg)); // 序号在此同步分配
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
