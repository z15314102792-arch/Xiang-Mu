"""可移植口播 AI 工作流质检作品集：规则模拟、回归与本地演示。

注意：此项目不执行音视频编辑，不替代实际声画审片。
规则取自既有项目的已确认要求，测试数据为脱敏/模拟案例。
"""
from __future__ import annotations

import argparse
import hashlib
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
GATES = ("structure", "take", "semantic", "flower", "sfx", "audio", "technical")
GATE_LABELS = {
    "structure": "结构", "take": "声画 take", "semantic": "语义",
    "flower": "花字", "sfx": "音效", "audio": "混音", "technical": "技术"
}


def read_json(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def audit_rules() -> dict:
    """阻止未更新锁定清单的规则内容被悄悄替换。"""
    rules_path = DATA / "rules.json"
    lock_path = DATA / "lock.json"
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        rules = json.loads(rules_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"status": "blocked", "reason": "规则或锁定清单不可读取", "details": str(exc)}
    digest = hashlib.sha256(rules_path.read_bytes()).hexdigest()
    expected = lock.get("rulesSha256")
    ids = [rule.get("id") for rule in rules] if isinstance(rules, list) else []
    unique = len(ids) == len(set(ids)) and all(isinstance(i, str) for i in ids)
    locked = bool(ids) and all(rule.get("status") == "locked" for rule in rules)
    ok = digest == expected and unique and locked
    return {
        "status": "passed" if ok else "blocked",
        "ruleCount": len(ids),
        "hashMatched": digest == expected,
        "uniqueIds": unique,
        "allLocked": locked,
        "expectedSha256": expected,
        "actualSha256": digest,
        "reason": "规则文件未发生未授权变化" if ok else "规则文件漂移、重复 ID 或状态异常"
    }


def evaluate_case(case: dict) -> dict:
    """对结构化剪辑计划作机械检查。返回阻断原因，不假装分析真实视频。"""
    problems: list[dict] = []

    def fail(rule_id: str, stage: str, message: str, action: str):
        problems.append({
            "ruleId": rule_id, "stage": stage,
            "message": message, "suggestion": action
        })

    if not isinstance(case, dict):
        case = {}
    inp = case.get("input")
    if not isinstance(inp, dict):
        inp = {}
        fail("INPUT-001", "输入", "缺少结构化输入 input", "提供完整 JSON 测试对象")
    audit = audit_rules()
    if audit["status"] != "passed":
        fail("RULE-LOCK", "规则治理", "规则锁定校验不通过", "核对规则 SHA-256 和锁定清单")

    take = inp.get("take")
    if not isinstance(take, dict) or take.get("audioReviewed") is not True or take.get("videoReviewed") is not True:
        fail("ROUGH-001", "粗剪", "保留片段没有声画双重复核证据", "同时提供真实音频与视频 take 复核证据")

    subtitles = inp.get("subtitles")
    if not isinstance(subtitles, list) or not subtitles:
        fail("SUB-002", "字幕", "缺少字幕评估数据", "提供字幕片段及持续时间")
    else:
        for i, sub in enumerate(subtitles):
            if not isinstance(sub, dict):
                fail("SUB-002", "字幕", f"第{i+1}条字幕结构非法", "提供完整字幕对象")
                continue
            duration = sub.get("duration")
            if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
                fail("SUB-002", "字幕", f"第{i+1}条字幕时长缺失或非法", "核对实际时长")
            elif sub.get("placeholder") is True and duration > 8:
                fail("SUB-002", "字幕", f"第{i+1}条字幕占位 {duration:g}s，超过演示门槛", "只在必要的局部处理，恢复语义连续性")

    flowers = inp.get("flowers")
    if not isinstance(flowers, list):
        fail("FLOWER-001", "花字", "缺少花字计划列表", "无花字可使用空列表 []")
    else:
        for i, flower in enumerate(flowers):
            if not isinstance(flower, dict):
                fail("FLOWER-001", "花字", f"第{i+1}条花字结构非法", "提供有效花字对象")
                continue
            label = f"第{i+1}条花字"
            if flower.get("intent") not in ("core_point", "summary"):
                fail("FLOWER-001", "花字", label + "不是核心观点或有价值总结", "标记 omit，禁止按数量凑花字")
            if flower.get("durationMode") != "word_alignment":
                fail("FLOWER-003", "花字", label + "未绑定词级起止", "按真实语音起止重建时长")
            timing = [flower.get(k) for k in ("start", "end", "wordStart", "wordEnd")]
            if any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in timing):
                fail("FLOWER-003", "花字", label + "缺少数字型语音对齐时间", "补齐 wordStart / wordEnd 与 start / end")
            else:
                st, en, wst, wen = timing
                if st >= en or wst >= wen or abs(st - wst) > 0.12 or abs(en - wen) > 0.12:
                    fail("FLOWER-003", "花字", label + "和词级语音不一致", "按实际词级时间重新对齐（演示容差0.12秒）")
            if flower.get("fitsSafeArea") is not True or flower.get("animationLoop") is not False:
                fail("FLOWER-005", "花字", label + "存在裁切或循环动画风险", "重算文字包围盒并取消循环动画")

    sfx = inp.get("sfx")
    if not isinstance(sfx, list):
        fail("SFX-001", "音效", "缺少音效计划列表", "无音效可使用空列表 []")
    else:
        for i, event in enumerate(sfx):
            if not isinstance(event, dict) or event.get("trigger") not in ("semantic", "emphasis", "action"):
                fail("SFX-001", "音效", f"第{i+1}条音效不是独立语义触发", "改为按实际语义/动作/重音决定是否使用")

    bgm = inp.get("bgm")
    if not isinstance(bgm, dict) or bgm.get("sourceType") != "instrumental" or bgm.get("voiceClear") is not True:
        fail("BGM-001", "音效", "BGM 来源或人声避让未通过", "改用纯配乐并复核说话清晰度")

    reports = inp.get("reports")
    if not isinstance(reports, dict):
        reports = {}
    for gate in GATES:
        if reports.get(gate) != "passed":
            fail("WORKFLOW-001", "质检", f"缺少通过的{GATE_LABELS[gate]}检查报告", "补齐真实报告；任一门槛阻断时不得交付")

    outcome = "blocked" if problems else "review_required"
    return {
        "caseId": str(case.get("id", "CUSTOM"))[:80],
        "title": str(case.get("title", "自定义案例"))[:120],
        "status": outcome,
        "statusLabel": "机械检查阻断" if problems else "机械检查通过 · 待人工审片",
        "failCount": len(problems),
        "findings": problems,
        "ruleAudit": audit,
        "manualReview": inp.get("humanReview", "pending"),
        "limitations": "仅检查输入的结构化声明，不验证视频内容或音质；必须人工听看成片。",
    }


