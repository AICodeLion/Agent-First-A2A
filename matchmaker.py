"""
matchmaker.py — A2A 撮合器（通用多场景版）

通用化改造：
  - run_interview(): 从 scenario 动态读取 role_A/role_B，不再硬编码 supervisor/applicant
  - save_transcript(): 从 scenario.phases 动态生成阶段标签，不再硬编码
  - main(): CLI 参数改为通用的 --agent-a/--agent-b（保留 --supervisor/--applicant 作别名）

流程：
  1. 分别请求双方 /.well-known/agent.json（A2A 服务发现）
  2. 按场景分阶段，role_A 先说，role_B 后说
  3. 对话结束后裁判 LLM 生成结构化报告
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx

from scenarios import get_scenario, list_scenarios
import judge as judge_module

SAVE_DIR = Path(__file__).parent / "output"


# ── A2A 服务发现 ───────────────────────────────────────────────────────────────

def discover_agent(base_url: str) -> dict:
    """请求对方 /.well-known/agent.json 拿到 Agent Card"""
    url = base_url.rstrip("/") + "/.well-known/agent.json"
    try:
        resp = httpx.get(url, timeout=5)
        resp.raise_for_status()
        card = resp.json()
        print(f"  ✅ 发现 Agent：{card['name']} @ {base_url}")
        return card
    except Exception as e:
        print(f"  ❌ 无法连接 {url}: {e}")
        sys.exit(1)


# ── 视角转换 ────────────────────────────────────────────────────────────────────

def to_perspective(history: list[dict], recipient: str) -> list[dict]:
    """
    把共享历史转成 recipient 视角的 user/assistant 消息列表。
      recipient 说的 → "assistant"（自己之前说的）
      另一方说的     → "user"（对方说的，需要回应）
    """
    return [
        {
            "role":    "assistant" if entry["speaker"] == recipient else "user",
            "content": entry["content"],
        }
        for entry in history
    ]


# ── A2A 任务调用 ───────────────────────────────────────────────────────────────

def send_task(
    agent_url: str,
    history:   list[dict],
    recipient: str,
    metadata:  dict = {},
) -> str:
    url  = agent_url.rstrip("/") + "/tasks/send"
    body = {
        "messages": to_perspective(history, recipient),
        "metadata": metadata,
    }
    resp = httpx.post(url, json=body, timeout=60)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


# ── 分阶段对话驱动 ─────────────────────────────────────────────────────────────

def run_interview(
    scenario: dict,
    url_A:    str,
    url_B:    str,
    name_A:   str,
    name_B:   str,
) -> list[dict]:
    """
    按场景 phases 驱动对话，返回带 speaker 标记的 history。

    通用化：role_A/role_B 从 scenario 读取，不再硬编码 supervisor/applicant。
    """
    history: list[dict] = []

    role_A = scenario["role_A"]
    role_B = scenario["role_B"]

    urls   = {role_A: url_A,   role_B: url_B}
    names  = {role_A: name_A,  role_B: name_B}
    labels = {role_A: scenario["role_A_label"], role_B: scenario["role_B_label"]}

    for phase in scenario["phases"]:
        print(f"\n{'='*60}")
        print(f"  {phase['name']}（{phase['rounds']} 轮）")
        print(f"{'='*60}\n")

        for round_num in range(phase["rounds"]):
            # role_A 先说，role_B 后说
            for role_key in [role_A, role_B]:
                name  = names[role_key]
                label = labels[role_key]
                url   = urls[role_key]

                print(f"\033[2m[{phase['name']} · 第 {round_num+1} 轮 · {label} {name}]\033[0m")
                print(f"\033[1m{name}（{label}）：\033[0m", flush=True)

                metadata: dict = {"phase": phase["id"], "round": round_num + 1}

                # 首轮或新阶段首轮：注入 role_A 的触发指令
                trigger = phase.get("role_A_trigger", "")
                if trigger and role_key == role_A:
                    if not history or round_num == 0:
                        metadata["trigger"] = trigger

                try:
                    reply = send_task(url, history, role_key, metadata)
                except Exception as e:
                    reply = f"[调用失败: {e}]"
                    print(f"\033[31m{reply}\033[0m")

                print(reply)
                print()

                history.append({
                    "speaker":    role_key,
                    "name":       name,
                    "role_label": label,
                    "content":    reply,
                    "phase":      phase["id"],
                    "round":      round_num + 1,
                })

    return history


# ── 保存对话记录 ───────────────────────────────────────────────────────────────

def save_transcript(
    scenario: dict,
    name_A:   str,
    name_B:   str,
    history:  list[dict],
    timestamp: str,
) -> Path:
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    filepath = SAVE_DIR / f"{timestamp}-chat.md"

    # 从 scenario.phases 动态生成阶段标签映射，不再硬编码
    phase_labels = {p["id"]: p["name"] for p in scenario["phases"]}

    lines = [
        f"# TutorClaw A2A · 对话记录\n",
        f"**场景**：{scenario['name']}\n",
        f"**{scenario['role_A_label']}**：{name_A}　**{scenario['role_B_label']}**：{name_B}\n",
        f"**时间**：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        "\n---\n",
    ]

    current_phase = None
    for entry in history:
        if entry["phase"] != current_phase:
            current_phase = entry["phase"]
            label = phase_labels.get(current_phase, current_phase)
            lines.append(f"\n## {label}\n")
        lines.append(
            f"### {entry['name']}（{entry['role_label']}）\n{entry['content']}\n\n"
        )

    filepath.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n📄 对话记录：{filepath}")
    return filepath


# ── 构建裁判所需的 history 格式 ────────────────────────────────────────────────

def to_judge_history(history: list[dict]) -> list[dict]:
    """matchmaker history → judge.evaluate 所需格式"""
    return [
        {
            "speaker":    entry["name"],
            "role_label": entry["role_label"],
            "content":    entry["content"],
            "phase":      entry["phase"],
        }
        for entry in history
    ]


# ── 主程序 ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="A2A 撮合器：发现双方 Agent，驱动对话，输出评估报告",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
可用场景：
{"".join(list_scenarios())}

示例（学术面试）:
  python3 matchmaker.py \\
    --agent-a http://192.168.1.10:8001 \\
    --agent-b http://192.168.1.20:8002 \\
    --scenario academic_interview

示例（本地测试，双 Agent 同一台机器）:
  python3 matchmaker.py \\
    --agent-a http://localhost:8001 \\
    --agent-b http://localhost:8002
        """,
    )
    # 通用参数名（--agent-a / --agent-b）兼容旧参数（--supervisor / --applicant）
    parser.add_argument("--agent-a", "--supervisor", "-A", required=True,
                        dest="agent_a",
                        help="角色 A 的 Agent 地址，例如 http://用户A的IP:8001")
    parser.add_argument("--agent-b", "--applicant",  "-B", required=True,
                        dest="agent_b",
                        help="角色 B 的 Agent 地址，例如 http://用户B的IP:8002")
    parser.add_argument("--scenario", "-sc", default="academic_interview",
                        help=f"场景名称（默认 academic_interview）")
    args = parser.parse_args()

    scenario = get_scenario(args.scenario)
    print(f"\n🦞 TutorClaw A2A · {scenario['name']}")
    print(f"   {scenario['description']}\n")

    # ── 1. A2A 服务发现 ────────────────────────────────────────────────────────
    print("🔍 A2A 服务发现...")
    card_A = discover_agent(args.agent_a)
    card_B = discover_agent(args.agent_b)
    name_A = card_A["name"]
    name_B = card_B["name"]
    print(f"\n   {scenario['role_A_label']}：{name_A} | {scenario['role_B_label']}：{name_B}\n")

    # ── 2. 分阶段对话 ──────────────────────────────────────────────────────────
    history = run_interview(
        scenario, args.agent_a, args.agent_b, name_A, name_B,
    )

    # ── 3. 保存对话记录 ────────────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
    save_transcript(scenario, name_A, name_B, history, timestamp)

    # ── 4. 双向裁判评估 ───────────────────────────────────────────────────────
    dual_report = judge_module.evaluate_dual(
        scenario, name_A, name_B, to_judge_history(history)
    )
    judge_module.save_report(dual_report, SAVE_DIR, timestamp, scenario)
    judge_module.print_summary(dual_report)


if __name__ == "__main__":
    main()
