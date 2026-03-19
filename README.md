# 🦞 TutorClaw A2A

**分布式双 Agent 对话框架** — 让你的数字分身代你完成第一轮对接，再由你决定是否亲自出场。

两个 Agent 运行在独立设备上，通过 A2A 协议互相发现、对话，最终由裁判 AI 双向评分。

---

## 两类使用者

本项目面向两类人：

- **普通用户**：我想用数字分身和别人的数字分身对接，不想看代码
- **开发者**：我想接入新场景、修改评分逻辑、或把 Agent 部署到自己的服务器

---

## 普通用户：快速上手

### 第一步：安装依赖

```bash
pip install -r requirements.txt
```

### 第二步：准备你的档案

Agent 会读取本机 `~/.openclaw/workspace/` 下的三个文件作为你的"数字分身"：

```
~/.openclaw/workspace/
├── SOUL.md      # 你的性格、价值观、核心特质
├── USER.md      # 你的背景信息（学历、经历、技能等）
└── MEMORY.md    # 你的记忆、偏好、近期状态
```

按照自己的实际情况填写这三个文件，Agent 会以此为基础代表你说话。

> 档案内容会在发送前自动脱敏（手机号、邮箱等敏感信息会被替换）。

### 第三步：启动你的 Agent

**用户 A（角色 A 方）在自己的机器上运行：**

```bash
python3 agents/supervisor_agent.py --name "你的名字" --port 8001
```

**用户 B（角色 B 方）在自己的机器上运行：**

```bash
python3 agents/applicant_agent.py --name "你的名字" --port 8002
```

### 第四步：启动撮合器

任意一方（或第三方）运行撮合器，填入双方的 IP 地址：

```bash
python3 matchmaker.py \
  --agent-a http://用户A的IP:8001 \
  --agent-b http://用户B的IP:8002
```

本地测试（双 Agent 同一台机器）：

```bash
python3 matchmaker.py \
  --agent-a http://localhost:8001 \
  --agent-b http://localhost:8002
```

### 第五步：查看结果

对话结束后，`output/` 目录下会生成：

```
output/
├── 2026-03-19-00-48-chat.md        # 完整对话记录
├── 2026-03-19-00-48-report-a.json  # 角色 A 的评分报告（JSON）
├── 2026-03-19-00-48-report-a.md    # 角色 A 的评分报告（Markdown）
├── 2026-03-19-00-48-report-b.json  # 角色 B 的评分报告（JSON）
└── 2026-03-19-00-48-report-b.md    # 角色 B 的评分报告（Markdown）
```

### 可用场景

通过 `--scenario` 指定场景（默认 `academic_interview`）：

| 场景名 | 说明 |
|---|---|
| `academic_interview` | 学术面试：导师 × 博士申请者，学术考察 + 行为学考察 |
| `dating` | 相亲匹配：价值观 + 生活方式 + 未来规划 |
| `job_matching` | 职场对接：HR × 候选人，技能评估 + 文化匹配 |

```bash
# 示例：相亲场景
python3 matchmaker.py \
  --agent-a http://localhost:8001 \
  --agent-b http://localhost:8002 \
  --scenario dating
```

### 自定义档案路径

如果你的档案不在默认位置，可以手动指定：

```bash
python3 agents/supervisor_agent.py \
  --name "Leo" \
  --port 8001 \
  --soul /path/to/SOUL.md \
  --user /path/to/USER.md \
  --memory /path/to/MEMORY.md
```

---

## 开发者：架构与扩展

### 系统架构

```
Agent A (FastAPI :8001)          Agent B (FastAPI :8002)
  BaseA2AAgent                     BaseA2AAgent
  读取本机 SOUL/USER/MEMORY          读取本机 SOUL/USER/MEMORY
        │                                │
        └────────── matchmaker ──────────┘
                   (撮合器/编排器)
                   服务发现 → 分阶段对话 → 双向裁判评分
```

