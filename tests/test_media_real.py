"""实际视频自动化验收：真实生成、分析、人工剪切、SRT 和输出核验。"""
import io
import json
import math
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import media_workflow as mw


def wait_status(jid, states, timeout=70):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        j = mw.read_job(jid)
        if j["status"] in states:
            return j
        time.sleep(0.2)
    raise TimeoutError(f"工作流超时，最后状态：{mw.read_job(jid)}")


def synthetic_video(folder: Path) -> Path:
    wavfile = folder / "synthetic.wav"
    rate, dur = 16000, 6
    with wave.open(str(wavfile), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        samples = bytearray()
        for i in range(dur * rate):
            sec = i / rate
            value = 0.32 * math.sin(2 * math.pi * 440 * sec) if (0.5 <= sec < 2.1 or 3.7 <= sec < 5.6) else 0
            samples.extend(struct.pack("<h", int(value * 32767)))
        f.writeframes(bytes(samples))
    output = folder / "synthetic.mp4"
    subprocess.run([mw.tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=black:s=320x568:r=25:d=6",
                    "-i", str(wavfile), "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(output)],
                   check=True, timeout=45)
    return output


class RealMediaTests(unittest.TestCase):
    def test_srt_time_remap(self):
        self.assertEqual(mw.srt_time(0), "00:00:00,000")
        self.assertEqual(mw.srt_time(61.23), "00:01:01,230")

    def test_invalid_edit_rejected(self):
        with self.assertRaises(ValueError):
            mw.validate_segments([{"start": 1, "end": 2, "keep": True, "speaker": "IP", "text": "A"},
                                  {"start": 1.5, "end": 3, "keep": True, "speaker": "IP", "text": "B"}], 5)
        with self.assertRaises(ValueError):
            mw.validate_segments([{"start": 0, "end": 1, "keep": True, "speaker": "模型自动识别IP", "text": "X"}], 5)
        with self.assertRaises(ValueError):
            mw.validate_segments([{"start": 0, "end": 1, "keep": False, "speaker": "IP", "text": "X"}], 5)

    def test_actual_video_analysis_export(self):
        with tempfile.TemporaryDirectory(prefix="xiang_mu_media_test_") as temp:
            folder = Path(temp)
            video = synthetic_video(folder)
            with patch.object(mw, "BASE", folder / "workspace"):
                info = mw.probe(video)
                self.assertTrue(info["hasAudio"])
                self.assertGreater(info["duration"], 5.5)
                silences = mw.detect_silences(video, info["duration"], True)
                self.assertGreaterEqual(len(silences), 2)
                self.assertGreaterEqual(len(mw.speech_ranges(info["duration"], silences)), 2)
                with video.open("rb") as f:
                    start = mw.create_job("test.mp4", f, video.stat().st_size, "off")
                jid = start["id"]
                j = wait_status(jid, {"review", "failed"})
                self.assertEqual(j["status"], "review", str(j.get("progress")))
                self.assertGreaterEqual(len(j["segments"]), 2)
                # 用户人工确定片段范围；此处为程序构造的验证数据。
                rows = [{"start": 0.55, "end": 1.5, "keep": True, "speaker": "IP", "text": "第一句话"},
                        {"start": 3.85, "end": 4.9, "keep": True, "speaker": "IP", "text": "第二句话"}]
                mw.save_plan(jid, rows)
                with self.assertRaises(ValueError):
                    mw.export_job(jid, rows, reviewed=False)
                mw.export_job(jid, rows, reviewed=True)
                done = wait_status(jid, {"ready", "failed"})
                self.assertEqual(done["status"], "ready", str(done.get("progress")))
                self.assertEqual(done["report"]["selectedSegments"], 2)
                self.assertEqual(done["report"]["subtitleLines"], 2)
                self.assertEqual(done["report"]["timingCheck"], "passed")
                result = mw.probe(mw.job_asset(jid, "video"))
                self.assertTrue(result["hasAudio"])
                self.assertLess(result["duration"], 2.3)
                self.assertGreater(result["duration"], 1.75)
                captions = mw.job_asset(jid, "srt").read_text(encoding="utf-8-sig")
                self.assertIn("第一句话", captions)
                self.assertIn("第二句话", captions)
                self.assertIn("00:00:00,000 --> 00:00:00,950", captions)
                self.assertIn("00:00:00,950 --> 00:00:02,000", captions)
                report = json.loads(mw.job_asset(jid, "report").read_text(encoding="utf-8"))
                self.assertTrue(report["manualReviewConfirmedByUser"])
                self.assertIn("没有自动可靠区分 IP/操盘手", report["limitations"])


if __name__ == "__main__":
    unittest.main()
