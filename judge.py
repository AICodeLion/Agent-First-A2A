"""
judge.py — 克隆龙虾裁判 LLM（通用多场景版）

双向评估版：
  - evaluate_dual(): 并行调用两次裁判 LLM，返回 {report_a, report_b}
    - report_b: role_A 视角评 role_B（原有方向，使用 judge_criteria_b）
    - report_a: role_B 视角评 role_A（新增，使用 judge_criteria_a）
  - _build_judge_prompt_b(): 原有 prompt，role_A 评 role_B
  - _build_judge_prompt_a(): 新增 prompt，role_B 评 role_A
  - save_report(): 接收 dual_report dict，保存两份 JSON+MD
  - print_summary(): 打印双向结论对比

单向兼容：evaluate() 保留为向下兼容接口（调用 evaluate_dual 取 report_b）
"""

import json
import re
from datetime import datetime
from pathlib import Path

import anthropic

# ── LLM 配置 ──────────────────────────────────────────────────────────────────
MINIMAX_BASE_URL = "https://api.minimaxi.com/anthropic"
MINIMAX_API_KEY  = "sk-cp-TRZ3kVSSzHdr4YVMW4rtzWdZhU6dvC_ZT3LhIdqOfKUKBE_1lZa_tqXnCo4QZstB3RxiO6YtsFvX3zYud3vskbG7W0t2AgNosSCscV9vPLN2L-MNWGpYwO8"
MODEL            = "MiniMax-M2.5"


# ── 工具函数 ────────────────────────────────────────────────────────────────────

def _format_transcript(history: list[dict], scenario: dict = None) -> str:
    """把 history 格式化成裁判可读的纯文本。
    通用化：从 scenario.phases 动态读取阶段标签，不再硬编码 academic/behavioral。
    """
    if scenario:
        phase_labels = {p["id"]: f"【{p['name']}】" for p in scenario.get("phases", [])}
    else:
        phase_labels = {}

    lines = []
    current_phase = None
    for entry in history:
        phase = entry.get("phase", "")
        if phase != current_phase:
            current_phase = phase
            label = phase_labels.get(phase, f"【{phase}】")
            lines.append(f"\n{label}")
        role_label = entry.get("role_label", entry["speaker"])
        lines.append(f"{entry['speaker']}（{role_label}）：{entry['content']}")
    return "\n\n".join(lines)


def _criteria_text(criteria: list[dict]) -> str:
    return "\n".join(
        f"- {c['name']}（满分 {c['max_score']} 分，阶段：{c['phase']}）"
        for c in criteria
    )


def _scores_template(criteria: list[dict]) -> str:
    return ",\n    ".join(
        f'"{c["name"]}": <0–{c["max_score"]} 的整数>'
        for c in criteria
    )


def _phase_fields_template(scenario: dict) -> str:
    """动态生成裁判 JSON 中的各阶段评估字段模板（排除 overall）"""
    fields = []
    for p in scenario.get("phases", []):
        if p["id"] == "overall":
            continue
        fields.append(
            f'  "phase_{p["id"]}": {{\n'
            f'    "strengths": ["<{p["name"]}亮点1>", "<亮点2>"],\n'
            f'    "weaknesses": ["<{p["name"]}不足1>"]\n'
            f'  }}'
        )
    return ",\n".join(fields)


def _verdict_from_score(score: int, thresholds: list[tuple]) -> str:
    for threshold, label in thresholds:
        if score >= threshold:
            return label
    return "参考报告"


def _call_judge_llm(judge_system: str, judge_prompt: str) -> dict:
    """调用裁判 LLM，返回解析后的 dict。出错时返回含 error 键的 dict。"""
    client = anthropic.Anthropic(api_key=MINIMAX_API_KEY, base_url=MINIMAX_BASE_URL)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=judge_system,
            messages=[{"role": "user", "content": judge_prompt}],
        )
        raw = next((b.text for b in response.content if b.type == "text"), "").strip()

        # 清理可能的 ```json ... ``` 包裹
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()

        # 提取第一个完整 JSON 对象（防止 LLM 追加额外文字）
        brace_count, end_idx = 0, 0
        for i, ch in enumerate(raw):
            if ch == "{":
                brace_count += 1
            elif ch == "}":
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i + 1
                    break
        if end_idx:
            raw = raw[:end_idx]

        return json.loads(raw)

    except json.JSONDecodeError as e:
        print(f"  ❌ JSON 解析失败: {e}\n  原始输出: {raw[:300]}")
        return {"error": "JSON 解析失败", "raw": raw, "generated_at": datetime.now().isoformat()}
    except Exception as e:
        print(f"  ❌ 裁判 LLM 调用失败: {e}")
        return {"error": str(e), "generated_at": datetime.now().isoformat()}


