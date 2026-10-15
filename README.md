# owu-proxy

把 OpenWebUI 的账号密码登录能力，转成 OpenAI 兼容接口对外提供，并签发稳定的 API Key。

## 背景

用户仅有 OpenWebUI 登录名 + 密码、无 admin 权限、无法创建 API Key。本网关用账号密码登录换 JWT（自动续期），对外暴露 `/v1/models` 与 `/v1/chat/completions`（流式/非流式），外部调用方用自定义 key 即可。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量（复制模板后填写）
cp .env.example .env

# 3. 载入环境变量
# Linux/macOS:
set -a && source .env && set +a
# Windows (cmd):
#   for /f "tokens=*" %i in (.env) do set %i

# 4. 启动
python main.py
# 或生产用：
uvicorn main:app --host 0.0.0.0 --port 18000
```

## 外部调用

```bash
# 模型列表
curl http://localhost:18000/v1/models -H "Authorization: Bearer sk-proxy-abc123"

# 非流式对话
curl http://localhost:18000/v1/chat/completions \
  -H "Authorization: Bearer sk-proxy-abc123" \
  -H "Content-Type: application/json" \
  -d '{"model":"模型名","messages":[{"role":"user","content":"你好"}]}'

# 流式对话
curl http://localhost:18000/v1/chat/completions \
  -H "Authorization: Bearer sk-proxy-abc123" \
  -H "Content-Type: application/json" \
  -d '{"model":"模型名","messages":[{"role":"user","content":"你好"}],"stream":true}'
```

### openai SDK 接入

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:18000/v1",
    api_key="sk-proxy-abc123",
)
resp = client.chat.completions.create(
    model="模型名",
    messages=[{"role": "user", "content": "你好"}],
)
print(resp.choices[0].message.content)
```

## 配置项

| 环境变量 | 说明 | 默认 |
|----------|------|------|
| `OPENWEBUI_URL` | OpenWebUI 地址 | `http://127.0.0.1:8080` |
| `OWU_EMAIL` | 登录邮箱 | 空 |
| `OWU_PASSWORD` | 登录密码 | 空 |
| `PROXY_KEYS` | 对外 key（逗号分隔） | 空 |
| `REFRESH_AHEAD` | JWT 提前刷新秒数 | `3600` |
| `PORT` | 监听端口 | `18000` |
