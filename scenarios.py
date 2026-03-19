"""
scenarios.py — 克隆龙虾匹配场景定义

双向评估改造（新增字段）：
  - judge_criteria_b  : 评估 role_B 的维度（原 judge_criteria，由 role_A 视角评分）
  - judge_criteria_a  : 评估 role_A 的维度（新增，由 role_B 视角评分）
  - verdict_thresholds_b : role_B 的结论映射
  - verdict_thresholds_a : role_A 的结论映射（新增）

原字段 judge_criteria / verdict_thresholds 保留为 judge_criteria_b / verdict_thresholds_b 的别名，
供 evaluate_dual() 读取时向下兼容。
"""

SCENARIOS: dict = {

    # ── 学术面试 ──────────────────────────────────────────────────────────────
    "academic_interview": {
        "name": "学术面试",
        "description": "博士申请考核：学术考察（3轮）+ 行为学考察（3轮）",

        "role_A": "supervisor",
        "role_B": "applicant",
        "role_A_label": "导师",
        "role_B_label": "申请者",

        "judge_role": "资深学术评审专家",
        "judge_system": "你是专业学术面试评审专家，只输出合法 JSON，不输出任何其他内容。",

        # ── 分阶段 ──────────────────────────────────────────────────────────────
        "phases": [
            {
                "id":     "academic",
                "name":   "第一阶段：学术考察",
                "emoji":  "📚",
                "legend": "学术考察（3轮）· 研究背景 · 方法论 · 科研思维",
                "rounds": 3,
                "role_A_trigger": (
                    "面试正式开始，进入【学术考察阶段】。"
                    "请先请申请者做自我介绍，包括研究背景和主要科研项目经历。"
                    "之后根据其回答，围绕学科背景和研究方向深入提问。"
                ),
            },
            {
                "id":     "behavioral",
                "name":   "第二阶段：行为学考察",
                "emoji":  "🧠",
                "legend": "行为学考察（3轮）· 读博动机 · 分歧处理 · 抗压能力",
                "rounds": 3,
                "role_A_trigger": (
                    "学术考察部分已结束，进入【行为学考察阶段】。"
                    "请围绕三个维度依次考察：①科研动机，②抗压能力，③团队协作。"
                    "第一个问题：请申请者谈谈选择继续读博的核心动机是什么？"
                ),
            },
        ],

        # ── System Prompts ──────────────────────────────────────────────────────
        "system_prompts": {
            "supervisor": """\
你是一位资深科研导师。请结合你在 SOUL.md 和 MEMORY.md 中积累的领域知识，以导师身份主持本次博士申请面试。

面试结构：
- 第一阶段（前3轮）：学术考察。先请申请者自我介绍 + 介绍项目经历，再针对其背景深入提问，考察科研深度和创新思维。
- 第二阶段（后3轮）：行为学考察。依次考察：科研动机、抗压能力、团队协作。

行为准则：
- 每次提问简洁精准，不超过200字
- 根据申请者的回答灵活追问，不照本宣科
- 态度专业、温和而不失严格
- 在系统提示切换阶段时，自然过渡，无需提示"进入第X阶段"
- 直接输出对话内容，不要加任何前缀（如"Leo："、"🦁 Leo："等）
""",
            "applicant": """\
你是一位博士项目申请者，正在接受导师的考核面试。
请结合你自己 SOUL.md 和 MEMORY.md 中的研究背景和项目经历如实作答。

行为准则：
- 先正面回答导师的问题，再适当补充
- 回答简明扼要，每次不超过500字
- 不确定或不了解的内容，坦然承认，不要编造
- 展现真实的科研思维和学习态度
- 直接输出对话内容，不要加任何前缀（如"ddd："、"🦁 ddd："等）
""",
        },

        # ── 评分维度 A（导师视角评申请者）────────────────────────────────────────
        "judge_criteria_b": [
            # 学术阶段 (50分)
            {"name": "研究背景与方向契合度",   "max_score": 20, "phase": "academic"},
            {"name": "科研思维深度与创新性",   "max_score": 20, "phase": "academic"},
            {"name": "学术表达与逻辑清晰度",   "max_score": 10, "phase": "academic"},
            # 行为阶段 (40分)
            {"name": "科研动机清晰度与真实性", "max_score": 15, "phase": "behavioral"},
            {"name": "抗压能力与处理模糊性",   "max_score": 15, "phase": "behavioral"},
            {"name": "团队协作与沟通风格",     "max_score": 10, "phase": "behavioral"},
            # 综合印象 (10分)
            {"name": "综合潜力印象",           "max_score": 10, "phase": "overall"},
        ],
        "verdict_thresholds_b": [
            (85, "强烈推荐录取"),
            (70, "建议进入下一轮"),
            (55, "持保留意见，需补充考察"),
            (0,  "不建议录取"),
        ],

        # ── 评分维度 B（申请者视角评导师）────────────────────────────────────────
        # 申请者在这场面试中对导师的综合印象：实验室值不值得去？
        "judge_criteria_a": [
            # 学术阶段感受 (45分)
            {"name": "研究方向吸引力与清晰度",   "max_score": 20, "phase": "academic"},
            {"name": "面试问题质量与是否有效考察", "max_score": 15, "phase": "academic"},
            {"name": "对申请者背景的理解深度",   "max_score": 10, "phase": "academic"},
            # 行为阶段感受 (40分)
            {"name": "导师风格与沟通方式",       "max_score": 20, "phase": "behavioral"},
            {"name": "培养意愿与支持态度",       "max_score": 20, "phase": "behavioral"},
            # 综合 (15分)
            {"name": "综合意向：是否想加入该课题组", "max_score": 15, "phase": "overall"},
        ],
        "verdict_thresholds_a": [
            (85, "非常理想，强烈意向加入"),
            (70, "有合作意向，值得深入了解"),
            (55, "存在顾虑，需进一步了解"),
            (0,  "暂无加入意向"),
        ],
    },

    # ── 相亲匹配 ──────────────────────────────────────────────────────────────
    "dating": {
        "name": "相亲匹配",
        "description": "两人数字分身先聊一轮：价值观（2轮）+ 生活方式（2轮）+ 未来规划（2轮）",

        "role_A": "person_a",
        "role_B": "person_b",
        "role_A_label": "A方",
        "role_B_label": "B方",

        "judge_role": "专业婚恋匹配顾问",
        "judge_system": "你是专业的婚恋匹配顾问，只输出合法 JSON，不输出任何其他内容。",

        "phases": [
            {
                "id": "values", "name": "第一阶段：价值观探索",
                "emoji": "💡", "legend": "价值观（2轮）· 世界观 · 家庭观 · 人生优先级",
                "rounds": 2,
                "role_A_trigger": (
                    "相亲开始，进入【价值观探索阶段】。"
                    "请先做一个简单的自我介绍，然后聊聊你对家庭和人生中最重要的事情的看法。"
                ),
            },
            {
                "id": "lifestyle", "name": "第二阶段：生活方式",
                "emoji": "🌱", "legend": "生活方式（2轮）· 日常习惯 · 兴趣爱好 · 生活节奏",
                "rounds": 2,
                "role_A_trigger": (
                    "进入【生活方式阶段】。"
                    "请聊聊你的日常生活节奏、兴趣爱好，以及理想的周末是怎么过的。"
                ),
            },
            {
                "id": "future", "name": "第三阶段：未来规划",
                "emoji": "🔭", "legend": "未来规划（2轮）· 职业发展 · 居住计划 · 长期目标",
                "rounds": 2,
                "role_A_trigger": (
                    "进入【未来规划阶段】。"
                    "请聊聊你未来3-5年的职业规划，以及对定居城市和家庭组建的想法。"
                ),
            },
        ],

        "system_prompts": {
            "person_a": """\
你正在参与一次相亲匹配。请结合你在 SOUL.md 和 MEMORY.md 中的个人信息，真实、自然地与对方交流。
行为准则：语气轻松自然，主动提问，如实分享，每次回答 200 字以内。
""",
            "person_b": """\
你正在参与一次相亲匹配。请结合你在 SOUL.md 和 MEMORY.md 中的个人信息，真实、自然地与对方交流。
行为准则：语气轻松自然，主动回应并适当提问，如实分享，每次回答 200 字以内。
""",
        },

        # A方（先发起方）从 B方（回应方）视角评分
        "judge_criteria_b": [
            {"name": "价值观契合度",       "max_score": 25, "phase": "values"},
            {"name": "沟通方式与节奏匹配", "max_score": 20, "phase": "lifestyle"},
            {"name": "生活方式兼容性",     "max_score": 20, "phase": "lifestyle"},
            {"name": "未来规划一致性",     "max_score": 25, "phase": "future"},
            {"name": "整体印象与自然度",   "max_score": 10, "phase": "overall"},
        ],
        "verdict_thresholds_b": [
            (80, "强烈推荐见面"),
            (65, "建议见面"),
            (50, "可以再聊聊"),
            (0,  "暂不建议见面"),
        ],

        # B方对 A方的好感度（A方视角：B方值不值得见面）
        "judge_criteria_a": [
            {"name": "真实性与坦诚度",   "max_score": 25, "phase": "values"},
            {"name": "沟通吸引力",       "max_score": 25, "phase": "lifestyle"},
            {"name": "价值观认同度",     "max_score": 25, "phase": "values"},
            {"name": "整体好感与见面意向", "max_score": 25, "phase": "overall"},
        ],
        "verdict_thresholds_a": [
            (80, "很有好感，非常愿意见面"),
            (65, "有好感，愿意见面"),
            (50, "好感一般，再考虑"),
            (0,  "暂无见面意向"),
        ],
    },

    # ── 职场对接 ──────────────────────────────────────────────────────────────
    "job_matching": {
        "name": "职场对接",
        "description": "候选人数字分身与 HR 数字分身完成初面：技能评估（2轮）+ 文化匹配（2轮）",

        "role_A": "recruiter",
        "role_B": "candidate",
        "role_A_label": "HR",
        "role_B_label": "候选人",

        "judge_role": "资深企业招聘顾问",
        "judge_system": "你是专业的企业招聘顾问，只输出合法 JSON，不输出任何其他内容。",

        "phases": [
            {
                "id": "skills", "name": "第一阶段：技能与经验评估",
                "emoji": "🛠️", "legend": "技能评估（2轮）· 专业能力 · 项目经历 · 解决问题的方式",
                "rounds": 2,
                "role_A_trigger": (
                    "初面开始，进入【技能与经验评估阶段】。"
                    "请先请候选人做自我介绍，重点介绍和岗位相关的项目经历和核心技能。"
                ),
            },
            {
                "id": "culture", "name": "第二阶段：文化与动机匹配",
                "emoji": "🤝", "legend": "文化匹配（2轮）· 工作动机 · 团队风格 · 职业发展期待",
                "rounds": 2,
                "role_A_trigger": (
                    "进入【文化与动机匹配阶段】。"
                    "请问候选人：选择我们公司的核心原因是什么？"
                    "期待的工作氛围和职业发展路径是怎样的？"
                ),
            },
        ],

        "system_prompts": {
            "recruiter": """\
你是公司的招聘负责人，正在进行一场职位初面。
请结合你在 SOUL.md 和 MEMORY.md 中的公司信息和岗位需求进行面试。
行为准则：问题聚焦，每次不超过150字；追问细节；保持专业友善。
""",
            "candidate": """\
你是一位求职候选人，正在参加职位初面。
请结合你在 SOUL.md 和 MEMORY.md 中的个人背景如实作答。
行为准则：结构清晰，突出重点，每次不超过400字；诚实展现经历；适当提问。
""",
        },

        # HR视角评候选人
        "judge_criteria_b": [
            {"name": "岗位技能匹配度",     "max_score": 30, "phase": "skills"},
            {"name": "项目经验深度",       "max_score": 20, "phase": "skills"},
            {"name": "工作动机真实性",     "max_score": 20, "phase": "culture"},
            {"name": "文化与团队契合度",   "max_score": 20, "phase": "culture"},
            {"name": "综合潜力与成长性",   "max_score": 10, "phase": "overall"},
        ],
        "verdict_thresholds_b": [
            (80, "强烈推荐进入下一轮"),
            (65, "建议进入下一轮"),
            (50, "保留候选人资料"),
            (0,  "本轮不通过"),
        ],

        # 候选人视角评公司/HR
        "judge_criteria_a": [
            {"name": "岗位描述清晰度与吸引力", "max_score": 30, "phase": "skills"},
            {"name": "公司文化传递与认同感",   "max_score": 25, "phase": "culture"},
            {"name": "面试体验与专业度",       "max_score": 25, "phase": "skills"},
            {"name": "职业发展空间表达",       "max_score": 20, "phase": "culture"},
        ],
        "verdict_thresholds_a": [
            (80, "非常感兴趣，强烈意向接受"),
            (65, "有兴趣，愿意进入下一步"),
            (50, "兴趣一般，还在考虑"),
            (0,  "兴趣不足，暂不考虑"),
        ],
    },
}


def get_scenario(name: str) -> dict:
    """获取场景配置，name 不存在时抛出 ValueError"""
    if name not in SCENARIOS:
        available = ", ".join(SCENARIOS.keys())
        raise ValueError(f"未知场景: '{name}'，可用场景: {available}")
    return SCENARIOS[name]


def list_scenarios() -> list[str]:
    return [
        f"  {key}: {val['description']}"
        for key, val in SCENARIOS.items()
    ]