# ── 构建 Judge Prompt（双向）────────────────────────────────────────────────────

def _build_judge_prompt_b(
    scenario:   dict,
    name_A:     str,
    name_B:     str,
    transcript: str,
) -> str:
    """role_A 视角评 role_B（原有方向）"""
    criteria      = scenario["judge_criteria_b"]
    total_max     = sum(c["max_score"] for c in criteria)
    scenario_name = scenario["name"]
    judge_role    = scenario.get("judge_role", "专业评审专家")
    label_A       = scenario["role_A_label"]
    label_B       = scenario["role_B_label"]

    return f"""\
你是一位{judge_role}。请根据以下对话记录，站在【{label_A}】{name_A} 的视角，对【{label_B}】{name_B} 的表现进行客观、独立的评估。

## 场景
{scenario_name}（{label_A}：{name_A}，{label_B}：{name_B}）

## 评分维度（满分 {total_max} 分）
{_criteria_text(criteria)}

## 对话记录
{transcript}

## 输出要求
严格按照以下 JSON 格式输出，**不要有任何额外文字、markdown 包裹或注释**：

{{
  "scenario": "{scenario_name}",
  "role_a_label": "{label_A}",
  "role_b_label": "{label_B}",
  "name_a": "{name_A}",
  "name_b": "{name_B}",
  "evaluator_perspective": "{label_A}评{label_B}",
  "total_score": <整数>,
  "total_max": {total_max},
  "scores": {{
    {_scores_template(criteria)}
  }},
{_phase_fields_template(scenario)},
  "key_moments": ["<对话中最值得关注的时刻1>", "<时刻2>"],
  "concerns": ["<主要顾虑1>", "<主要顾虑2>"],
  "blind_spots": ["<双方都未深入探讨的重要问题>"],
  "recommendation": "<100字以内的综合评估与建议>",
  "generated_at": "{datetime.now().isoformat()}"
}}
"""


def _build_judge_prompt_a(
    scenario:   dict,
    name_A:     str,
    name_B:     str,
    transcript: str,
) -> str:
    """role_B 视角评 role_A（新增方向）"""
    criteria      = scenario["judge_criteria_a"]
    total_max     = sum(c["max_score"] for c in criteria)
    scenario_name = scenario["name"]
    judge_role    = scenario.get("judge_role", "专业评审专家")
    label_A       = scenario["role_A_label"]
    label_B       = scenario["role_B_label"]

    return f"""\
你是一位{judge_role}。请根据以下对话记录，站在【{label_B}】{name_B} 的视角，对【{label_A}】{name_A} 的表现进行客观、独立的评估。

## 场景
{scenario_name}（{label_A}：{name_A}，{label_B}：{name_B}）

## 评分维度（满分 {total_max} 分）
{_criteria_text(criteria)}

## 对话记录
{transcript}

## 输出要求
严格按照以下 JSON 格式输出，**不要有任何额外文字、markdown 包裹或注释**：

{{
  "scenario": "{scenario_name}",
  "role_a_label": "{label_A}",
  "role_b_label": "{label_B}",
  "name_a": "{name_A}",
  "name_b": "{name_B}",
  "evaluator_perspective": "{label_B}评{label_A}",
  "total_score": <整数>,
  "total_max": {total_max},
  "scores": {{
    {_scores_template(criteria)}
  }},
{_phase_fields_template(scenario)},
  "key_moments": ["<对话中最值得关注的时刻1>", "<时刻2>"],
  "concerns": ["<主要顾虑1>", "<主要顾虑2>"],
  "blind_spots": ["<双方都未深入探讨的重要问题>"],
  "recommendation": "<100字以内的综合评估与建议>",
  "generated_at": "{datetime.now().isoformat()}"
}}
"""


# ── 核心：后处理单份报告 ─────────────────────────────────────────────────────────

