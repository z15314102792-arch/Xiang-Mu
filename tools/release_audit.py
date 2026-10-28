"""仅审计公开候选目录；拒绝未经检查的文件、素材和敏感内容。"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
ALLOW = {
    ".gitignore", ".gitattributes", "README.md", "start-demo.bat",
    "portfolio.py", "media_workflow.py", "media_server.py",
    "data/rules.json", "data/lock.json", "data/cases.json",
    "web/index.html", "web/workbench.html",
    "tests/test_portfolio.py", "tests/test_media_real.py",
    "tests/test_media_http.py", "tools/release_audit.py",
    "docs/PROJECT_STORY.md", "docs/PUBLISH_CHECKLIST.md",
}
BLOCK_PATTERNS = [
    ("windows absolute path", re.compile(r"\b[A-Za-z]:\\(?:Users|项目|素材|第二大脑|Program Files|\\)", re.I)),
    ("personal email address", re.compile(r"(?<![A-Z0-9._%+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)),
    ("github secret", re.compile(r"gh[pousr]_[A-Za-z0-9_]{15,}|github_pat_[A-Za-z0-9_]{20,}")),
    ("openai style secret", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("pem private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("cloud access key", re.compile(r"AKIA[0-9A-Z]{16}")),
]
errors = []
found = []

for path in ROOT.rglob("*"):
    if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
        continue
    relative = path.relative_to(ROOT).as_posix()
    if relative not in ALLOW:
        errors.append(f"unreviewed file: {relative}")
        continue
    if path.is_symlink():
        errors.append(f"symlink: {relative}")
        continue
    if path.stat().st_size > 750_000:
        errors.append(f"oversized file: {relative}")
        continue
    found.append(relative)
    if relative == "tools/release_audit.py":
        # The scanner necessarily contains the secret/path patterns as literal strings.
        continue
    text = path.read_text(encoding="utf-8")
    for label, regex in BLOCK_PATTERNS:
        if regex.search(text):
            errors.append(f"{label}: {relative}")

for item in sorted(ALLOW - set(found)):
    errors.append(f"missing required file: {item}")

print("PREPUBLISH_FILES", len(found))
for file in sorted(found):
    print(" CHECK", file)
if errors:
    for error in errors:
        print("BLOCK", error)
    print("PUBLICATION_AUDIT BLOCKED")
    sys.exit(1)
print("PUBLICATION_AUDIT PASS (静态预检查，不保证不存在隐蔽泄露)")
