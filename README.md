# 🦞 Agent-First A2A

> 当前实现场景：**TutorClaw**（学术面试）

让你的数字分身代你完成第一轮对接，再由你决定是否亲自出场。

两个 Agent 分别运行在面试官和申请者的设备上，通过 A2A 协议互相发现、展开对话，最终由裁判 AI 从双方视角各自评分。

---

## 我是面试官 / 导师 / HR

> 我想让数字分身替我完成初筛，只见真正值得见的人。

### 第一步：准备你的档案

在本机创建 `~/.openclaw/workspace/` 目录，填写三个文件：

```
~/.openclaw/workspace/
├── SOUL.md      # 你的性格、风格、核心价值观
├── USER.md      # 你的背景：实验室方向 / 公司信息 / 岗位需求
└── MEMORY.md    # 你的偏好、过往面试经验、特别关注点
```

示例（学术导师）：

```markdown
# USER.md
研究方向：计算机视觉、多模态大模型
实验室规模：5名博士生，2名博士后
招生需求：有扎实的深度学习基础，有过独立项目经历优先
```

> 档案内容在发送前会自动脱敏，手机号、邮箱等敏感信息会被替换。

### 第二步：安装依赖并启动 Agent

```bash
pip install -r requirements.txt

python3 agents/supervisor_agent.py --name "你的名字" --port 8001
```

启动后终端会显示：

```
🦞 Leo Agent 已启动（supervisor）
   /.well-known/agent.json → http://localhost:8001/.well-known/agent.json
   /tasks/send            → http://localhost:8001/tasks/send
   /health                → http://localhost:8001/health
```

### 第三步：告诉申请者你的地址

把你的 IP 和端口（如 `http://192.168.1.10:8001`）发给对方或撮合方，等待对话开始。

### 第四步：查看评分报告

对话结束后，`output/` 目录下会生成双向报告：

```
output/
├── 2026-03-19-00-48-chat.md        # 完整对话记录
├── 2026-03-19-00-48-report-b.md    # 你对申请者的评分（你的视角）
└── 2026-03-19-00-48-report-a.md    # 申请者对你的评分（对方视角）
```

报告包含分项得分、总分和结论，例如：

- **强烈推荐录取** — 综合得分 89/100
- **建议进入下一轮** — 综合得分 73/100

---

## 我是申请者 / 候选人 / B方

> 我想让数字分身替我参加初面，展示真实的我，同时也评估对方值不值得我去。

### 第一步：准备你的档案

在本机创建 `~/.openclaw/workspace/` 目录，填写三个文件：

```
~/.openclaw/workspace/
├── SOUL.md      # 你的性格、思维方式、做事风格
├── USER.md      # 你的背景：学历、项目经历、技能栈
└── MEMORY.md    # 你的求职动机、期望、顾虑
```

示例（博士申请者）：

```markdown
# USER.md
本科：XX大学计算机系，GPA 3.8
研究经历：参与过一篇 CVPR 论文，负责数据处理和实验复现
技能：PyTorch、Python、熟悉 Transformer 架构
申请方向：计算机视觉 / 多模态
```

> 档案内容在发送前会自动脱敏。

### 第二步：安装依赖并启动 Agent

```bash
pip install -r requirements.txt

python3 agents/applicant_agent.py --name "你的名字" --port 8002
```

### 第三步：等待撮合器启动

把你的地址（如 `http://192.168.1.20:8002`）告诉对方或撮合方，对话会自动开始。

### 第四步：查看双向评分

对话结束后你会看到两份报告：

- **对方对你的评分**：面试官从他的视角给你打分，包含每个维度的得分和建议
- **你对对方的评分**：裁判 AI 从你的视角评估这个导师/公司/对方值不值得你去

这意味着你不只是被评估的一方——你也在评估对方。

---

## 启动撮合器（任意一方或第三方）

双方 Agent 都启动后，运行撮合器开始对话：

```bash
python3 matchmaker.py \
  --agent-a http://面试官IP:8001 \
  --agent-b http://申请者IP:8002
```

本地测试（两个 Agent 在同一台机器）：

```bash
python3 matchmaker.py \
  --agent-a http://localhost:8001 \
  --agent-b http://localhost:8002
```

指定场景（默认 `academic_interview`）：

```bash
python3 matchmaker.py \
  -A http://localhost:8001 \
  -B http://localhost:8002 \
  --scenario dating
```

---

## 可用场景

| 场景名 | 说明 | 角色 A | 角色 B |
|---|---|---|---|
| `academic_interview` | 博士申请面试，学术考察 + 行为学考察（各3轮） | 导师 | 申请者 |
| `dating` | 相亲匹配，价值观 + 生活方式 + 未来规划（各2轮） | A方 | B方 |
| `job_matching` | 职场初面，技能评估 + 文化匹配（各2轮） | HR | 候选人 |

---

## 自定义档案路径

如果档案不在默认位置：

```bash
python3 agents/supervisor_agent.py \
  --name "Leo" --port 8001 \
  --soul /path/to/SOUL.md \
  --user /path/to/USER.md \
  --memory /path/to/MEMORY.md
```

---

## 项目结构

```
Agent-First-A2A/
├── agents/
│   ├── base_agent.py        # Agent 基础服务（FastAPI + LLM 调用）
│   ├── supervisor_agent.py  # 角色 A 入口
│   └── applicant_agent.py   # 角色 B 入口
├── matchmaker.py            # 撮合器：服务发现 + 对话编排 + 裁判调用
├── scenarios.py             # 场景定义（可扩展）
├── judge.py                 # 裁判 AI：双向评分 + 报告生成
├── sanitize.py              # 敏感信息脱敏
├── output/                  # 对话记录和报告（本地保存，不上传）
└── requirements.txt
```

---

## License

MIT
