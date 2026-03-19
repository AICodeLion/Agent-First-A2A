# 🦞 Agent-First A2A

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![Protocol](https://img.shields.io/badge/Protocol-A2A-orange?style=flat-square)
![Scene](https://img.shields.io/badge/场景-TutorClaw_学术面试-red?style=flat-square)
![Security](https://img.shields.io/badge/隐私-本地脱敏处理-blueviolet?style=flat-square)

**让你的数字分身代你完成第一轮对接，再由你决定是否亲自出场。**

两个 Agent 分别运行在面试官和申请者的设备上，通过 A2A 协议互相发现、展开对话，最终由裁判 AI 从双方视角各自评分。

> 🎯 **当前实现**：Agent-First A2A 是一个可扩展的分布式对话框架。目前已落地第一个场景 —— **TutorClaw（学术面试）**，支持导师与博士申请者的数字分身完成学术考察 + 行为学考察，并输出双向评分报告。更多场景持续开发中。

[工作原理](#工作原理) · [快速开始](#快速开始) · [可用场景](#可用场景) · [隐私安全](#隐私安全) · [系统架构](#系统架构)

</div>

---

## 工作原理

```
你（面试官）                              对方（申请者）
    │                                        │
    ▼                                        ▼
数字分身 Agent A                        数字分身 Agent B
读取你的 SOUL / USER / MEMORY            读取对方的档案
本地脱敏处理 🔒                          本地脱敏处理 🔒
    │                                        │
    └──────────── Matchmaker ────────────────┘
                  服务发现 → 分阶段对话 → 裁判 AI 双向评分
                                             │
                              ┌──────────────┴──────────────┐
                         导师视角报告                   申请者视角报告
                       （你对申请者评分）             （申请者对你评分）
```

> **核心设计**：视角校正集中在 Matchmaker，Agent 只负责透传。双方都是评估者，也都是被评估者。

---

## 快速开始

### 前置要求

- Python 3.10+
- MiniMax API Key（在 `agents/base_agent.py` 和 `judge.py` 中配置）
- 双方设备网络互通（跨机器部署时）

### 第一步：安装依赖

```bash
# 建议使用虚拟环境
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 第二步：准备你的档案

在本机创建 `~/.openclaw/workspace/` 目录，填写三个文件：

```
~/.openclaw/workspace/
├── SOUL.md      # 你的性格、风格、核心价值观
├── USER.md      # 你的背景信息（因角色而异，见下方示例）
└── MEMORY.md    # 你的偏好、经验、特别关注点
```

<details>
<summary>📋 示例：学术导师的 USER.md</summary>

```markdown
研究方向：计算机视觉、多模态大模型
实验室规模：5名博士生，2名博士后
招生需求：有扎实的深度学习基础，有过独立项目经历优先
```

</details>

<details>
<summary>📋 示例：博士申请者的 USER.md</summary>

```markdown
本科：XX大学计算机系，GPA 3.8
研究经历：参与过一篇 CVPR 论文，负责数据处理和实验复现
技能：PyTorch、Python、熟悉 Transformer 架构
申请方向：计算机视觉 / 多模态
```

</details>

> 🔒 档案内容在发送前会自动脱敏，手机号、邮箱等敏感信息会被替换，[详见隐私安全](#隐私安全)。

### 第三步：启动各自的 Agent

**面试官 / 导师 / HR（角色 A）：**

```bash
python3 agents/supervisor_agent.py --name "你的名字" --port 8001
```

**申请者 / 候选人（角色 B）：**

```bash
python3 agents/applicant_agent.py --name "你的名字" --port 8002
```

启动成功后终端显示：

```
🦞 Leo Agent 已启动（supervisor）
   /.well-known/agent.json → http://localhost:8001/.well-known/agent.json
   /tasks/send            → http://localhost:8001/tasks/send
   /health                → http://localhost:8001/health
```

如果档案不在默认位置，可手动指定路径：

```bash
python3 agents/supervisor_agent.py \
  --name "Leo" --port 8001 \
  --soul /path/to/SOUL.md \
  --user /path/to/USER.md \
  --memory /path/to/MEMORY.md
```

### 第四步：启动撮合器

双方 Agent 都启动后，任意一方运行撮合器：

```bash
# 跨机器
python3 matchmaker.py \
  --agent-a http://面试官IP:8001 \
  --agent-b http://申请者IP:8002

# 本地测试（双 Agent 同一台机器）
python3 matchmaker.py \
  --agent-a http://localhost:8001 \
  --agent-b http://localhost:8002
```

### 第五步：查看评分报告

对话结束后，`output/` 目录下生成双向报告：

```
output/
├── 2026-03-19-00-48-chat.md        # 完整对话记录
├── 2026-03-19-00-48-report-b.md    # 导师对申请者的评分
└── 2026-03-19-00-48-report-a.md    # 申请者对导师的评分
```

报告示例：

```
导师视角 · 评申请者
─────────────────────────────
研究背景与方向契合度    18 / 20
科研思维深度与创新性    16 / 20
学术表达与逻辑清晰度     9 / 10
科研动机清晰度与真实性  13 / 15
抗压能力与处理模糊性    12 / 15
团队协作与沟通风格       8 / 10
综合潜力印象             9 / 10
─────────────────────────────
总分  85 / 100   ✅ 强烈推荐录取
```

> 申请者同样会收到一份对导师 / 实验室的评分报告——你不只是被评估的一方，你也在评估对方。

---

## 可用场景

| 场景名 | 说明 | 角色 A | 角色 B | 状态 |
|---|---|---|---|---|
| `academic_interview` | 学术考察（3轮）+ 行为学考察（3轮） | 导师 | 申请者 | ✅ 已实现 |
| `dating` | 价值观 + 生活方式 + 未来规划（各2轮） | A方 | B方 | 🚧 开发中 |
| `job_matching` | 技能评估 + 文化匹配（各2轮） | HR | 候选人 | 🚧 开发中 |

---

## 隐私安全

**你的档案永远不会原文发送。** 所有内容在离开本机之前，经过本地脱敏处理：

```
原始内容：联系我：zhang@example.com，手机 138-0000-1234
脱敏后：  联系我：[EMAIL]，手机 [PHONE]
```

脱敏覆盖范围：

| 类型 | 示例 | 替换为 |
|---|---|---|
| 手机号 | `138-0000-1234` | `[PHONE]` |
| 邮箱地址 | `user@example.com` | `[EMAIL]` |
| 身份证号 | `310...` | `[ID_NUMBER]` |
| 家庭住址 | `上海市XX区XX路` | `[ADDRESS]` |
| 银行卡号 | `6222...` | `[BANK_CARD]` |

脱敏在本机完成，发送给 LLM 的内容已经是处理后的版本。启动日志中可以看到脱敏统计：

```
🔒 脱敏 2 处：手机号、邮箱地址
✅ 无敏感信息
```

如需单独检查某个文件的脱敏结果：

```bash
python3 sanitize.py ~/.openclaw/workspace/USER.md --dry-run
```

---

## 系统架构

```
Agent-First-A2A/
├── agents/
│   ├── base_agent.py        # BaseA2AAgent：FastAPI 服务 + LLM 调用
│   ├── supervisor_agent.py  # 角色 A 入口（导师 / HR / A方）
│   └── applicant_agent.py   # 角色 B 入口（申请者 / 候选人 / B方）
├── matchmaker.py            # 撮合器：服务发现 + 对话编排 + 裁判调用
├── scenarios.py             # 场景定义（可扩展新场景）
├── judge.py                 # 裁判 AI：双向评分 + 报告生成
├── sanitize.py              # 敏感信息脱敏
├── output/                  # 对话记录和报告（本地保存，不上传）
└── requirements.txt
```

**A2A 协议端点（每个 Agent）：**

| 端点 | 方法 | 用途 |
|---|---|---|
| `/.well-known/agent.json` | GET | 服务发现，返回 Agent Card |
| `/tasks/send` | POST | 接收任务，返回回复 |
| `/health` | GET | 健康检查 |

---

## License

MIT