def all_cases():
    return read_json("cases.json")


class Handler(BaseHTTPRequestHandler):
    def respond_json(self, value, status=HTTPStatus.OK):
        raw = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            raw = (ROOT / "web" / "index.html").read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        elif url.path == "/api/cases":
            self.respond_json([{
                "id": x["id"], "title": x["title"], "story": x["story"], "expected": x["expected"], "input": x["input"],
                "result": evaluate_case(x)
            } for x in all_cases()])
        elif url.path == "/api/rules":
            self.respond_json({"audit": audit_rules(), "rules": read_json("rules.json")})
        elif url.path == "/api/health":
            self.respond_json({"ok": audit_rules()["status"] == "passed", "caseCount": len(all_cases()), "mode": "structured-demo-only"})
        else:
            self.respond_json({"error": "route not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self):
        if urlparse(self.path).path != "/api/evaluate":
            return self.respond_json({"error": "route not found"}, HTTPStatus.NOT_FOUND)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size < 131072:
                return self.respond_json({"error": "payload size invalid"}, HTTPStatus.BAD_REQUEST)
            case = json.loads(self.rfile.read(size).decode("utf-8"))
            if not isinstance(case, dict):
                return self.respond_json({"error": "object required"}, HTTPStatus.BAD_REQUEST)
            self.respond_json(evaluate_case(case))
        except (UnicodeError, ValueError) as exc:
            self.respond_json({"error": str(exc)[:160]}, HTTPStatus.BAD_REQUEST)

    def log_message(self, *_):
        return


def demo() -> int:
    rows = []
    for case in all_cases():
        result = evaluate_case(case)
        actual = result["status"]
        correct = actual == case["expected"]
        rows.append((case["id"], correct, actual, result["failCount"]))
    for cid, correct, status, fail_count in rows:
        print(("PASS" if correct else "FAIL"), cid, status, f"findings={fail_count}")
    print("REGRESSION", sum(x[1] for x in rows), "/", len(rows))
    print("RULE_AUDIT", audit_rules()["status"])
    return 0 if all(x[1] for x in rows) and audit_rules()["status"] == "passed" else 1


def main():
    ap = argparse.ArgumentParser(description="口播剪辑工作流质检作品集（结构化数据演示）")
    ap.add_argument("command", choices=("demo", "audit", "serve"))
    ap.add_argument("--port", type=int, default=8989)
    ap.add_argument("--open", action="store_true", help="在默认浏览器中打开工作台")
    args = ap.parse_args()
    if args.command == "demo":
        return demo()
    if args.command == "audit":
        result = audit_rules()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "passed" else 1
    if not 1024 <= args.port <= 65535:
        ap.error("port must be 1024..65535")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"打开 http://127.0.0.1:{args.port} （Ctrl+C 退出）", flush=True)
    if args.open:
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
