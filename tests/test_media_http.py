"""真实本地 HTTP 交互：视频二进制上传、状态查询、复核、导出和 Range 播放。"""
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib import request, error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import media_workflow as mw
import media_server
from test_media_real import synthetic_video, wait_status


class RealHTTPTests(unittest.TestCase):
    def test_http_real_video_pipeline(self):
        with tempfile.TemporaryDirectory(prefix="xiang_mu_http_") as temp:
            folder = Path(temp)
            video = synthetic_video(folder)
            with patch.object(mw, "BASE", folder / "workspace"):
                server = media_server.ThreadingHTTPServer(("127.0.0.1", 0), media_server.Handler)
                thr = threading.Thread(target=server.serve_forever, daemon=True)
                thr.start()
                base = f"http://127.0.0.1:{server.server_address[1]}"
                try:
                    with request.urlopen(base + "/api/real/health", timeout=4) as res:
                        self.assertTrue(json.load(res)["ok"])
                    with request.urlopen(base, timeout=4) as res:
                        self.assertIn(b"REAL VIDEO PROCESSING", res.read())
                    with request.urlopen(base + "/demo", timeout=4) as res:
                        self.assertIn(b"Workflow", res.read())
                    body = video.read_bytes()
                    no_auth = request.Request(base + "/api/real/upload?name=test.mp4&asr=off",
                                              data=body, method="POST")
                    with self.assertRaises(error.HTTPError) as x:
                        request.urlopen(no_auth, timeout=4)
                    self.assertEqual(x.exception.code, 403)
                    upload = request.Request(base + "/api/real/upload?name=test.mp4&asr=off",
                                              data=body, headers={"X-Workflow-Local": "1"}, method="POST")
                    with request.urlopen(upload, timeout=15) as res:
                        job = json.load(res)
                    jid = job["id"]
                    analyzed = wait_status(jid, {"review", "failed"})
                    self.assertEqual(analyzed["status"], "review", analyzed["progress"])
                    part = [{"start": 0.7, "end": 1.7, "keep": True, "speaker": "IP", "text": "你好"},
                            {"start": 4, "end": 5, "keep": True, "speaker": "IP", "text": "谢谢"}]
                    # 视频播放必须支持 HTTP Range
                    src = request.Request(base + "/api/real/file/" + jid + "/source",
                                          headers={"Range": "bytes=0-31"})
                    with request.urlopen(src, timeout=5) as res:
                        self.assertEqual(res.status, 206)
                        self.assertEqual(len(res.read()), 32)
                    payload = json.dumps({"id": jid, "segments": part, "reviewed": True}).encode()
                    export = request.Request(base + "/api/real/export", data=payload,
                                            headers={"X-Workflow-Local": "1", "Content-Type": "application/json"},
                                            method="POST")
                    with request.urlopen(export, timeout=4) as res:
                        self.assertEqual(json.load(res)["status"], "exporting")
                    done = wait_status(jid, {"ready", "failed"})
                    self.assertEqual(done["status"], "ready", done.get("progress"))
                    with request.urlopen(base + "/api/real/file/" + jid + "/report", timeout=5) as res:
                        report = json.load(res)
                    self.assertEqual(report["selectedSegments"], 2)
                    with request.urlopen(base + "/api/real/file/" + jid + "/srt", timeout=5) as res:
                        self.assertIn("你好", res.read().decode("utf-8-sig"))
                    with request.urlopen(base + "/api/real/file/" + jid + "/video", timeout=5) as res:
                        self.assertGreater(int(res.headers["Content-Length"]), 1000)
                finally:
                    server.shutdown()
                    server.server_close()
                    thr.join(timeout=4)


if __name__ == "__main__":
    unittest.main()
