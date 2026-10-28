"""真实成片包装：ASS 硬字幕/花字动画、开场缓推、BGM/SFX 混音。
仅使用用户上传音效；所有滤镜在本地 ffmpeg 中执行。
"""
from __future__ import annotations
import json
import math
import re
import subprocess
from pathlib import Path

DEFAULT = {
    "subtitleEnabled": True, "subtitleSize": 46, "subtitleBottom": 13,
    "subtitleColor": "#FFFFFF", "subtitleAnimation": "fade",
    "openingZoom": False, "flowers": [],
    "bgmEnabled": False, "bgmVolume": 0.12,
    "sfxEnabled": False, "sfxTime": 0.6, "sfxVolume": 0.14
}
COLORS = {"#FFFFFF", "#FFD85C", "#7CE8CE", "#FF9FAF", "#9ED4FF"}


def validate(data: dict | None) -> dict:
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("包装参数必须是对象")
    out = dict(DEFAULT)
    out.update({k: v for k, v in data.items() if k in DEFAULT})
    for k in ("subtitleEnabled", "openingZoom", "bgmEnabled", "sfxEnabled"):
        if type(out[k]) is not bool:
            raise ValueError(f"{k} 只能开或关")
    out["subtitleSize"] = integer(out["subtitleSize"], "字幕字号", 18, 90)
    out["subtitleBottom"] = integer(out["subtitleBottom"], "字幕底边", 4, 40)
    for k in ("bgmVolume", "sfxVolume"):
        v = num(out[k], k, 0, 0.8)
        out[k] = round(v, 3)
    out["sfxTime"] = round(num(out["sfxTime"], "音效触发秒数", 0, 7200), 3)
    if out["subtitleColor"] not in COLORS:
        raise ValueError("不支持的字幕颜色")
    if out["subtitleAnimation"] not in {"none", "fade", "pop"}:
        raise ValueError("不支持的字幕动画")
    flowers = out["flowers"]
    if not isinstance(flowers, list) or len(flowers) > 30:
        raise ValueError("花字数量限制 0–30")
    clean = []
    for index, raw in enumerate(flowers):
        if not isinstance(raw, dict):
            raise ValueError("花字必须是对象")
        txt = str(raw.get("text", "")).strip()
        if not txt or len(txt) > 24 or any(c in txt for c in "\r\n"):
            raise ValueError(f"第 {index+1} 条花字应为 1–24 字、单行")
        start = round(num(raw.get("start"), "花字起点", 0, 7200), 3)
        end = round(num(raw.get("end"), "花字终点", 0, 7200), 3)
        if end - start < .15:
            raise ValueError("花字持续时间至少 0.15 秒")
        animation = raw.get("animation", "pop")
        if animation not in {"none", "fade", "pop", "rise"}:
            raise ValueError("花字动画无效")
        position = raw.get("position", "upper")
        if position not in {"upper", "center", "lower"}:
            raise ValueError("花字位置无效")
        color = raw.get("color", "#FFD85C")
        if color not in COLORS:
            raise ValueError("花字颜色无效")
        clean.append({"text": txt, "start": start, "end": end,
                      "animation": animation, "position": position, "color": color})
    out["flowers"] = clean
    return out


def integer(value, label, minimum, maximum):
    if isinstance(value, bool):
        raise ValueError(f"{label}必须是整数")
    try:
        i = int(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{label}无效")
    if str(value).strip() not in {str(i), str(float(i))}:
        raise ValueError(f"{label}必须是整数")
    if not minimum <= i <= maximum:
        raise ValueError(f"{label}必须在 {minimum}–{maximum} 范围")
    return i


def num(value, label, minimum, maximum):
    if isinstance(value, bool):
        raise ValueError(f"{label}无效")
    try:
        v = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"{label}无效")
    if not math.isfinite(v) or not minimum <= v <= maximum:
        raise ValueError(f"{label}超出范围")
    return v


def ass_time(seconds: float) -> str:
    cs = round(seconds * 100)
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, centi = divmod(rem, 100)
    return f"{h}:{m:02}:{s:02}.{centi:02}"


