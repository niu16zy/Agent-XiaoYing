"""Small explicit .env loader: no execution, interpolation or secret logging."""

import os
from pathlib import Path


def load_env(path: Path):
    if not path.exists():
        return
    allowed = {"MODEL_API_KEY", "MODEL_BASE_URL", "MODEL_NAME", "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL", "DEEPSEEK_API_KEY"}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or key not in allowed:
            raise ValueError("环境文件包含不支持的配置。")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if value:
            os.environ.setdefault(key, value)
