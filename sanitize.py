"""
sanitize.py — 克隆龙虾上下文脱敏处理
在 agent 文件内容传入 LLM 之前，自动检测并替换敏感信息。

脱敏格式：<TYPE> 或 <TYPE:hint>
  - 保留类型标签，让 LLM 知道"这里有一个 API key"，但不知道具体值
  - 不影响人格、科研背景、记忆等核心内容
"""

import re
from dataclasses import dataclass, field

# ── 脱敏规则 ─────────────────────────────────────────────────────────────────
# 每条规则：(pattern, replacement, description)
# replacement 可以是字符串或 callable(match) -> str

_RULES: list[tuple] = [

    # ── AI / LLM API Keys ────────────────────────────────────────────────────
    # Anthropic / OpenAI 风格
    (r'\bsk-proj-[A-Za-z0-9_\-]{20,}\b',           '<API_KEY:anthropic>',  "Anthropic project key"),
    (r'\bsk-ant-[A-Za-z0-9_\-]{20,}\b',            '<API_KEY:anthropic>',  "Anthropic key"),
    (r'\bsk-cp-[A-Za-z0-9_\-]{20,}\b',             '<API_KEY:minimax>',    "MiniMax/兼容 key"),
    (r'\bsk-[A-Za-z0-9_\-]{20,}\b',                '<API_KEY:openai-style>','OpenAI 风格 key'),

    # MiniMax / 国产平台特有前缀
    (r'\bmoltbook_sk_[A-Za-z0-9_\-]{16,}\b',       '<API_KEY:moltbook>',   "Moltbook key"),
    (r'\bmoltcn_[a-f0-9]{24,}\b',                  '<API_KEY:moltcn>',     "Moltcn key"),
    (r'\bxialiao_[a-f0-9]{24,}\b',                 '<API_KEY:xialiao>',    "虾聊 key"),

    # HuggingFace
    (r'\bhf_[A-Za-z0-9]{30,}\b',                   '<API_KEY:huggingface>','HuggingFace token'),

    # ── Git / GitHub Tokens ──────────────────────────────────────────────────
    (r'\bghp_[A-Za-z0-9]{36}\b',                   '<GITHUB_TOKEN:pat>',   "GitHub PAT"),
    (r'\bgho_[A-Za-z0-9]{36}\b',                   '<GITHUB_TOKEN:oauth>', "GitHub OAuth token"),
    (r'\bghs_[A-Za-z0-9]{36}\b',                   '<GITHUB_TOKEN:server>','GitHub server token'),
    (r'\bghr_[A-Za-z0-9]{36}\b',                   '<GITHUB_TOKEN:refresh>','GitHub refresh token'),

    # ── Discord Tokens ───────────────────────────────────────────────────────
    # Discord Bot token 特征：MTA...格式（Base64 编码 user_id）
    (r'\b[A-Za-z0-9]{24}\.[A-Za-z0-9_\-]{6}\.[A-Za-z0-9_\-]{27,38}\b',
                                                    '<DISCORD_BOT_TOKEN>',  "Discord bot token"),

    # ── 通用 key=value / key: value 格式 ────────────────────────────────────
    # 匹配含敏感词的键，替换值部分
    (
        r'(?i)((?:api[_\-]?key|secret[_\-]?key|access[_\-]?token|auth[_\-]?token'
        r'|bearer|password|passwd|pwd|private[_\-]?key|webhook[_\-]?url'
        r'|client[_\-]?secret|refresh[_\-]?token|keyring)["\s]*[:=]["\s]*)([^\s\n\r"\'`]{6,})',
        lambda m: m.group(1) + '<REDACTED>',
        "通用 key=value 敏感字段",
    ),

    # ── URL 内嵌凭证 ─────────────────────────────────────────────────────────
    (r'(?:https?|ftp)://[^:@\s/]+:[^@\s/]+@',     '<URL_WITH_CREDENTIALS>@', "URL 内嵌用户名:密码"),

    # ── OAuth URL（含 client_id / client_secret）────────────────────────────
    (r'(client_secret=)[A-Za-z0-9_\-]{8,}',        r'\1<REDACTED>',        "OAuth client_secret"),
    (r'(client_id=)[A-Za-z0-9_\-]{8,}',            r'\1<REDACTED>',        "OAuth client_id"),

    # ── Email 地址 ───────────────────────────────────────────────────────────
    (r'\b[A-Za-z0-9._%+\-]{2,}@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b',
                                                    '<EMAIL>',              "邮箱地址"),

    # ── 服务器公网 IP（排除 127.x.x.x / 192.168.x.x / 10.x.x.x 等内网）────
    (
        r'\b(?!(?:127\.|192\.168\.|10\.|172\.(?:1[6-9]|2\d|3[01])\.)\d)'
        r'(?:\d{1,3}\.){3}\d{1,3}\b',
        '<SERVER_IP>',
        "公网 IP 地址",
    ),

    # ── SSH 私钥内容 ─────────────────────────────────────────────────────────
    (r'-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+PRIVATE KEY-----',
                                                    '<SSH_PRIVATE_KEY>',    "SSH 私钥"),

    # ── 飞书 / Lark open_id ──────────────────────────────────────────────────
    (r'\bou_[a-f0-9]{30,}\b',                      '<LARK_OPEN_ID>',       "飞书 open_id"),

    # ── 长随机字符串兜底（高熵，非中文，非代码）────────────────────────────
    # 仅匹配 40 字符以上、仅含字母数字下划线的孤立 token（极可能是 secret）
    # 用负向断言避免误伤正常单词、代码变量
    (
        r'(?<![/\w\-])\b[A-Za-z0-9_]{48,}\b(?![/\w\-])',
        '<POSSIBLE_SECRET>',
        "疑似长随机 secret（兜底）",
    ),
]

