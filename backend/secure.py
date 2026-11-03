"""传输加密（在 HTTPS 之外再加一层；也让 http 部署时被动抓包看不到内容）。

流程
  1. 网页里写死 RSA-2048 公钥（public/js/rsa-public.js），服务器持有私钥（RSA_PRIVATE_KEY）。
  2. 登录请求：网页随机生成一次性 AES-128 密钥 k，用 RSA-OAEP(SHA-256) 加密 k，
     再用 AES-128-GCM(k) 加密请求体：{ek, iv, ct}。
  3. 服务器解密后完成登录，生成本次会话的 AES-128 密钥 K（即「唯一 token」），
     用 k 加密整个响应（含 K）返回。K 永远不会以明文出现在网络上。
  4. 之后的 WebSocket 全部是二进制帧：AES-128-GCM(K)。
     IV = 方向(1 字节) ‖ 连接号(4 字节) ‖ 帧序号(7 字节)：双方各自计数，不在帧里传 IV，
     因此截获的帧无法重放、调换顺序或拿到另一个连接里使用（GCM 校验会失败，连接被关闭）。
     会话 ID = SHA-256(K) 的前 16 字节（只用来查找密钥，没有 K 无法通信）。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PUBLIC_JS = Path(__file__).resolve().parent.parent / "public" / "js" / "rsa-public.js"
OAEP = padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
KEY_BYTES = 16  # AES-128
C2S, S2C = 1, 2  # IV 中的方向字节


class CryptoError(Exception):
    """解密 / 校验失败（篡改、重放、密钥不对）。"""


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def unb64(s: object) -> bytes:
    try:
        return base64.b64decode(str(s), validate=True)
    except (ValueError, TypeError) as e:
        raise CryptoError("bad base64") from e


# ---------- RSA 密钥 ----------
def generate_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def private_pem(key: rsa.RSAPrivateKey) -> str:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


def public_spki_b64(key: rsa.RSAPrivateKey) -> str:
    """网页 WebCrypto importKey('spki') 使用的公钥（DER，base64）。"""
    return b64(key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))


def public_js(key: rsa.RSAPrivateKey) -> str:
    return (
        "// 由 scripts/gen_rsa.py 生成：服务器 RSA-2048 公钥（SPKI / DER，base64）。\n"
        "// 对应的私钥只保存在服务器（环境变量 RSA_PRIVATE_KEY），不要提交到仓库。\n"
        f"export const RSA_PUBLIC_KEY = '{public_spki_b64(key)}';\n"
    )


EXAMPLE_ENV = Path(__file__).resolve().parent.parent / ".env.example"


def default_example_key() -> str:
    """仓库里 .env.example 附带的公开默认私钥（克隆后可直接运行；正式部署应替换）。"""
    try:
        for line in EXAMPLE_ENV.read_text("utf-8").splitlines():
            if line.startswith("RSA_PRIVATE_KEY="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def load_private_key(value: str | None = None) -> rsa.RSAPrivateKey | None:
    """RSA_PRIVATE_KEY：PEM 文本，或 PEM 的 base64（便于 docker run -e 单行传入）。
    未设置时退回 .env.example 中的公开默认密钥。"""
    raw = (value if value is not None else os.environ.get("RSA_PRIVATE_KEY", "")).strip()
    if not raw and value is None:
        raw = default_example_key()
    if not raw:
        return None
    pem = raw.replace("\\n", "\n")
    if "BEGIN" not in pem:
        pem = base64.b64decode(pem).decode()
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
        raise ValueError("RSA_PRIVATE_KEY 必须是 2048 位以上的 RSA 私钥")
    return key


def is_default_key(key: rsa.RSAPrivateKey) -> bool:
    d = default_example_key()
    return bool(d) and public_spki_b64(key) == public_spki_b64(load_private_key(d))


def check_public_js(key: rsa.RSAPrivateKey) -> bool:
    """网页里写死的公钥必须和服务器私钥配对，否则所有登录都会失败。"""
    try:
        return f"'{public_spki_b64(key)}'" in PUBLIC_JS.read_text("utf-8")
    except OSError:
        return False


# ---------- 登录请求（RSA + AES-GCM 混合加密） ----------
def open_request(key: rsa.RSAPrivateKey, body: object) -> tuple[bytes, dict]:
    """解开 {ek, iv, ct}：返回 (一次性密钥 k, 请求内容)。"""
    if not isinstance(body, dict):
        raise CryptoError("bad request")
    try:
        k = key.decrypt(unb64(body.get("ek")), OAEP)
    except ValueError as e:
        raise CryptoError("rsa") from e
    if len(k) != KEY_BYTES:
        raise CryptoError("key size")
    data = aead_open(k, unb64(body.get("iv")), unb64(body.get("ct")))
    try:
        obj = json.loads(data)
    except ValueError as e:
        raise CryptoError("json") from e
    if not isinstance(obj, dict):
        raise CryptoError("json")
    return k, obj


def seal_response(k: bytes, obj: dict) -> dict:
    iv = secrets.token_bytes(12)
    return {"iv": b64(iv), "ct": b64(AESGCM(k).encrypt(iv, json.dumps(obj, ensure_ascii=False).encode(), None))}


def aead_open(k: bytes, iv: bytes, ct: bytes) -> bytes:
    if len(iv) != 12:
        raise CryptoError("iv")
    try:
        return AESGCM(k).decrypt(iv, ct, None)
    except InvalidTag as e:
        raise CryptoError("tag") from e


# ---------- 会话密钥 ----------
def new_session_key() -> tuple[str, bytes]:
    """返回 (会话 ID, AES-128 会话密钥)。会话 ID 由密钥派生。"""
    k = secrets.token_bytes(KEY_BYTES)
    return session_id(k), k


def session_id(k: bytes) -> str:
    return hashlib.sha256(k).hexdigest()[:32]


class Channel:
    """一个 WebSocket 连接上的加密通道（每个方向独立计数）。"""

    MAX_CTR = 1 << 56

    def __init__(self, key: bytes, conn: int, side: int) -> None:
        self.aead = AESGCM(key)
        self.conn = conn & 0xFFFFFFFF
        self.out_dir, self.in_dir = (S2C, C2S) if side == S2C else (C2S, S2C)
        self.out_ctr = 0
        self.in_ctr = 0

    def _iv(self, direction: int, ctr: int) -> bytes:
        if ctr >= self.MAX_CTR:
            raise CryptoError("counter exhausted")
        return bytes([direction]) + self.conn.to_bytes(4, "big") + ctr.to_bytes(7, "big")

    def seal(self, text: str) -> bytes:
        iv = self._iv(self.out_dir, self.out_ctr)
        self.out_ctr += 1
        return self.aead.encrypt(iv, text.encode(), None)

    def open(self, data: bytes) -> str:
        iv = self._iv(self.in_dir, self.in_ctr)
        try:
            text = self.aead.decrypt(iv, data, None).decode()
        except (InvalidTag, UnicodeDecodeError) as e:
            raise CryptoError("frame") from e
        self.in_ctr += 1
        return text


# ---------- 客户端实现（测试与压测脚本使用，和网页 secure.js 行为一致） ----------
def client_seal_request(public_key, obj: dict) -> tuple[bytes, dict]:
    k = secrets.token_bytes(KEY_BYTES)
    iv = secrets.token_bytes(12)
    body = {
        "ek": b64(public_key.encrypt(k, OAEP)),
        "iv": b64(iv),
        "ct": b64(AESGCM(k).encrypt(iv, json.dumps(obj).encode(), None)),
    }
    return k, body


def client_open_response(k: bytes, body: dict) -> dict:
    if "ct" not in body:
        return body  # 未加密的错误（例如请求格式错误）
    return json.loads(aead_open(k, unb64(body["iv"]), unb64(body["ct"])))