def ass_color(hex_color: str) -> str:
    value = hex_color.lstrip("#")
    return f"&H00{value[4:6]}{value[2:4]}{value[:2]}"


def clean_text(text: str) -> str:
    """禁止 ASS 命令注入；换行转换为受控换行。"""
    return (text.replace("\\", "＼").replace("{", "｛").replace("}", "｝")
            .replace("\r", "").replace("\n", r"\N").replace(",", "，"))


def make_ass(folder: Path, config: dict, captions: list[tuple],
             duration: float, width: int, height: int) -> dict:
    width, height = max(320, width), max(320, height)
    # 大尺寸原视频自动按宽度调字号，避免 320 像素测试片中文字超界。
    factor = min(1.0, width / 720)
    caption_size = max(15, round(config["subtitleSize"] * factor))
    flower_size = max(20, round(caption_size * 1.42))
    outline = max(2, round(caption_size * .07))
    margin = round(width * .075)
    bottom = round(height * config["subtitleBottom"] / 100)
    style = (
        "Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour,"
        " BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle,"
        " BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
    )
    def line(name, size, color, align, marginv):
        return f"Style: {name},Microsoft YaHei,{size},{ass_color(color)},&H00FFFFFF,&H00131313,&H7F111111,-1,0,0,0,100,100,0,0,1,{outline},1,{align},{margin},{margin},{marginv},1"
    body = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}",
        f"PlayResY: {height}", "ScaledBorderAndShadow: yes", "WrapStyle: 2", "",
        "[V4+ Styles]", f"Format: {style}",
        line("Caption", caption_size, config["subtitleColor"], 2, bottom),
        line("Flower", flower_size, "#FFD85C", 5, 0), "",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]
    cap_n, flower_n = 0, 0
    if config["subtitleEnabled"]:
        for start, end, words in captions:
            if not words.strip() or start >= duration:
                continue
            end = min(end, duration)
            if end <= start:
                continue
            animation = config["subtitleAnimation"]
            effect = ""
            if animation == "fade":
                effect = r"{\fad(100,90)}"
            elif animation == "pop":
                effect = r"{\fscx85\fscy85\t(0,180,\fscx100\fscy100)}"
            body.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Caption,,0,0,0,,{effect}{clean_text(words)}")
            cap_n += 1
    y_factor = {"upper": .27, "center": .48, "lower": .68}
    for f in config["flowers"]:
        start, end = f["start"], min(f["end"], duration)
        if start >= duration or end <= start:
            continue
        x, y = round(width*.5), round(height*y_factor[f["position"]])
        col = ass_color(f["color"])
        effect = r"{\pos("+f"{x},{y}"+r")\c"+col
        if f["animation"] == "pop":
            effect += r"\fscx55\fscy55\t(0,250,\fscx100\fscy100)\fad(80,120)"
        elif f["animation"] == "fade":
            effect += r"\fad(220,200)"
        elif f["animation"] == "rise":
            effect = r"{\move("+f"{x},{y+round(height*.07)},{x},{y},0,340)"+r"\c"+col+r"\fad(140,160)"
        effect += "}"
        body.append(f"Dialogue: 1,{ass_time(start)},{ass_time(end)},Flower,,0,0,0,,{effect}{clean_text(f['text'])}")
        flower_n += 1
    (folder/"packaging.ass").write_text("\n".join(body)+"\n",encoding="utf-8-sig")
    return {"burnedSubtitleLines": cap_n, "animatedFlowers": flower_n,
            "assFile": "packaging.ass"}