# 编译正则，提高重复调用性能
_COMPILED: list[tuple] = [
    (re.compile(pattern, re.MULTILINE), replacement, desc)
    for pattern, replacement, desc in _RULES
]


# ── 脱敏结果 ─────────────────────────────────────────────────────────────────

@dataclass
class SanitizeResult:
    text: str                          # 脱敏后的文本
    redacted: list[dict] = field(default_factory=list)  # 每条脱敏记录

    @property
    def count(self) -> int:
        return sum(r["count"] for r in self.redacted)

    def summary(self) -> str:
        if not self.redacted:
            return "  ✅ 未发现敏感信息"
        lines = [f"  🔒 共脱敏 {self.count} 处："]
        for r in self.redacted:
            lines.append(f"     [{r['count']}x] {r['description']}")
        return "\n".join(lines)


# ── 核心脱敏函数 ─────────────────────────────────────────────────────────────

def sanitize(text: str) -> SanitizeResult:
    """
    对输入文本执行全量脱敏，返回 SanitizeResult。
    规则按顺序执行，前面的规则匹配后不会再被后面的规则二次替换。
    """
    result_text = text
    redacted_log: list[dict] = []

    for pattern, replacement, desc in _COMPILED:
        if callable(replacement):
            new_text, n = pattern.subn(replacement, result_text)
        else:
            new_text, n = pattern.subn(replacement, result_text)

        if n > 0:
            redacted_log.append({"description": desc, "count": n})
            result_text = new_text

    return SanitizeResult(text=result_text, redacted=redacted_log)


def sanitize_context(name: str, raw_context: str) -> str:
    """
    加载上下文后调用，打印脱敏报告并返回干净文本。
    agent_chat.py 里直接用这个函数替换 raw context。
    """
    result = sanitize(raw_context)
    if result.count > 0:
        print(f"  🔒 {name} 上下文脱敏完成 — {result.count} 处敏感信息已替换")
        for r in result.redacted:
            print(f"     [{r['count']}x] {r['description']}")
    else:
        print(f"  ✅ {name} 上下文无敏感信息")
    return result.text


# ── CLI 独立检测模式 ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("用法: python3 sanitize.py <file_path> [--dry-run]")
        sys.exit(1)

    filepath = Path(sys.argv[1])
    dry_run  = "--dry-run" in sys.argv

    if not filepath.exists():
        print(f"❌ 文件不存在: {filepath}")
        sys.exit(1)

    raw  = filepath.read_text(encoding="utf-8")
    res  = sanitize(raw)

    print(f"\n📄 文件: {filepath}")
    print(res.summary())

    if not dry_run and res.count > 0:
        out_path = filepath.with_suffix(".sanitized" + filepath.suffix)
        out_path.write_text(res.text, encoding="utf-8")
        print(f"\n  💾 脱敏版本已保存: {out_path}")
    elif dry_run:
        print("\n[dry-run 模式，不写入文件]")
        if res.count > 0:
            print("\n── 脱敏后预览（前50行）──")
            for line in res.text.splitlines()[:50]:
                print(line)
