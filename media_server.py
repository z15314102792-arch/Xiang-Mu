"""实际口播剪辑工作台 HTTP 服务；仅监听 127.0.0.1。

/demo 保留历史规则演示，首页 / 执行真实视频处理。
"""
from __future__ import annotations

import argparse
import json
import re
import webbrowser
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import media_workflow as media
from portfolio import Handler as DemoHandler, ROOT

JOB = re.compile(r"^/api/real/job/([a-f0-9]{32})$")
ASSET = re.compile(r"^/api/real/file/([a-f0-9]{32})/(source|video|srt|report)$")


class Handler(DemoHandler):
    def send_page(self, name: str):
        raw = (ROOT / "web" / name).read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_asset(self, path: Path, content_type: str, download=False):
        size = path.stat().st_size
        rng = self.headers.get("Range", "")
        start, end = 0, size - 1
        if rng:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
            if not match or (not match.group(1) and not match.group(2)):
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                return
            if not match.group(1):
                n = int(match.group(2))
                start = max(0, size - n)
            else:
                start = int(match.group(1))
                end = min(size - 1, int(match.group(2))) if match.group(2) else size - 1
            if start > end or start >= size:
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                return
        count = end - start + 1
        self.send_response(HTTPStatus.PARTIAL_CONTENT if rng else HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(count))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if rng:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        try:
            with path.open("rb") as fp:
                fp.seek(start)
                remaining = count
                while remaining:
                    chunk = fp.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (ConnectionResetError, BrokenPipeError):
            pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html", "/workbench"):
            return self.send_page("workbench.html")
        if path == "/demo":
            return self.send_page("index.html")
        if path == "/packaging.js":
            raw = (ROOT / "web" / "packaging.js").read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)
            return
        if path == "/api/real/health":
            return self.respond_json({"ok": bool(media.shutil.which("ffmpeg") and media.shutil.which("ffprobe")),
                                      "whisperTinyCached": media.whisper_cache("tiny").is_file(),
                                      "whisperSmallCached": media.whisper_cache("small").is_file(),
                                      "mode": "actual-local-video-processing",
                                      "maxBytes": media.MAX_UPLOAD_BYTES})
        match = JOB.fullmatch(path)
        if match:
            try:
                return self.respond_json(media.read_job(match.group(1)))
            except (ValueError, FileNotFoundError):
                return self.respond_json({"error": "找不到这个项目"}, HTTPStatus.NOT_FOUND)
        match = ASSET.fullmatch(path)
        if match:
            try:
                kind = match.group(2)
                asset = media.job_asset(match.group(1), kind)
                mime = "video/mp4" if kind in ("video", "source") else ("text/plain; charset=utf-8" if kind == "srt" else "application/json")
                return self.send_asset(asset, mime, kind in ("srt", "report", "video"))
            except (ValueError, FileNotFoundError):
                return self.respond_json({"error": "文件不存在或尚未生成"}, HTTPStatus.NOT_FOUND)
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/real/"):
            return super().do_POST()
        # 浏览器同源调用才能操作本地视频文件，跨域页面不能借用此服务。
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if self.headers.get("X-Workflow-Local") != "1" or (
            origin and origin not in {f"http://{host}", f"https://{host}"}
        ):
            return self.respond_json({"error": "请求未通过本地来源校验"}, HTTPStatus.FORBIDDEN)
        try:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise ValueError("请求体大小不合法")
            if path == "/api/real/audio":
                if not 0 < length <= 50_000_000:
                    raise ValueError("上传音频不得超过 50MB")
                query = parse_qs(urlparse(self.path).query)
                job_id = (query.get("id") or [""])[0]
                kind = (query.get("kind") or [""])[0]
                name = (query.get("name") or [""])[0]
                return self.respond_json(media.upload_audio(job_id, kind, name, self.rfile, length))
            if path == "/api/real/upload":
                if not 0 < length <= media.MAX_UPLOAD_BYTES:
                    raise ValueError("视频文件为空或超过 1.5GB")
                query = parse_qs(urlparse(self.path).query)
                name = (query.get("name") or [""])[0]
                asr = (query.get("asr") or ["off"])[0]
                if not name or len(name) > 255:
                    raise ValueError("文件名称无效")
                result = media.create_job(name, self.rfile, length, asr)
                return self.respond_json(result, HTTPStatus.ACCEPTED)
            if length < 1 or length > 1_000_000:
                raise ValueError("JSON 数据大小超出限制")
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("请求必须为 JSON 对象")
            if path == "/api/real/plan":
                return self.respond_json(media.save_plan(str(data.get("id", "")), data.get("segments")))
            if path == "/api/real/packaging":
                return self.respond_json(media.save_packaging(str(data.get("id", "")), data.get("packaging")))
            if path == "/api/real/export":
                return self.respond_json(
                    media.export_job(str(data.get("id", "")), data.get("segments"),
                                     data.get("reviewed") is True), HTTPStatus.ACCEPTED
                )
            return self.respond_json({"error": "未知操作"}, HTTPStatus.NOT_FOUND)
        except (ValueError, FileNotFoundError, KeyError, TypeError, json.JSONDecodeError) as exc:
            return self.respond_json({"error": str(exc)[:600]}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            return self.respond_json({"error": f"操作失败：{str(exc)[:600]}"}, HTTPStatus.INTERNAL_SERVER_ERROR)


def main():
    ap = argparse.ArgumentParser(description="真实视频工作流 + 规则回归演示")
    ap.add_argument("--port", type=int, default=8990)
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()
    if not 1024 <= args.port <= 65535:
        ap.error("端口需要在 1024..65535")
    media.workspace()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"实际视频工作台：http://127.0.0.1:{args.port}/", flush=True)
    print("原规则案例演示：/demo；项目文件仅保存在本机个人 Videos/XiangMu-workspace", flush=True)
    if args.open:
        webbrowser.open(f"http://127.0.0.1:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
