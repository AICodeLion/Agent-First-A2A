"""
agents/base_agent.py — A2A Agent 基础服务器（修复版）

修复：
  1. 直接读本机 SOUL/USER/MEMORY，不再依赖 profile.json
  2. 接收来自 matchmaker 的视角已校正消息（user/assistant），不再自己判断
  3. 同步 LLM 调用（FastAPI 自动放入线程池，不阻塞事件循环）
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

import anthropic
import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from sanitize import sanitize

# ── LLM 配置 ──────────────────────────────────────────────────────────────────
MINIMAX_BASE_URL = "https://api.minimaxi.com/anthropic"
MINIMAX_API_KEY  = "sk-cp-TRZ3kVSSzHdr4YVMW4rtzWdZhU6dvC_ZT3LhIdqOfKUKBE_1lZa_tqXnCo4QZstB3RxiO6YtsFvX3zYud3vskbG7W0t2AgNosSCscV9vPLN2L-MNWGpYwO8"
MODEL            = "MiniMax-M2.5"

# ── OpenClaw 默认路径 ──────────────────────────────────────────────────────────
DEFAULT_BASE     = Path.home() / ".openclaw" / "workspace"
DEFAULT_SOUL     = DEFAULT_BASE / "SOUL.md"
DEFAULT_USER     = DEFAULT_BASE / "USER.md"
DEFAULT_MEMORY   = DEFAULT_BASE / "MEMORY.md"


# ── A2A 数据结构 ───────────────────────────────────────────────────────────────

class A2AMessage(BaseModel):
    """
    matchmaker 发来的消息已经是视角校正后的格式：
      role="user"      → 对方说的（需要我回应）
      role="assistant" → 我自己之前说的
    """
    role:    str    # "user" | "assistant"
    content: str


class A2ATask(BaseModel):
    id:       str            = ""
    messages: list[A2AMessage] = []
    metadata: dict           = {}


class A2ATaskResult(BaseModel):
    task_id: str
    status:  str
    message: A2AMessage
    metadata: dict = {}


# ── 本地文件加载 ───────────────────────────────────────────────────────────────

def load_local_context(soul: Path, user: Path, memory: Path) -> str:
    """读取本机三个档案文件，拼接后脱敏，返回干净上下文"""
    parts = []
    for p in [soul, user, memory]:
        if p.exists():
            content = p.read_text(encoding="utf-8")
            parts.append(f"## [{p.name}]\n{content}")
            print(f"  ✅ 读取 {p.name}（{len(content)} 字）")
        else:
            print(f"  ⚠️  跳过 {p}（不存在）")

    raw    = "\n\n---\n\n".join(parts)
    result = sanitize(raw)

    if result.count > 0:
        print(f"  🔒 脱敏 {result.count} 处：" +
              "、".join(r["description"] for r in result.redacted))
    else:
        print("  ✅ 无敏感信息")

    return result.text


# ── 基础 Agent ─────────────────────────────────────────────────────────────────

class BaseA2AAgent:

    def __init__(
        self,
        name:        str,
        role_key:    str,       # "supervisor" | "applicant"
        scenario:    dict,
        soul_path:   Path = DEFAULT_SOUL,
        user_path:   Path = DEFAULT_USER,
        memory_path: Path = DEFAULT_MEMORY,
        port:        int  = 8000,
    ):
        self.name     = name
        self.role_key = role_key
        self.port     = port

        # 读取 + 脱敏本地文件
        print(f"\n📂 读取 {name} 的本地档案...")
        context = load_local_context(soul_path, user_path, memory_path)

        # 构建 system prompt
        role_prompt        = scenario["system_prompts"][role_key]
        self.system_prompt = (
            f"你是 {name}。以下是你的身份设定、用户背景和记忆：\n\n"
            f"{context}\n\n---\n\n## 当前角色要求\n\n{role_prompt}\n\n"
            f"请完全沉浸在你的角色中。直接以 {name} 的身份说话。"
        )

        # Agent Card
        self.agent_card = self._build_card(scenario)

        # FastAPI
        self.app = FastAPI(title=f"TutorClaw · {name}")
        self._register_routes()

    # ── Agent Card ─────────────────────────────────────────────────────────────

    def _build_card(self, scenario: dict) -> dict:
        template = json.loads(
            (Path(__file__).parent.parent / "well-known" / "agent_template.json")
            .read_text(encoding="utf-8")
        )
        template["name"]        = self.name
        template["description"] = f"TutorClaw 数字分身 · {self.name}（{self.role_key}）"
        template["url"]         = f"http://localhost:{self.port}"
        return template

    # ── FastAPI 路由 ───────────────────────────────────────────────────────────

    def _register_routes(self):
        app = self.app

        @app.get("/.well-known/agent.json")
        def get_agent_card():
            return self.agent_card

        @app.post("/tasks/send")
        def handle_task(task: A2ATask):
            """
            接收来自 matchmaker 的视角校正消息，调用 LLM，返回回复。
            FastAPI 自动在线程池中运行同步路由，不阻塞事件循环。
            """
            task.id = task.id or str(uuid.uuid4())
            reply   = self._call_llm(task.messages, task.metadata)
            return A2ATaskResult(
                task_id  = task.id,
                status   = "completed",
                message  = A2AMessage(role="assistant", content=reply),
                metadata = {"agent": self.name, "role": self.role_key,
                            "at": datetime.now().isoformat()},
            )

        @app.get("/health")
        def health():
            return {"status": "ok", "agent": self.name, "role": self.role_key}

    # ── LLM 调用 ───────────────────────────────────────────────────────────────

    def _build_llm_messages(
        self, messages: list[A2AMessage], metadata: dict
    ) -> list[dict]:
        """
        消息已经是视角校正后的 user/assistant 格式，直接转换。
        特殊处理：
          - 空历史（第一轮）→ 用 metadata.trigger 引导
          - 新阶段开始（有 trigger）→ 追加触发指令
          - 最后一条是 assistant → 追加"请继续"
        """
        if not messages:
            trigger = metadata.get("trigger", "请开始。")
            return [{"role": "user", "content": trigger}]

        msgs = [{"role": m.role, "content": m.content} for m in messages]

        if "trigger" in metadata:
            # 新阶段：在历史末尾注入触发指令
            msgs.append({"role": "user", "content": metadata["trigger"]})
        elif msgs[-1]["role"] == "assistant":
            msgs.append({"role": "user", "content": "（请继续）"})

        return msgs

    def _call_llm(self, messages: list[A2AMessage], metadata: dict) -> str:
        client   = anthropic.Anthropic(api_key=MINIMAX_API_KEY, base_url=MINIMAX_BASE_URL)
        llm_msgs = self._build_llm_messages(messages, metadata)
        response = client.messages.create(
            model=MODEL, max_tokens=1500,
            system=self.system_prompt,
            messages=llm_msgs,
        )
        return next((b.text for b in response.content if b.type == "text"), "").strip()

    # ── 启动 ───────────────────────────────────────────────────────────────────

    def run(self):
        print(f"\n🦞 {self.name} Agent 已启动（{self.role_key}）")
        print(f"   /.well-known/agent.json → http://localhost:{self.port}/.well-known/agent.json")
        print(f"   /tasks/send            → http://localhost:{self.port}/tasks/send")
        print(f"   /health                → http://localhost:{self.port}/health\n")
        uvicorn.run(self.app, host="0.0.0.0", port=self.port, log_level="warning")
