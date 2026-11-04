// 传输加密（与 backend/secure.py 对应）
//
// 登录：随机生成一次性 AES-128 密钥 k → 用写死的 RSA 公钥（RSA-OAEP / SHA-256）加密 k，
//       请求体用 AES-128-GCM(k) 加密；服务器的响应也用 k 加密，其中带回本次会话的 AES-128 密钥 K。
// 之后：WebSocket 全部是 AES-128-GCM(K) 二进制帧，IV = 方向 ‖ 连接号 ‖ 帧序号（双方各自计数，不随帧发送）。
//
// 需要浏览器的 WebCrypto（HTTPS 或 localhost 等安全上下文）。

import { RSA_PUBLIC_KEY } from './rsa-public.js';

const enc = new TextEncoder();
const dec = new TextDecoder();
const C2S = 1, S2C = 2;

export const b64 = (buf) => {
  const u = new Uint8Array(buf);
  let s = '';
  for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000));
  return btoa(s);
};
export const unb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

/** 当前环境能否使用 WebCrypto（http 非本机访问时浏览器不提供） */
export const cryptoAvailable = () => !!(globalThis.isSecureContext && globalThis.crypto?.subtle);

let rsaKeyP = null;
function rsaKey() {
  rsaKeyP ||= crypto.subtle.importKey('spki', unb64(RSA_PUBLIC_KEY), { name: 'RSA-OAEP', hash: 'SHA-256' }, false, ['encrypt']);
  return rsaKeyP;
}

const aesKey = (raw) => crypto.subtle.importKey('raw', raw, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt']);

/**
 * 加密的 POST：返回 { status, data }。
 * 请求 {ek, iv, ct}；响应 {iv, ct}（用同一个一次性密钥解密）。
 */
export async function sealedPost(url, body) {
  const raw = crypto.getRandomValues(new Uint8Array(16));
  const [key, ek] = await Promise.all([aesKey(raw), rsaKey().then((pk) => crypto.subtle.encrypt({ name: 'RSA-OAEP' }, pk, raw))]);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, enc.encode(JSON.stringify(body)));
  // 15 秒超时：网络或服务器卡住时不会无限等待（超时按网络错误处理，界面会恢复登录表单）
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ek: b64(ek), iv: b64(iv), ct: b64(ct) }),
    signal: AbortSignal.timeout ? AbortSignal.timeout(15000) : undefined,
  });
  const wire = await r.json().catch(() => ({}));
  if (!wire.ct) return { status: r.status, data: wire };
  const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: unb64(wire.iv) }, key, unb64(wire.ct));
  return { status: r.status, data: JSON.parse(dec.decode(pt)) };
}

/** 一个 WebSocket 连接上的加密通道 */
export class Channel {
  static async create(keyB64, conn) {
    const ch = new Channel();
    ch.key = await aesKey(unb64(keyB64));
    ch.conn = conn >>> 0;
    ch.outCtr = 0;
    ch.inCtr = 0;
    return ch;
  }

  iv(dir, ctr) {
    const iv = new Uint8Array(12);
    iv[0] = dir;
    new DataView(iv.buffer).setUint32(1, this.conn);
    let c = ctr;
    for (let i = 11; i >= 5; i--) { iv[i] = c % 256; c = Math.floor(c / 256); }
    return iv;
  }

  /** 加密：序号在调用时同步分配，调用顺序即发送顺序 */
  seal(text) {
    const iv = this.iv(C2S, this.outCtr++);
    return crypto.subtle.encrypt({ name: 'AES-GCM', iv }, this.key, enc.encode(text));
  }

  /** 解密：同样按到达顺序同步分配序号 */
  async open(buf) {
    const iv = this.iv(S2C, this.inCtr++);
    return dec.decode(await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, this.key, buf));
  }
}
