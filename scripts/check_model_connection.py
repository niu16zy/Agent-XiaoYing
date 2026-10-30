"""Check the configured model with one JSON request, without running business tools."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowledge_agent.agent import bounded_call
from knowledge_agent.config import load_env
from knowledge_agent.model import Action, ActionError, ModelError, OpenAIModel


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        load_env(ROOT / ".env")
        model = OpenAIModel()
        messages = [
            {"role": "system", "content": "这是连接检查。仅输出 JSON，不执行工具。"},
            {"role": "user", "content": '请输出 {"action":"search_docs","arguments":{"query":"连接检查"},"reason":"连接正常。"}'},
        ]
        reply = bounded_call(lambda: model.choose(messages, timeout=60), 60)
        Action.parse(reply)
        print(json.dumps({"status": "connected", "model": model.name, "endpoint": model.endpoint,
                          "message": "模型连接及 JSON 动作返回正常；尚未验证业务问答。"}, ensure_ascii=False, indent=2))
        return 0
    except ModelError as exc:
        code = exc.code
    except TimeoutError:
        code = "MODEL_TIMEOUT"
    except ActionError:
        code = "INVALID_MODEL_ACTION"
    except (ValueError, OSError):
        code = "INVALID_LOCAL_CONFIG"
    print(json.dumps({"status": "failed", "code": code}, ensure_ascii=False, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
