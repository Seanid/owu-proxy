#!/usr/bin/env python3
"""OpenWebUI → OpenAI 兼容中转网关（自写 FastAPI）。

免责声明：
  本代码由 AI 编码（AI Coding）辅助生成，仅供个人学习与技术研究，
  不保证稳定性与安全性，使用风险自负。请勿用于商业用途或未授权访问。
  详见 DISCLAIMER.md。
"""
import os
import time
import asyncio
import base64
import json
from typing import Optional

try:
    from dotenv import load_dotenv

    load_dotenv()  # 自动加载同目录下的 .env
except ImportError:
    pass  # 未安装 python-dotenv 时忽略，改用系统环境变量

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

# ---------- 配置（从环境变量读取） ----------
OPENWEBUI_URL = os.environ.get("OPENWEBUI_URL", "http://127.0.0.1:8080").rstrip("/")
OWU_EMAIL = os.environ.get("OWU_EMAIL", "")
OWU_PASSWORD = os.environ.get("OWU_PASSWORD", "")

# 对外签发的 API Key 集合（多个 key 用逗号分隔）
PROXY_KEYS = set(
    k.strip() for k in os.environ.get("PROXY_KEYS", "").split(",") if k.strip()
)

# JWT 提前刷新阈值（秒），默认剩余不足 1 小时就重新登录
REFRESH_AHEAD = int(os.environ.get("REFRESH_AHEAD", "3600"))


def _jwt_exp(token: str) -> float:
    """从 JWT payload 里解析 exp，失败则返回 6 天后（兜底）。"""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)  # 补齐 base64 padding
        data = json.loads(base64.urlsafe_b64decode(payload))
        return float(data.get("exp", time.time() + 6 * 86400))
    except Exception:
        return time.time() + 6 * 86400


class TokenManager:
    """JWT 缓存 + 自动续期，asyncio.Lock 保证并发安全。"""

    def __init__(self):
        self._token: Optional[str] = None
        self._exp: float = 0.0
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        # 快过期或还没有 → 重新登录
        if self._token is None or time.time() > self._exp - REFRESH_AHEAD:
            async with self._lock:
                # 双重检查，避免并发重复登录
                if self._token is None or time.time() > self._exp - REFRESH_AHEAD:
                    await self._signin()
        return self._token

    async def _signin(self) -> None:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{OPENWEBUI_URL}/api/v1/auths/signin",
                json={"email": OWU_EMAIL, "password": OWU_PASSWORD},
            )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=502, detail=f"OpenWebUI 登录失败: {resp.text}"
            )
        data = resp.json()
        token = data.get("token")
        if not token:
            raise HTTPException(status_code=502, detail="OpenWebUI 登录响应缺少 token")
        self._token = token
        self._exp = _jwt_exp(token)


tm = TokenManager()
app = FastAPI(title="OpenWebUI Proxy")


def check_api_key(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少 Authorization: Bearer <key>")
    key = auth[len("Bearer "):].strip()
    if key not in PROXY_KEYS:
        raise HTTPException(status_code=401, detail="无效的 API Key")


def _is_json(resp: httpx.Response) -> bool:
    ct = resp.headers.get("content-type", "")
    return "application/json" in ct


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/v1/models")
async def list_models(request: Request):
    check_api_key(request)
    token = await tm.get_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{OPENWEBUI_URL}/api/v1/models", headers=headers)
    if _is_json(resp):
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    return JSONResponse(status_code=resp.status_code, content={"detail": resp.text})


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    check_api_key(request)
    body = await request.json()
    token = await tm.get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    if body.get("stream"):
        # 流式：逐块透传 SSE
        async def event_stream():
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{OPENWEBUI_URL}/api/v1/chat/completions",
                    headers=headers,
                    json=body,
                ) as resp:
                    if resp.status_code != 200:
                        err = await resp.aread()
                        detail = err.decode(errors="ignore")[:200]
                        yield f'data: {{"error": {{"message": "上游错误 {resp.status_code}", "body": "{detail}"}}}}\n\n'
                        yield "data: [DONE]\n\n"
                        return
                    async for chunk in resp.aiter_bytes():
                        if chunk:
                            yield chunk

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # 非流式：直接透传
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{OPENWEBUI_URL}/api/v1/chat/completions",
            headers=headers,
            json=body,
        )
    if _is_json(resp):
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    return JSONResponse(status_code=resp.status_code, content={"detail": resp.text})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "18000")))
