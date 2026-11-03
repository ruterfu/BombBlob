"""压力测试：N 个真实客户端（游客账号 + WebSocket）同时游戏。

用法：
    .venv/bin/python scripts/loadtest.py --players 100 --seconds 40 [--url http://localhost:8000] [--pid <服务器PID>]

每个房间最多 6 人：每组第 1 个客户端建房，其余加入并准备，然后统一开局，
之后持续发送随机移动 / 放炸弹输入（每 0.12~0.35 秒一次，接近真人操作频率）。
输出：快照间隔抖动、输入→确认延迟、每客户端下行带宽、服务器 CPU / 内存。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import subprocess
import time

import aiohttp
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cryptography.hazmat.primitives.serialization import load_der_public_key  # noqa: E402

from backend import secure  # noqa: E402

# 和网页一样使用写死在 public/js/rsa-public.js 里的公钥
PUBLIC_KEY = load_der_public_key(secure.unb64(re.search(r"'([A-Za-z0-9+/=]+)'", secure.PUBLIC_JS.read_text()).group(1)))

DIRS = ["up", "down", "left", "right", None]


class Client:
    def __init__(self, idx: int):
        self.idx = idx
        self.gaps: list[float] = []
        self.lat: list[float] = []
        self.bytes = 0
        self.snaps = 0
        self.last = 0.0
        self.sent: dict[int, float] = {}
        self.acked = 0
        self.seq = 0
        self.uid = ""
        self.playing = False
        self.errors = 0


async def run_client(session, url, c: Client, is_host: bool, room_fut: asyncio.Future, ctl: dict):
    k, wire = secure.client_seal_request(PUBLIC_KEY, {"name": f"压测{c.idx}"})
    r = secure.client_open_response(k, await (await session.post(f"{url}/api/guest", json=wire)).json())
    c.uid = r["user"]["id"]
    raw_ws = await session.ws_connect(f"{url.replace('http', 'ws')}/gamesocket?session={r['session']}", max_msg_size=0)
    hello = await raw_ws.receive_json()
    ch = secure.Channel(secure.unb64(r["key"]), hello["c"], secure.C2S)

    class _WS:  # 加密包装
        async def send_json(self, obj):
            await raw_ws.send_bytes(ch.seal(json.dumps(obj)))

        async def close(self):
            await raw_ws.close()

    ws = _WS()

    async def reader():
        async for msg in raw_ws:
            if msg.type != aiohttp.WSMsgType.BINARY:
                break
            now = time.perf_counter()
            data = ch.open(msg.data)
            if not data.startswith('{"t":"s"'):
                d = json.loads(data)
                if d["t"] == "room" and is_host and not room_fut.done():
                    room_fut.set_result(d["room"]["id"])
                elif d["t"] == "error":
                    c.errors += 1
                continue
            c.bytes += len(data.encode())
            c.snaps += 1
            if c.last and c.playing:
                c.gaps.append((now - c.last) * 1000)
            c.last = now
            d = json.loads(data)
            if d["ph"] == "play":
                c.playing = True
            me = next((p for p in d["p"] if p["id"] == c.uid), None)
            if me and me["q"] > c.acked:
                for k in range(c.acked + 1, me["q"] + 1):
                    t0 = c.sent.pop(k, None)
                    if t0 and c.playing:
                        c.lat.append((now - t0) * 1000)
                c.acked = me["q"]

    rt = asyncio.create_task(reader())
    if is_host:
        await ws.send_json({"t": "createRoom", "name": f"压测房{c.idx}"})
    else:
        await ws.send_json({"t": "joinRoom", "id": await room_fut})
        await asyncio.sleep(0.3)
        await ws.send_json({"t": "ready", "v": True})
    await ctl["start"].wait()
    if is_host:
        await ws.send_json({"t": "start"})
    while time.perf_counter() < ctl["stop"]:
        c.seq += 1
        c.sent[c.seq] = time.perf_counter()
        if random.random() < 0.15:
            await ws.send_json({"t": "bomb", "q": c.seq})
        else:
            await ws.send_json({"t": "in", "d": random.choice(DIRS), "q": c.seq})
        await asyncio.sleep(random.uniform(0.12, 0.35))
    rt.cancel()
    await ws.close()


def proc_stats(pid: int) -> tuple[float, float]:
    out = subprocess.run(["ps", "-o", "%cpu=,rss=", "-p", str(pid)], capture_output=True, text=True).stdout.split()
    return (float(out[0]), float(out[1]) / 1024) if out else (0.0, 0.0)


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * q))] if xs else 0.0


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--players", type=int, default=100)
    ap.add_argument("--seconds", type=float, default=40)
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--pid", type=int, default=0)
    a = ap.parse_args()

    clients = [Client(i) for i in range(a.players)]
    groups = [clients[i:i + 6] for i in range(0, len(clients), 6)]
    ctl = {"start": asyncio.Event(), "stop": float("inf")}
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=0)) as session:
        tasks = []
        for g in groups:
            fut = asyncio.get_running_loop().create_future()
            for k, c in enumerate(g):
                tasks.append(asyncio.create_task(run_client(session, a.url, c, k == 0, fut, ctl)))
        await asyncio.sleep(3 + a.players * 0.02)  # 等所有人进房
        ctl["stop"] = time.perf_counter() + a.seconds + 3.5  # 含 3 秒倒计时
        ctl["start"].set()
        cpu, rss = [], 0.0
        t0 = time.perf_counter()
        while time.perf_counter() < ctl["stop"]:
            await asyncio.sleep(1)
            if a.pid and time.perf_counter() - t0 > 5:
                c_, rss = proc_stats(a.pid)
                cpu.append(c_)
        await asyncio.gather(*tasks, return_exceptions=True)

    gaps = [g for c in clients for g in c.gaps]
    lat = [x for c in clients for x in c.lat]
    played = sum(1 for c in clients if c.playing)
    print(f"\n==== {a.players} 名玩家 · {len(groups)} 个房间 · 对局 {a.seconds:.0f}s ====")
    print(f"进入对局的客户端   {played}/{a.players}   错误消息 {sum(c.errors for c in clients)}")
    print(f"快照间隔 ms        p50={pct(gaps, .5):.1f}  p95={pct(gaps, .95):.1f}  p99={pct(gaps, .99):.1f}  max={max(gaps or [0]):.1f}")
    print(f"输入→确认 ms       p50={pct(lat, .5):.1f}  p95={pct(lat, .95):.1f}  p99={pct(lat, .99):.1f}  (样本 {len(lat)})")
    dur = a.seconds + 3.5
    rate = statistics.mean(c.snaps / dur for c in clients)
    bw = statistics.mean(c.bytes / dur for c in clients) / 1024
    print(f"每客户端           {rate:.1f} 帧/秒  下行 {bw:.1f} KB/s  （服务器总出口约 {bw * a.players / 1024:.2f} MB/s）")
    if cpu:
        print(f"服务器进程         CPU 平均 {statistics.mean(cpu):.0f}%  峰值 {max(cpu):.0f}%  内存 {rss:.0f} MB")


if __name__ == "__main__":
    asyncio.run(main())
