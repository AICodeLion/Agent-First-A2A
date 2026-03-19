"""
agents/supervisor_agent.py — 导师用户在自己设备上运行这个脚本
直接读取本机 SOUL/USER/MEMORY，启动 A2A HTTP 服务
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base_agent import BaseA2AAgent, DEFAULT_SOUL, DEFAULT_USER, DEFAULT_MEMORY
from scenarios import get_scenario


def main():
    parser = argparse.ArgumentParser(
        description="导师 Agent — 在自己设备上启动，等待 matchmaker 连接",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用 OpenClaw 默认路径
  python3 agents/supervisor_agent.py --name "Leo"

  # 指定文件路径
  python3 agents/supervisor_agent.py --name "Leo" \\
    --soul  /path/to/SOUL.md \\
    --user  /path/to/USER.md \\
    --memory /path/to/MEMORY.md
        """,
    )
    parser.add_argument("--name",     "-n", required=True,
                        help="你的名字（显示在 Agent Card 和对话中）")
    parser.add_argument("--soul",     type=Path, default=DEFAULT_SOUL,
                        help=f"SOUL.md 路径（默认 {DEFAULT_SOUL}）")
    parser.add_argument("--user",     type=Path, default=DEFAULT_USER,
                        help=f"USER.md 路径（默认 {DEFAULT_USER}）")
    parser.add_argument("--memory",   type=Path, default=DEFAULT_MEMORY,
                        help=f"MEMORY.md 路径（默认 {DEFAULT_MEMORY}）")
    parser.add_argument("--port",     type=int, default=8001,
                        help="监听端口（默认 8001）")
    parser.add_argument("--scenario", type=str, default="academic_interview",
                        help="场景名称（默认 academic_interview）")
    args = parser.parse_args()

    scenario = get_scenario(args.scenario)
    agent    = BaseA2AAgent(
        name        = args.name,
        role_key    = scenario["role_A"],   # 通用：从场景配置读，不再硬编码
        scenario    = scenario,
        soul_path   = args.soul,
        user_path   = args.user,
        memory_path = args.memory,
        port        = args.port,
    )
    agent.run()


if __name__ == "__main__":
    main()