def _finalize_report(
    report:     dict,
    scenario:   dict,
    criteria:   list[dict],
    thresholds: list[tuple],
) -> dict:
    """补全 verdict、None 回退、辅助字段。"""
    if "error" in report:
        return report

    # verdict
    score = report.get("total_score", 0)
    if isinstance(score, str):
        try:
            score = int(score)
        except ValueError:
            score = 0
    report["total_score"] = score
    report["verdict"] = _verdict_from_score(score, thresholds)

    # None 字段回退
    for field in ("recommendation", "concerns", "blind_spots", "key_moments"):
        if report.get(field) is None:
            report[field] = [] if field != "recommendation" else ""

    # generated_at 回退
    if not report.get("generated_at"):
        report["generated_at"] = datetime.now().isoformat()

    # 辅助字段（供外部工具使用）
    report["score_maxes"] = {c["name"]: c["max_score"] for c in criteria}
    report["phases_info"] = [
        {"id": p["id"], "name": p["name"],
         "emoji": p.get("emoji", ""), "legend": p.get("legend", "")}
        for p in scenario["phases"]
        if p["id"] != "overall"
    ]

    return report


# ── 主函数：双向评估 ──────────────────────────────────────────────────────────────

def evaluate_dual(
    scenario: dict,
    name_A:   str,
    name_B:   str,
    history:  list[dict],
) -> dict:
    """
    双向评估：串行调用两次裁判 LLM，返回：
      {
        "report_b": {...},   # role_A 视角评 role_B
        "report_a": {...},   # role_B 视角评 role_A
      }
    """
    label_A = scenario["role_A_label"]
    label_B = scenario["role_B_label"]

    transcript    = _format_transcript(history, scenario)
    judge_system  = scenario.get("judge_system", "你是专业评审专家，只输出合法 JSON，不输出任何其他内容。")

    # ── report_b：role_A 视角评 role_B ──────────────────────────────────────────
    print(f"\n🧑‍⚖️  裁判 LLM 评估中（{label_A} 视角 → 评 {label_B}）...", flush=True)
    prompt_b  = _build_judge_prompt_b(scenario, name_A, name_B, transcript)
    report_b  = _call_judge_llm(judge_system, prompt_b)
    criteria_b    = scenario["judge_criteria_b"]
    thresholds_b  = scenario.get("verdict_thresholds_b", [(0, "参考报告")])
    report_b  = _finalize_report(report_b, scenario, criteria_b, thresholds_b)
    if "error" not in report_b:
        print(f"  ✅ 完成 | 总分 {report_b['total_score']}/{report_b.get('total_max','?')} | {report_b['verdict']}")

    # ── report_a：role_B 视角评 role_A ──────────────────────────────────────────
    print(f"\n🧑‍⚖️  裁判 LLM 评估中（{label_B} 视角 → 评 {label_A}）...", flush=True)
    prompt_a  = _build_judge_prompt_a(scenario, name_A, name_B, transcript)
    report_a  = _call_judge_llm(judge_system, prompt_a)
    criteria_a    = scenario["judge_criteria_a"]
    thresholds_a  = scenario.get("verdict_thresholds_a", [(0, "参考报告")])
    report_a  = _finalize_report(report_a, scenario, criteria_a, thresholds_a)
    if "error" not in report_a:
        print(f"  ✅ 完成 | 总分 {report_a['total_score']}/{report_a.get('total_max','?')} | {report_a['verdict']}")

    return {"report_b": report_b, "report_a": report_a}


def evaluate(
    scenario: dict,
    name_A:   str,
    name_B:   str,
    history:  list[dict],
) -> dict:
    """
    向下兼容接口：只返回 report_b（role_A 视角评 role_B）。
    新代码请改用 evaluate_dual()。
    """
    dual = evaluate_dual(scenario, name_A, name_B, history)
    return dual["report_b"]


# ── 保存报告 ─────────────────────────────────────────────────────────────────────

