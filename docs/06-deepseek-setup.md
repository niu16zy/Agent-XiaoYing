# DeepSeek 真实模型配置

本机已经安装 OpenAI SDK 2.30.0。项目根目录 `.env` 为本地配置文件，已在 `.gitignore` 排除。

将 DeepSeek 平台的实际 API 密钥填到 `.env` 第一行的等号后面，不写入 Python 源码，不发到聊天中：

```dotenv
MODEL_API_KEY=在这里填入你的DeepSeek密钥
MODEL_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-flash
```

示例中的占位文字必须替换为实际密钥。使用项目的 MODEL_API_KEY 即可；官方示例中的 DEEPSEEK_API_KEY 是环境变量名称，不是密钥本身。项目也支持 DEEPSEEK_API_KEY 作为 DeepSeek 地址下的备用变量；两者只需配置一个。已有同名系统/终端环境变量优先于 `.env`。

在 PowerShell 运行：

```powershell
cd D:\Desktop\小影笔试
python scripts/check_model_connection.py
```

返回 `status: connected` 代表一次真实模型 JSON 请求成功，不代表全部业务验收通过。随后运行：

```powershell
python scripts/run_agent.py --mode real --question "报销期限多久？" --model-timeout 90 --total-timeout 300
python scripts/run_agent.py --mode real --scenario conflict --question "报销期限多久？" --model-timeout 90 --total-timeout 300
```

第一条预期依据 D01 回答 30 个自然日，第二条预期展示 D01/D02 的冲突并请求确认。实际结果和 Trace 保存到 `examples/real/<运行编号>/`。填入密钥后还需实际执行，不能预先宣称成功。

适配器对官方 DeepSeek 地址使用 `max_tokens=8192`、`reasoning_effort=high` 和 `extra_body={"thinking":{"type":"enabled"}}`，保留 JSON 输出模式；不记录 `reasoning_content`。依据 [DeepSeek Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/) 和 [JSON Output 文档](https://api-docs.deepseek.com/guides/json_mode/)。

常见返回：`MISSING_API_KEY` 表示未读取到密钥；`MODEL_HTTP_401` 表示认证失败；`MODEL_REQUEST_FAILED` 表示请求失败，需检查网络和地址；`MODEL_TIMEOUT` 表示超时。连接检查不打印密钥或服务原始异常内容。