**核心设计原则：视角校正集中在 matchmaker，Agent 只负责透传。**

matchmaker 在每次调用前将共享历史转换为接收方视角（`to_perspective()`），Agent 收到的已经是正确的 `user`/`assistant` 消息，直接传给 LLM 即可。

### A2A 协议端点

每个 Agent 暴露三个端点：

| 端点 | 方法 | 用途 |
|---|---|---|
| `/.well-known/agent.json` | GET | 服务发现，返回 Agent Card |
| `/tasks/send` | POST | 接收任务，返回 Agent 回复 |
| `/health` | GET | 健康检查 |

### 新增场景

在 `scenarios.py` 的 `SCENARIOS` 字典中添加新条目：

```python
"my_scenario": {
    "name": "场景显示名",
    "description": "场景描述",

    "role_A": "role_key_a",       # role_A 的内部 key
    "role_B": "role_key_b",
    "role_A_label": "A方显示名",
    "role_B_label": "B方显示名",

    "judge_role": "裁判角色描述",
    "judge_system": "裁判 system prompt，只输出合法 JSON。",

    "phases": [
        {
            "id": "phase_1",
            "name": "第一阶段名称",
            "emoji": "💬",
            "legend": "阶段说明（用于前端展示）",
            "rounds": 3,
            "role_A_trigger": "阶段开始时注入给 role_A 的触发指令",
        },
        # 更多阶段...
    ],

    "system_prompts": {
        "role_key_a": "role_A 的 system prompt",
        "role_key_b": "role_B 的 system prompt",
    },

    # role_A 视角评 role_B（分项评分）
    "judge_criteria_b": [
        {"name": "评分维度名", "max_score": 20, "phase": "phase_1"},
    ],
    "verdict_thresholds_b": [
        (85, "结论文字"),
        (0,  "兜底结论"),
    ],

    # role_B 视角评 role_A
    "judge_criteria_a": [
        {"name": "评分维度名", "max_score": 20, "phase": "phase_1"},
    ],
    "verdict_thresholds_a": [
        (85, "结论文字"),
        (0,  "兜底结论"),
    ],
}
```

添加后直接用 `--scenario my_scenario` 启动即可，无需修改其他文件。

### 项目结构

```
Agent-First-A2A/
├── agents/
│   ├── base_agent.py        # BaseA2AAgent：FastAPI 服务 + LLM 调用
│   ├── supervisor_agent.py  # 角色 A 入口（导师/HR/A方）
│   └── applicant_agent.py   # 角色 B 入口（申请者/候选人/B方）
├── matchmaker.py            # 撮合器：服务发现 + 对话编排 + 调用裁判
├── scenarios.py             # 所有场景定义
├── judge.py                 # 裁判 LLM：双向评分 + 报告生成
├── sanitize.py              # 敏感信息脱敏
├── well-known/
│   └── agent_template.json  # Agent Card 模板
├── output/                  # 对话记录和评分报告（不上传 git）
└── requirements.txt
```

### LLM 配置

当前使用 MiniMax M2.5（Anthropic 兼容 API）。如需更换，修改 `agents/base_agent.py` 和 `judge.py` 顶部的配置：

```python
MINIMAX_BASE_URL = "https://api.minimaxi.com/anthropic"
MINIMAX_API_KEY  = "your_api_key"
MODEL            = "MiniMax-M2.5"
```

> 建议迁移到环境变量：`export MINIMAX_API_KEY=your_key`

### 跨机器部署注意事项

- Agent 默认绑定 `0.0.0.0`，确保防火墙开放对应端口（8001/8002）
- `well-known/agent_template.json` 中的 `url` 字段需要改为实际的公网/局域网 IP
- 当前无鉴权，生产环境建议在 `matchmaker.py` 的请求头中加入 Bearer Token

---

## 依赖

```
anthropic>=0.84.0
fastapi>=0.110.0
uvicorn>=0.29.0
httpx>=0.27.0
pydantic>=2.0.0
```

---

## License

MIT