def package_video(folder: Path, source: Path, duration: float,
                  info: dict, captions: list[tuple], config: dict,
                  audio_files: dict) -> tuple[Path, dict]:
    config = validate(config)
    if not (config["subtitleEnabled"] or config["flowers"] or config["openingZoom"] or
            config["bgmEnabled"] or config["sfxEnabled"]):
        return source, {"applied": False, "reason": "用户关闭全部包装项"}
    if config["bgmEnabled"] and "bgm" not in audio_files:
        raise ValueError("已启用 BGM 但没有上传音乐文件")
    if config["sfxEnabled"] and "sfx" not in audio_files:
        raise ValueError("已启用音效但没有上传音效文件")
    out = make_ass(folder,config,captions,duration,
                   info.get("width",720),info.get("height",1280))
    graph = []
    filters = []
    has_overlay = config["subtitleEnabled"] or bool(config["flowers"])
    v = "[0:v]"
    if config["openingZoom"]:
        w, h = int(info["width"]), int(info["height"])
        if w <= 0 or h <= 0:
            raise ValueError("开头缓推需要明确视频分辨率")
        # 输入按 25fps 归一化后 zoompan 每帧生成一帧，不改变视频总时长。
        filters += ["fps=25", "zoompan=z='min(1.10,1+on*0.0016)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s="+f"{w}x{h}"+":fps=25"]
    if has_overlay:
        filters.append("ass=filename=packaging.ass")
    filters.append("format=yuv420p")
    graph.append(v + ",".join(filters)+"[vout]")
    args=["ffmpeg","-y","-hide_banner","-nostdin","-i",str(source)]
    mixer=[]
    source_has_audio = bool(info.get("hasAudio"))
    # FFmpeg 解析输入文件必须按序添加。
    if config["bgmEnabled"]:
        args += ["-stream_loop","-1","-i",str(audio_files["bgm"])]
    if config["sfxEnabled"]:
        args += ["-i",str(audio_files["sfx"])]
    if config["bgmEnabled"] or config["sfxEnabled"]:
        if source_has_audio:
            graph.append("[0:a]aformat=sample_rates=44100:channel_layouts=stereo[amain]")
        else:
            graph.append(f"anullsrc=r=44100:cl=stereo,atrim=duration={duration:.3f}[amain]")
        mixer.append("[amain]")
        input_idx=1
        if config["bgmEnabled"]:
            vol=config["bgmVolume"]
            fade_d=min(0.4,duration/3)
            graph.append(f"[{input_idx}:a]volume={vol:.3f},atrim=duration={duration:.3f},asetpts=PTS-STARTPTS,afade=t=in:st=0:d={fade_d:.3f},afade=t=out:st={max(0,duration-fade_d):.3f}:d={fade_d:.3f}[bgm]")
            mixer.append("[bgm]")
            input_idx+=1
        if config["sfxEnabled"] and config["sfxTime"] < duration:
            delay=round(config["sfxTime"]*1000)
            graph.append(f"[{input_idx}:a]volume={config['sfxVolume']:.3f},adelay=delays={delay}:all=1,atrim=duration={duration:.3f},asetpts=PTS-STARTPTS[sfx]")
            mixer.append("[sfx]")
        graph.append("".join(mixer)+f"amix=inputs={len(mixer)}:duration=first:dropout_transition=0:normalize=0[aout]")
    (folder/"package_filters.txt").write_text(";\n".join(graph),encoding="utf-8")
    result=folder/"final_video.mp4"
    args += ["-filter_complex_script","package_filters.txt","-map","[vout]"]
    if mixer:
        args += ["-map","[aout]","-c:a","aac","-b:a","160k"]
    elif source_has_audio:
        args += ["-map","0:a:0","-c:a","copy"]
    args += ["-c:v","libx264","-preset","veryfast","-crf","21","-pix_fmt","yuv420p",
             "-movflags","+faststart",str(result)]
    proc=subprocess.run(args,cwd=folder,capture_output=True,text=True,
                        encoding="utf-8",errors="replace",timeout=3600)
    if proc.returncode:
        raise RuntimeError("视频包装失败：" + proc.stderr[-1300:])
    return result, {"applied": True, "subtitleAnimation": config["subtitleAnimation"],
                    "openingZoom": config["openingZoom"],
                    "bgmMixed":config["bgmEnabled"],"sfxMixed":config["sfxEnabled"],
                    **out}
