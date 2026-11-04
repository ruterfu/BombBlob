"""测试用的加密客户端：与网页 public/js/secure.js 使用同一套协议。"""
import json

from aiohttp import WSMsgType

from backend import secure

TEST_RSA = secure.generate_key()  # 测试服务器使用的 RSA 私钥（公钥给客户端）


class Resp:
    def __init__(self, status: int, data: dict) -> None:
        self.status = status
        self.data = data

    async def json(self) -> dict:
        return self.data


async def spost(client, path: str, body: dict, key=TEST_RSA) -> Resp:
    """加密的登录请求：RSA 包裹一次性 AES 密钥，响应用同一密钥解密。"""
    k, wire = secure.client_seal_request(key.public_key(), body)
    r = await client.post(path, json=wire)
    return Resp(r.status, secure.client_open_response(k, await r.json()))


class _Msg:
    def __init__(self, type_, data):
        self.type = type_
        self.data = data


class SecureWS:
    """包装 aiohttp WebSocket：发送 / 接收自动加解密（接口与原来的 send_json / receive_json 一致）。"""

    def __init__(self, ws, channel: secure.Channel) -> None:
        self.ws = ws
        self.channel = channel
        self.pending = []  # 建角色期间收到、尚未交给测试的消息

    @property
    def closed(self) -> bool:
        return self.ws.closed

    @property
    def close_code(self):
        return self.ws.close_code

    async def send_json(self, obj) -> None:
        await self.ws.send_bytes(self.channel.seal(json.dumps(obj)))

    async def send_raw(self, data: bytes) -> None:
        await self.ws.send_bytes(data)

    async def receive(self, timeout=None):
        if self.pending:
            return _Msg(WSMsgType.TEXT, self.pending.pop(0))
        msg = await self.ws.receive(timeout=timeout)
        if msg.type == WSMsgType.BINARY:
            return _Msg(WSMsgType.TEXT, self.channel.open(msg.data))
        return msg

    async def receive_json(self, timeout=None):
        msg = await self.receive(timeout)
        if msg.type != WSMsgType.TEXT:
            raise AssertionError(f"socket closed: {msg}")
        return json.loads(msg.data)

    async def close(self) -> None:
        await self.ws.close()


async def sws(client, login: dict, create_character: bool = True) -> SecureWS:
    """用登录响应（session + key）建立加密 WebSocket。
    新账号默认先创建角色（沿用当前名字 / 外观），期间收到的其他消息原样保留给测试。"""
    ws = await client.ws_connect("/api/gamesocket?session=" + login["session"])
    hello = await ws.receive_json()
    assert hello["t"] == "hello", hello
    sw = SecureWS(ws, secure.Channel(secure.unb64(login["key"]), hello["c"], secure.C2S))
    u = login.get("user") or {}
    if create_character and u.get("hasCharacter") is False:
        await sw.send_json({"t": "createCharacter", "name": u["name"], "skin": u["skin"], "hat": u["hat"]})
        while True:
            m = await ws.receive(timeout=5)
            text = sw.channel.open(m.data)
            data = json.loads(text)
            if data["t"] == "me" and data["user"]["hasCharacter"]:
                login["user"] = data["user"]
                break
            sw.pending.append(text)
    return sw
