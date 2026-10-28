"""作品集可移植性、质量门槛和本地 HTTP 接口测试。"""
import json
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib import request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import portfolio


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = portfolio.all_cases()

    def test_every_regression_case_matches_expected(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(portfolio.evaluate_case(case)["status"], case["expected"])

    def test_good_case_requires_human_review(self):
        result = portfolio.evaluate_case(self.cases[0])
        self.assertEqual(result["status"], "review_required")
        self.assertEqual(result["manualReview"], "pending")
        self.assertEqual(result["failCount"], 0)

    def test_asr_only_is_blocked(self):
        case = next(c for c in self.cases if c["id"] == "BC-TAKE-009")
        self.assertIn("ROUGH-001", [x["ruleId"] for x in portfolio.evaluate_case(case)["findings"]])

    def test_flower_quota_is_blocked(self):
        case = next(c for c in self.cases if c["id"] == "BC-FLOWER-006")
        self.assertIn("FLOWER-001", [x["ruleId"] for x in portfolio.evaluate_case(case)["findings"]])

    def test_flower_timing_is_blocked(self):
        case = next(c for c in self.cases if c["id"] == "BC-FLOWER-007")
        self.assertIn("FLOWER-003", [x["ruleId"] for x in portfolio.evaluate_case(case)["findings"]])

    def test_sound_effect_linked_to_flower_is_blocked(self):
        case = next(c for c in self.cases if c["id"] == "BC-SFX-008")
        self.assertIn("SFX-001", [x["ruleId"] for x in portfolio.evaluate_case(case)["findings"]])

    def test_missing_technical_report_is_blocked(self):
        case = next(c for c in self.cases if c["id"] == "DEMO-WORKFLOW-001")
        self.assertIn("WORKFLOW-001", [x["ruleId"] for x in portfolio.evaluate_case(case)["findings"]])

    def test_missing_input_fails_closed(self):
        result = portfolio.evaluate_case({"id": "empty"})
        self.assertEqual(result["status"], "blocked")
        self.assertGreater(result["failCount"], 0)

    def test_no_flower_or_sfx_can_be_valid(self):
        case = json.loads(json.dumps(self.cases[0]))
        case["input"]["flowers"] = []
        case["input"]["sfx"] = []
        self.assertEqual(portfolio.evaluate_case(case)["status"], "review_required")

    def test_rule_lock_manifest_is_valid(self):
        self.assertEqual(portfolio.audit_rules()["status"], "passed")

    def test_rule_hash_drift_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            shutil.copyfile(portfolio.DATA / "rules.json", folder / "rules.json")
            shutil.copyfile(portfolio.DATA / "lock.json", folder / "lock.json")
            with patch.object(portfolio, "DATA", folder):
                self.assertEqual(portfolio.audit_rules()["status"], "passed")
                with (folder / "rules.json").open("a", encoding="utf-8") as fp:
                    fp.write(" ")
                self.assertEqual(portfolio.audit_rules()["status"], "blocked")

    def test_http_api_runs_locally(self):
        server = portfolio.ThreadingHTTPServer(("127.0.0.1", 0), portfolio.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with request.urlopen(base + "/api/health", timeout=3) as response:
                health = json.load(response)
            self.assertTrue(health["ok"])
            self.assertEqual(health["caseCount"], len(self.cases))
            body = json.dumps(self.cases[0], ensure_ascii=False).encode("utf-8")
            req = request.Request(base + "/api/evaluate", data=body,
                                  headers={"Content-Type": "application/json"}, method="POST")
            with request.urlopen(req, timeout=3) as response:
                answer = json.load(response)
            self.assertEqual(answer["status"], "review_required")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
