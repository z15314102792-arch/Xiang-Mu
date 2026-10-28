"""真实字幕/花字动画/开头缓推/BGM/SFX 的视频渲染回归测试。"""
import io
import math
import struct
import sys
import tempfile
import wave
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import media_workflow as mw
from test_media_real import synthetic_video, wait_status
from package_render import validate

def wav_tone(path: Path, duration, freq):
    rate=16000
    with wave.open(str(path),"wb") as writer:
        writer.setnchannels(1);writer.setsampwidth(2);writer.setframerate(rate)
        writer.writeframes(b"".join(struct.pack("<h",int(7800*math.sin(2*math.pi*freq*i/rate)))
                                    for i in range(int(duration*rate))))

class PackagingTests(unittest.TestCase):
    def test_invalid_animated_title_is_rejected(self):
        with self.assertRaises(ValueError):
            validate({"flowers":[{"text":"换行\n不允许","start":1,"end":2}]})
        with self.assertRaises(ValueError):
            validate({"flowers":[{"text":"正常","start":2,"end":2,"animation":"pop"}]})
        with self.assertRaises(ValueError):
            validate({"subtitleColor":"custom arbitrary filter string"})
        self.assertEqual(validate({})["subtitleEnabled"],True)

    def test_real_animated_render_bgm_sfx(self):
        with tempfile.TemporaryDirectory(prefix="xiangmu_packaging_") as td:
            base=Path(td);source=synthetic_video(base)
            bgm=base/"tone_bgm.wav";sfx=base/"tone_sfx.wav"
            wav_tone(bgm,1.3,280);wav_tone(sfx,.3,880)
            with patch.object(mw,"BASE",base/"work"):
                with source.open("rb") as f:
                    j=mw.create_job("source.mp4",f,source.stat().st_size,"off")
                jid=j["id"]
                self.assertEqual(wait_status(jid,{"review","failed"})["status"],"review")
                rows=[{"start":.55,"end":1.9,"keep":True,"speaker":"IP","text":"实际字幕测试"},
                      {"start":3.9,"end":5.1,"keep":True,"speaker":"IP","text":"第二行文字"}]
                with bgm.open("rb") as f:
                    mw.upload_audio(jid,"bgm","music.wav",f,bgm.stat().st_size)
                with sfx.open("rb") as f:
                    mw.upload_audio(jid,"sfx","effect.wav",f,sfx.stat().st_size)
                conf={"subtitleEnabled":True,"subtitleAnimation":"pop","openingZoom":True,
                      "bgmEnabled":True,"bgmVolume":.09,"sfxEnabled":True,
                      "sfxTime":.5,"sfxVolume":.13,
                      "flowers":[{"text":"真实花字动画","start":.3,"end":1.5,
                                  "animation":"rise","color":"#FFD85C","position":"upper"}]}
                mw.save_packaging(jid,conf)
                mw.export_job(jid,rows,True)
                done=wait_status(jid,{"ready","failed"},timeout=100)
                self.assertEqual(done["status"],"ready",done["progress"])
                pack=done["report"]["packaging"]
                self.assertTrue(pack["applied"])
                self.assertEqual(pack["burnedSubtitleLines"],2)
                self.assertEqual(pack["animatedFlowers"],1)
                self.assertTrue(pack["openingZoom"])
                self.assertTrue(pack["bgmMixed"])
                self.assertTrue(pack["sfxMixed"])
                rendered=mw.job_asset(jid,"video")
                probe=mw.probe(rendered)
                self.assertTrue(probe["hasAudio"])
                self.assertLess(abs(probe["duration"]-2.55),.35)
                # 文件真实有非黑色笔画（测试底片为纯黑），不是只写了配置。
                import subprocess
                frm=subprocess.run([mw.tool("ffmpeg"),"-v","error","-ss","0.7","-i",str(rendered),
                                    "-frames:v","1","-threads:v","1","-f","rawvideo","-pix_fmt","rgb24","pipe:1"],
                                   capture_output=True,timeout=30)
                self.assertEqual(frm.returncode,0,frm.stderr.decode("utf-8","replace")[-700:])
                colored=sum(1 for v in frm.stdout if v>60)
                self.assertGreater(colored,400,"最终画面未检测到真实烧录的字幕/花字像素")
                self.assertTrue((mw.job_dir(jid)/"packaging.ass").is_file())
                self.assertTrue((mw.job_dir(jid)/"package_filters.txt").is_file())

if __name__=="__main__":
    unittest.main()
