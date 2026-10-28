"""实际媒体工作流：导入、静音分析、可选本地 Whisper、人工复核、剪辑导出。

依赖：FFmpeg/FFprobe；Whisper 可选且只使用已缓存模型，禁止自动下载。
所有输入和产物均留在本机独立工作目录，不进入 Git 仓库。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

BASE = Path(os.environ.get("XIANG_MU_WORKSPACE", str(Path.home() / "Videos" / "XiangMu-workspace"))).resolve()
MAX_UPLOAD_BYTES = 1_500_000_000
MAX_DURATION = 2 * 60 * 60
MAX_SEGMENTS = 160
MUTEX = threading.RLock()


def workspace():
    BASE.mkdir(parents=True, exist_ok=True)
    return BASE


def job_dir(job_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise ValueError("非法项目 ID")
    path = workspace() / job_id
    if not path.is_dir():
        raise FileNotFoundError("项目不存在")
    return path


def meta_path(job_id: str):
    return job_dir(job_id) / "project.json"


def read_job(job_id: str) -> dict:
    with MUTEX:
        return json.loads(meta_path(job_id).read_text(encoding="utf-8"))


def write_job(job_id: str, updates: dict) -> dict:
    with MUTEX:
        current = read_job(job_id)
        current.update(updates)
        target = meta_path(job_id)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
        return current


def tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"缺少 {name}。请先安装 FFmpeg 并加入 PATH。")
    return path


def run(args: list[str], timeout=300) -> subprocess.CompletedProcess:
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{Path(args[0]).name} 执行失败: {r.stderr[-850:]}")
    return r


def probe(path: Path) -> dict:
    r = run([tool("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    data = json.loads(r.stdout)
    tracks = data.get("streams") or []
    video = next((x for x in tracks if x.get("codec_type") == "video"), None)
    if not video:
        raise ValueError("文件没有有效视频轨")
    duration = float((data.get("format") or {}).get("duration") or video.get("duration") or 0)
    if not 0.1 < duration <= MAX_DURATION:
        raise ValueError("视频时长异常或超过 2 小时限制")
    return {
        "duration": round(duration, 3),
        "width": video.get("width", 0),
        "height": video.get("height", 0),
        "hasAudio": any(x.get("codec_type") == "audio" for x in tracks),
        "videoCodec": video.get("codec_name", "unknown")
    }


SIL_START = re.compile(r"silence_start:\s*([0-9.]+)")
SIL_END = re.compile(r"silence_end:\s*([0-9.]+)")


def detect_silences(path: Path, duration: float, has_audio: bool) -> list[dict]:
    if not has_audio:
        return []
    cmd = [tool("ffmpeg"), "-hide_banner", "-nostdin", "-i", str(path),
           "-map", "0:a:0", "-af", "silencedetect=noise=-38dB:d=0.35",
           "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900)
    if r.returncode != 0:
        raise RuntimeError("静音检测失败：" + r.stderr[-450:])
    current = None
    out = []
    for line in r.stderr.splitlines():
        st = SIL_START.search(line)
        en = SIL_END.search(line)
        if st:
            current = max(0, float(st.group(1)))
        if en and current is not None:
            end = min(duration, float(en.group(1)))
            if end > current:
                out.append({"start": round(current, 3), "end": round(end, 3)})
            current = None
    if current is not None and duration > current:
        out.append({"start": round(current, 3), "end": round(duration, 3)})
    return out


def speech_ranges(duration: float, silence: list[dict], pad=0.12) -> list[dict]:
    """只提供初步建议，静音并不等于口误；人工需审查头尾与重录。"""
    raw = []
    pos = 0.0
    for s in sorted(silence, key=lambda x: x["start"]):
        a, b = max(0, s["start"]), min(duration, s["end"])
        if a > pos + 0.08:
            raw.append([max(0, pos - pad), min(duration, a + pad)])
        pos = max(pos, b)
    if pos + 0.08 < duration:
        raw.append([max(0, pos - pad), duration])
    merged = []
    for start, end in raw:
        if merged and start - merged[-1][1] <= 0.04:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return [{"start": round(s, 3), "end": round(e, 3), "keep": True, "speaker": "待确认", "text": ""}
            for s, e in merged if e - s >= 0.09]


def whisper_cache(model: str) -> Path:
    if model not in {"tiny", "small"}:
        raise ValueError("只支持 tiny / small 模型")
    return Path.home() / ".cache" / "whisper" / f"{model}.pt"


def transcribe(path: Path, model: str) -> list[dict]:
    if not whisper_cache(model).is_file():
        raise RuntimeError(f"本机未缓存 Whisper {model} 模型。请选‘跳过转写’，不自动下载模型。")
    import whisper
    net = whisper.load_model(model, device="cpu")
    result = net.transcribe(str(path), language="zh", verbose=False, fp16=False,
                            condition_on_previous_text=False)
    return [{"start": round(float(x["start"]), 3), "end": round(float(x["end"]), 3),
             "text": str(x.get("text", "")).strip()} for x in result.get("segments", [])]


def attach_text(ranges: list[dict], captions: list[dict]) -> None:
    """将 Whisper 转录块分配给交叠最大的片段，避免跨片段重复字幕。"""
    for c in captions:
        if not c["text"] or not ranges:
            continue
        overlaps = [max(0., min(c["end"], x["end"]) - max(c["start"], x["start"])) for x in ranges]
        index = max(range(len(overlaps)), key=lambda i: overlaps[i])
        if overlaps[index] <= 0:
            continue
        ranges[index]["text"] = (ranges[index]["text"] + c["text"]).strip()


def create_job(filename: str, source_stream, byte_count: int, asr: str) -> dict:
    if not 0 < byte_count <= MAX_UPLOAD_BYTES:
        raise ValueError("文件过大或为空；上限为 1.5GB")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".mp4", ".mov", ".mkv", ".webm"}:
        raise ValueError("请选择 MP4/MOV/MKV/WebM 视频")
    if asr not in {"off", "tiny", "small"}:
        raise ValueError("不支持的转写模型")
    job_id = uuid.uuid4().hex
    folder = workspace() / job_id
    folder.mkdir(parents=True, exist_ok=False)
    path = folder / ("source" + suffix)
    try:
        left = byte_count
        with path.open("wb") as fp:
            while left:
                block = source_stream.read(min(left, 4 * 1024 * 1024))
                if not block:
                    raise ValueError("上传中断")
                fp.write(block)
                left -= len(block)
        meta = {"id": job_id, "name": Path(filename).name[:160], "source": path.name,
                "status": "queued", "progress": "已接收文件，等待分析",
                "asr": asr, "createdAt": time.strftime("%Y-%m-%d %H:%M:%S"),
                "segments": [], "silences": [], "report": None}
        (folder / "project.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    threading.Thread(target=analyze_job, args=(job_id,), daemon=True).start()
    return meta


def analyze_job(job_id: str) -> None:
    try:
        job = read_job(job_id)
        src = job_dir(job_id) / job["source"]
        write_job(job_id, {"status": "analyzing", "progress": "正在读取视频信息"})
        info = probe(src)
        write_job(job_id, {"info": info, "progress": "正在分析真实静音区间"})
        silences = detect_silences(src, info["duration"], info["hasAudio"])
        rows = speech_ranges(info["duration"], silences)
        if not rows:
            rows = [{"start": 0.0, "end": info["duration"], "keep": True,
                     "speaker": "待确认", "text": ""}]
        write_job(job_id, {"silences": silences, "segments": rows,
                           "progress": "停顿分析完成"})
        if job["asr"] != "off":
            if not info["hasAudio"]:
                raise RuntimeError("该视频没有音轨，无法执行语音转写")
            write_job(job_id, {"progress": "正在使用本地 Whisper 转写；CPU 上可能较慢"})
            captions = transcribe(src, job["asr"])
            attach_text(rows, captions)
            write_job(job_id, {"transcriptChunks": len(captions)})
        write_job(job_id, {"segments": rows, "status": "review",
                           "progress": "分析结束：请试听、确认说话人、编辑保留片段，再导出"})
    except Exception as exc:
        write_job(job_id, {"status": "failed", "progress": str(exc)[:850]})


def validate_segments(rows, duration: float) -> list[dict]:
    if not isinstance(rows, list) or not 0 < len(rows) <= MAX_SEGMENTS:
        raise ValueError(f"片段数应为 1–{MAX_SEGMENTS}")
    clean = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("片段格式错误")
        start = float(row["start"])
        end = float(row["end"])
        if not 0 <= start < end <= duration + 0.01 or end - start < 0.06:
            raise ValueError("片段时间超界或长度不足")
        if end > duration:
            end = duration
        if row.get("keep") is not True and row.get("keep") is not False:
            raise ValueError("keep 必须为 true 或 false")
        speaker = str(row.get("speaker", "待确认"))[:30]
        if speaker not in {"待确认", "IP", "操盘手", "其他"}:
            raise ValueError("未知说话人类别")
        clean.append({"start": round(start, 3), "end": round(end, 3),
                      "keep": row["keep"], "speaker": speaker,
                      "text": str(row.get("text", ""))[:800]})
    clean.sort(key=lambda x: (x["start"], x["end"]))
    kept = [x for x in clean if x["keep"]]
    if not kept:
        raise ValueError("至少保留一个片段")
    for x, y in zip(kept, kept[1:]):
        if y["start"] < x["end"] - 0.001:
            raise ValueError("保留片段互相重叠；请调整时间范围")
    return clean


def save_plan(job_id: str, rows) -> dict:
    job = read_job(job_id)
    if job["status"] not in {"review", "ready"}:
        raise ValueError("项目尚未分析完成或正在导出")
    clean = validate_segments(rows, job["info"]["duration"])
    return write_job(job_id, {"segments": clean, "status": "review",
                              "progress": "修改已保存，请继续试听并人工确认后导出",
                              "report": None})


def srt_time(sec: float) -> str:
    ms = max(0, int(round(sec * 1000)))
    hrs, rem = divmod(ms, 3600_000)
    mins, rem = divmod(rem, 60_000)
    secs, milli = divmod(rem, 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{milli:03d}"


def export_job(job_id: str, rows, reviewed: bool) -> dict:
    job = read_job(job_id)
    if job["status"] not in {"review", "ready"}:
        raise ValueError("请先等待分析完成")
    if reviewed is not True:
        raise ValueError("须先看听原片并确认保留段；不能把自动建议当作已验收")
    clean = validate_segments(rows, job["info"]["duration"])
    write_job(job_id, {"segments": clean, "status": "exporting",
                       "progress": "正在按人工确认的时间段生成 MP4", "report": None})
    threading.Thread(target=_render_job, args=(job_id,), daemon=True).start()
    return {"id": job_id, "status": "exporting"}


def _render_job(job_id: str) -> None:
    try:
        job = read_job(job_id)
        folder = job_dir(job_id)
        selected = [x for x in job["segments"] if x["keep"]]
        info = job["info"]
        has_audio = info["hasAudio"]
        sections, inputs = [], []
        for i, part in enumerate(selected):
            start, end = part["start"], part["end"]
            sections.append(f"[0:v:0]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{i}]")
            if has_audio:
                sections.append(f"[0:a:0]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{i}]")
                inputs.append(f"[v{i}][a{i}]")
            else:
                inputs.append(f"[v{i}]")
        sections.append("".join(inputs) + f"concat=n={len(selected)}:v=1:a={1 if has_audio else 0}" +
                        ("[vout][aout]" if has_audio else "[vout]"))
        (folder / "filters.txt").write_text(";".join(sections), encoding="utf-8")
        dst = folder / "cut_video.mp4"
        cmd = [tool("ffmpeg"), "-y", "-hide_banner", "-nostdin",
               "-i", str(folder / job["source"]), "-filter_complex_script", str(folder / "filters.txt"),
               "-map", "[vout]"]
        if has_audio:
            cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "160k"]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(dst)]
        run(cmd, timeout=3600)
        # 修正时间轴：字幕使用“剪切后的输出时间”，而非原片 start。
        srt = []
        offset = 0.0
        for part in selected:
            if part["text"].strip():
                srt.append((offset, offset + part["end"] - part["start"], part["text"].strip()))
            offset += part["end"] - part["start"]
        srt_body = "\n\n".join(
            f"{i}\n{srt_time(start)} --> {srt_time(end)}\n{content}"
            for i, (start, end, content) in enumerate(srt, 1)
        )
        (folder / "subtitles.srt").write_text(srt_body + ("\n" if srt else ""), encoding="utf-8-sig")
        result = probe(dst)
        expected = sum(p["end"] - p["start"] for p in selected)
        duration_delta = abs(result["duration"] - expected)
        report = {
            "sourceDurationSeconds": info["duration"],
            "expectedOutputSeconds": round(expected, 3),
            "actualOutputSeconds": result["duration"],
            "durationDifferenceSeconds": round(duration_delta, 3),
            "selectedSegments": len(selected),
            "removedSegments": len(job["segments"]) - len(selected),
            "subtitleLines": len(srt),
            "manualReviewConfirmedByUser": True,
            "timingCheck": "passed" if duration_delta < max(0.55, expected * 0.035) else "needs_review",
            "capabilities": ["本地视频分析", "FFmpeg 真实裁剪", "用户确认保留段", "SRT 时间重映射"],
            "limitations": ["没有自动可靠区分 IP/操盘手", "没有自动花字/BGM/音效包装",
                            "语音转写与静音建议需要人工复核", "人工确认由用户声明，系统无法代替试听审片"],
        }
        (folder / "quality_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        write_job(job_id, {"status": "ready", "progress": "实际视频与字幕已导出", "report": report})
    except Exception as exc:
        write_job(job_id, {"status": "failed", "progress": "导出失败：" + str(exc)[-900:]})


def job_asset(job_id: str, kind: str) -> Path:
    job = read_job(job_id)
    allowed = {"source": job["source"], "video": "cut_video.mp4",
               "srt": "subtitles.srt", "report": "quality_report.json"}
    if kind not in allowed:
        raise ValueError("未知文件类型")
    if kind in {"video", "srt", "report"} and job.get("status") != "ready":
        raise FileNotFoundError("当前修改尚未重新导出，禁止下载旧版本结果")
    path = job_dir(job_id) / allowed[kind]
    if not path.is_file():
        raise FileNotFoundError("文件尚未生成")
    return path
