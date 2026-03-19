# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Clone Lobster A2A** (克隆龙虾 A2A) — Distributed two-Agent dialogue framework using the Agent-to-Agent protocol. Two Agents run as independent FastAPI HTTP services on separate devices. A neutral matchmaker orchestrates service discovery, perspective correction, phased conversation, and judge evaluation.

Evolved from the single-machine version at `/home/ubuntu/projects/Agent-First/`. Modules `scenarios.py`, `judge.py`, and `sanitize.py` are shared logic carried over from that project.

## Running the System

```bash
# Install dependencies
pip install -r requirements.txt

# 1. Start Agent A (supervisor/导师, port 8001)
python3 agents/supervisor_agent.py --name "Leo" --port 8001

# 2. Start Agent B (applicant/申请者, port 8002)
python3 agents/applicant_agent.py --name "ddd" --port 8002

# 3. Start matchmaker (orchestrator)
python3 matchmaker.py --agent-a http://localhost:8001 --agent-b http://localhost:8002

# With a specific scenario (default: academic_interview)
python3 matchmaker.py -A http://localhost:8001 -B http://localhost:8002 --scenario dating

# Run sanitize standalone check
python3 sanitize.py <file_path> [--dry-run]
```

Legacy CLI flags `--supervisor`/`--applicant` are aliases for `--agent-a`/`--agent-b`.

## Architecture

```
Agent A (FastAPI :8001)          Agent B (FastAPI :8002)
  BaseA2AAgent                     BaseA2AAgent
  reads local SOUL/USER/MEMORY     reads local SOUL/USER/MEMORY
        │                                │
        └────────── matchmaker ──────────┘
                   (orchestrator)
                   service discovery → phased dialogue → dual judge
```

**Data flow per turn:** matchmaker calls `to_perspective(history, recipient)` to convert shared history into `user`/`assistant` roles for the recipient, then POSTs to `/tasks/send`. The Agent does NOT do any perspective logic — it transparently forwards messages to the LLM.

**Key design decision:** Perspective correction is centralized in `matchmaker.py`, not in the agents. Early versions had agents doing perspective conversion, which caused bugs. Agents receive pre-corrected `user`/`assistant` messages and pass them directly to the LLM.

## A2A Protocol Endpoints (per Agent)

| Endpoint | Method | Purpose |
|---|---|---|
| `/.well-known/agent.json` | GET | Service discovery card |
| `/tasks/send` | POST | Receive task, return Agent reply |
| `/health` | GET | Health check |

## Core Mechanisms

**Perspective correction** (`matchmaker.py:to_perspective`): Converts shared history (keyed by `speaker`) into recipient's view where own messages become `assistant` and the other party's become `user`.

**Phase triggers** (`metadata.trigger`): Stage transitions are injected via metadata, not added to conversation history. `base_agent.py:_build_llm_messages` handles three cases: (1) empty history → use trigger, (2) new phase → append trigger, (3) last message is assistant → append "请继续".

**Context loading** (`base_agent.py`): Each Agent reads local OpenClaw files (`~/.openclaw/workspace/{SOUL,USER,MEMORY}.md`), sanitizes them via `sanitize()`, and builds a system prompt with role instructions from the scenario. Custom paths via `--soul`, `--user`, `--memory` CLI args.

**Dual judge evaluation** (`judge.py:evaluate_dual`): After conversation ends, two judge LLM calls run serially — role_A evaluates role_B and vice versa. Reports are saved as both JSON and Markdown in `output/`.

**Sync LLM calls**: `base_agent.py` uses synchronous `anthropic.Anthropic.messages.create()`. FastAPI automatically runs sync route handlers in a thread pool, so this doesn't block the event loop.

## Scenarios

Defined in `scenarios.py` as a `SCENARIOS` dict. Three scenarios exist: `academic_interview`, `dating`, `job_matching`. Each scenario defines:
- `role_A`/`role_B` keys and labels
- `phases` with round counts and trigger prompts
- `system_prompts` per role
- Dual judge criteria (`judge_criteria_a`, `judge_criteria_b`) and verdict thresholds

## LLM Provider

Uses MiniMax via Anthropic-compatible API (`https://api.minimaxi.com/anthropic`, model `MiniMax-M2.5`). API key is currently hardcoded in `base_agent.py` and `judge.py` — should be migrated to environment variables.

## Internal History Format

Matchmaker's `history` entries contain: `speaker` (role key), `name`, `role_label`, `content`, `phase`, `round`. The `to_judge_history()` function maps `name` → `speaker` for judge consumption.

## Known Issues

- API key hardcoded in `base_agent.py` and `judge.py`
- Agents bind to `0.0.0.0` with no auth (A2A protocol supports Bearer token)
- `well-known/agent_template.json` URL field needs manual update for cross-machine deployment
- No reconnection mechanism; matchmaker HTTP timeout is 60s