def save_report(
    dual_report: dict,
    save_dir:    Path,
    timestamp:   str,
    scenario:    dict = None,
) -> tuple[Path, ...]:
    """
    保存双向评估报告。
    dual_report 为 evaluate_dual() 的返回值 {report_a, report_b}，
    也向下兼容直接传入单份 report dict（旧接口）。

    返回保存的文件路径元组。
    """
    save_dir.mkdir(parents=True, exist_ok=True)
    saved = []

    # 兼容旧式单报告调用
    if "report_a" not in dual_report and "report_b" not in dual_report:
        # 旧接口：直接传入单份报告
        json_path = save_dir / f"{timestamp}-report.json"
        json_path.write_text(json.dumps(dual_report, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path = save_dir / f"{timestamp}-report.md"
        md_path.write_text(_render_markdown(dual_report, scenario), encoding="utf-8")
        print(f"  📊 JSON 报告：{json_path}")
        print(f"  📄 MD 报告：{md_path}")
        return (json_path, md_path)

    # ── 双向报告 ────────────────────────────────────────────────────────────────
    report_b = dual_report.get("report_b", {})
    report_a = dual_report.get("report_a", {})

    label_A = (scenario or {}).get("role_A_label", report_b.get("role_a_label", "A方"))
    label_B = (scenario or {}).get("role_B_label", report_b.get("role_b_label", "B方"))

    # report_b：role_A 视角评 role_B
    json_b = save_dir / f"{timestamp}-report-b.json"
    json_b.write_text(json.dumps(report_b, ensure_ascii=False, indent=2), encoding="utf-8")
    md_b   = save_dir / f"{timestamp}-report-b.md"
    md_b.write_text(_render_markdown(report_b, scenario, title=f"{label_A}评{label_B}"), encoding="utf-8")
    print(f"  📊 {label_A}评{label_B} JSON：{json_b}")
    print(f"  📄 {label_A}评{label_B} MD：{md_b}")
    saved += [json_b, md_b]

    # report_a：role_B 视角评 role_A
    json_a = save_dir / f"{timestamp}-report-a.json"
    json_a.write_text(json.dumps(report_a, ensure_ascii=False, indent=2), encoding="utf-8")
    md_a   = save_dir / f"{timestamp}-report-a.md"
    md_a.write_text(_render_markdown(report_a, scenario, title=f"{label_B}评{label_A}"), encoding="utf-8")
    print(f"  📊 {label_B}评{label_A} JSON：{json_a}")
    print(f"  📄 {label_B}评{label_A} MD：{md_a}")
    saved += [json_a, md_a]

    return tuple(saved)


def _render_markdown(report: dict, scenario: dict = None, title: str = "") -> str:
    if "error" in report:
        return f"# ❌ 评估失败\n\n{report.get('error')}\n\n```\n{report.get('raw','')}\n```\n"

    score     = report.get("total_score", "?")
    total_max = report.get("total_max", 100)
    pct       = round(score / total_max * 100) if isinstance(score, int) else "?"
    verdict   = report.get("verdict", "")
    scenario_name = report.get("scenario", "")
    label_A   = report.get("role_a_label", "角色A")
    label_B   = report.get("role_b_label", "角色B")
    name_A    = report.get("name_a", report.get("supervisor", ""))
    name_B    = report.get("name_b", report.get("applicant", ""))
    perspective = report.get("evaluator_perspective", title or f"{label_A}评{label_B}")

    verdict_emojis = {
        "强烈推荐录取": "🟢", "建议进入下一轮": "🔵",
        "持保留意见，需补充考察": "🟡", "不建议录取": "🔴",
        "强烈推荐见面": "🟢", "建议见面": "🔵",
        "可以再聊聊": "🟡", "暂不建议见面": "🔴",
        "强烈推荐进入下一轮": "🟢", "保留候选人资料": "🟡",
        "本轮不通过": "🔴",
        "非常理想，强烈意向加入": "🟢", "有合作意向，值得深入了解": "🔵",
        "存在顾虑，需进一步了解": "🟡", "暂无加入意向": "🔴",
        "很有好感，非常愿意见面": "🟢", "有好感，愿意见面": "🔵",
        "好感一般，再考虑": "🟡", "暂无见面意向": "🔴",
        "非常感兴趣，强烈意向接受": "🟢", "有兴趣，愿意进入下一步": "🔵",
        "兴趣一般，还在考虑": "🟡", "兴趣不足，暂不考虑": "🔴",
    }
    verdict_emoji = verdict_emojis.get(verdict, "⚪")

    def ul(items):
        return "\n".join(f"- {x}" for x in (items or ["（无）"]))

    # scores 可能是 dict 或 list（LLM 偶发返回 list）
    raw_scores = report.get("scores", {})
    if isinstance(raw_scores, list):
        scores_md = "\n".join(f"| {item.get('name','?')} | {item.get('score','?')} |" for item in raw_scores)
    else:
        scores_md = "\n".join(f"| {k} | {v} |" for k, v in raw_scores.items())

    # 动态生成各阶段评估 section
    phases_list = scenario.get("phases", []) if scenario else []
    if not phases_list:
        phases_list = report.get("phases_info", [])
    phases_sections = ""
    for p in phases_list:
        if p["id"] == "overall":
            continue
        key  = f"phase_{p['id']}"
        data = report.get(key, {})
        phases_sections += f"""
## {p['name']}

**亮点**
{ul(data.get('strengths', []))}

**不足**
{ul(data.get('weaknesses', []))}

---"""

    return f"""# 🦞 克隆龙虾 · 评估报告（{perspective}）

**场景**：{scenario_name}
**{label_A}**：{name_A}　**{label_B}**：{name_B}
**评估视角**：{perspective}
**生成时间**：{report.get('generated_at', '')}

---

## 综合结论

> {verdict_emoji} **{verdict}**

**总分：{score} / {total_max}（{pct}%）**

{report.get('recommendation', '')}

---

## 分项评分

| 维度 | 得分 |
|------|------|
{scores_md}

---
{phases_sections}

## 关键时刻

{ul(report.get('key_moments', []))}

## 主要顾虑

{ul(report.get('concerns', []))}

## 未深入的盲区

{ul(report.get('blind_spots', []))}
"""


# ── 终端打印摘要 ──────────────────────────────────────────────────────────────────

def print_summary(dual_report: dict) -> None:
    """
    打印双向评估结论对比。
    兼容单份报告 dict（旧接口）。
    """
    # 兼容旧接口
    if "report_a" not in dual_report and "report_b" not in dual_report:
        _print_single_summary(dual_report)
        return

    report_b = dual_report.get("report_b", {})
    report_a = dual_report.get("report_a", {})

    label_A = report_b.get("role_a_label", "A方")
    label_B = report_b.get("role_b_label", "B方")
    name_A  = report_b.get("name_a", "")
    name_B  = report_b.get("name_b", "")

    print("\n" + "=" * 60)
    print(f"  🦞 双向评估结论")
    print("=" * 60)

    # report_b：A评B
    if "error" in report_b:
        print(f"  ❌ {label_A}评{label_B}：{report_b['error']}")
    else:
        score_b = report_b.get("total_score", "?")
        max_b   = report_b.get("total_max", 100)
        print(f"  📋 {label_A}（{name_A}）评 {label_B}（{name_B}）")
        print(f"     总分  : {score_b} / {max_b}")
        print(f"     结论  : {report_b.get('verdict', '')}")
        print(f"     建议  : {report_b.get('recommendation', '')}")

    print()

    # report_a：B评A
    if "error" in report_a:
        print(f"  ❌ {label_B}评{label_A}：{report_a['error']}")
    else:
        score_a = report_a.get("total_score", "?")
        max_a   = report_a.get("total_max", 100)
        print(f"  📋 {label_B}（{name_B}）评 {label_A}（{name_A}）")
        print(f"     总分  : {score_a} / {max_a}")
        print(f"     结论  : {report_a.get('verdict', '')}")
        print(f"     建议  : {report_a.get('recommendation', '')}")

    print("=" * 60)


def _print_single_summary(report: dict) -> None:
    if "error" in report:
        print(f"\n❌ 报告生成失败: {report['error']}")
        return

    score   = report.get("total_score", "?")
    total   = report.get("total_max", 100)
    verdict = report.get("verdict", "")
    rec     = report.get("recommendation", "")
    label_B = report.get("role_b_label", "评估对象")
    name_B  = report.get("name_b", report.get("applicant", ""))

    print("\n" + "=" * 60)
    print(f"  🦞 评估结果  · {label_B}：{name_B}")
    print("=" * 60)
    print(f"  总分    : {score} / {total}")
    print(f"  结论    : {verdict}")
    print(f"  建议    : {rec}")
    print("=" * 60)
