"""生成传输加密用的 RSA-2048 密钥对。

  python scripts/gen_rsa.py            # 写入 public/js/rsa-public.js，并把私钥写进 .env（RSA_PRIVATE_KEY）
  python scripts/gen_rsa.py --print    # 只打印私钥（单行 base64，用于 docker run -e RSA_PRIVATE_KEY=...）

公钥会被「写死」进网页（public/js/rsa-public.js，需要提交 / 打进镜像）；
私钥只放在服务器环境变量里，不要提交到仓库。换密钥后必须重新构建镜像，旧网页将无法登录。
"""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import secure  # noqa: E402


def main() -> None:
    key = secure.generate_key()
    line = base64.b64encode(secure.private_pem(key).encode()).decode()
    secure.PUBLIC_JS.write_text(secure.public_js(key), "utf-8")
    print(f"已写入公钥：{secure.PUBLIC_JS.relative_to(ROOT)}")
    if "--print" in sys.argv:
        print("\nRSA_PRIVATE_KEY=" + line)
        return
    env = ROOT / ".env"
    text = env.read_text("utf-8") if env.exists() else ""
    text = re.sub(r"(?m)^RSA_PRIVATE_KEY=.*\n?", "", text)
    if text and not text.endswith("\n"):
        text += "\n"
    env.write_text(text + f"RSA_PRIVATE_KEY={line}\n", "utf-8")
    env.chmod(0o600)
    print("已写入私钥：.env（RSA_PRIVATE_KEY，已设为仅本人可读）")


if __name__ == "__main__":
    main()
