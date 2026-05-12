import os
import re
import threading
import uuid
import tempfile
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template, after_this_request
import yt_dlp

app = Flask(__name__)

IS_CLOUD = bool(os.environ.get("RENDER") or os.environ.get("RAILWAY_ENVIRONMENT"))
DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "yt_downloads" if IS_CLOUD else Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# ffmpeg bundled in bin/ during cloud build
BIN_DIR = Path(__file__).parent / "bin"
FFMPEG_LOCATION = str(BIN_DIR) if BIN_DIR.exists() and (BIN_DIR / "ffmpeg").exists() else None

download_progress = {}


def sanitize(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def ydl_opts(quality, fmt, out_dir, hook):
    base = {
        "outtmpl": str(out_dir / "%(id)s_%(title).60s.%(ext)s"),
        "progress_hooks": [hook],
        "quiet": True,
        "no_warnings": True,
    }
    if FFMPEG_LOCATION:
        base["ffmpeg_location"] = FFMPEG_LOCATION

    if fmt == "mp3":
        return {**base,
            "format": "bestaudio/best",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        }

    q_map = {
        "2160": "bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/best[height<=2160]",
        "1080": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]",
        "720":  "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]",
        "480":  "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]",
        "360":  "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]",
        "240":  "bestvideo[height<=240][ext=mp4]+bestaudio[ext=m4a]/best[height<=240]",
    }
    return {**base,
        "format": q_map.get(quality, "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"),
        "merge_output_format": "mp4",
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/info", methods=["POST"])
def get_info():
    url = (request.get_json(force=True, silent=True) or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "URL kiritilmadi"}), 400
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        heights = {f.get("height") for f in info.get("formats", [])
                   if f.get("height") and f.get("vcodec") != "none"}
        available = sorted([h for h in [2160, 1080, 720, 480, 360, 240] if h in heights], reverse=True)
        return jsonify({
            "title": info.get("title", ""),
            "thumbnail": info.get("thumbnail", ""),
            "duration": info.get("duration", 0),
            "uploader": info.get("uploader", ""),
            "view_count": info.get("view_count", 0),
            "available_qualities": available,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/download", methods=["POST"])
def start_download():
    data = request.get_json(force=True, silent=True) or {}
    url = data.get("url", "").strip()
    quality = str(data.get("quality", "best"))
    fmt = data.get("format", "mp4")
    if not url:
        return jsonify({"error": "URL kiritilmadi"}), 400

    did = str(uuid.uuid4())
    download_progress[did] = {"status": "starting", "percent": 0, "filepath": None}

    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
            pct = int(d.get("downloaded_bytes", 0) / total * 100)
            download_progress[did].update(status="downloading", percent=pct)
        elif d["status"] == "finished":
            download_progress[did].update(status="processing", percent=99)

    def run():
        try:
            opts = ydl_opts(quality, fmt, DOWNLOAD_DIR, hook)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # find the output file
                ext = "mp3" if fmt == "mp3" else "mp4"
                vid_id = info.get("id", "")
                matches = list(DOWNLOAD_DIR.glob(f"{vid_id}_*{ext}"))
                if not matches:
                    matches = sorted(DOWNLOAD_DIR.glob(f"*.{ext}"), key=lambda p: p.stat().st_mtime, reverse=True)
                if matches:
                    download_progress[did].update(status="done", percent=100, filepath=str(matches[0]),
                                                   filename=matches[0].name)
                else:
                    download_progress[did].update(status="error", error="Fayl topilmadi")
        except Exception as e:
            download_progress[did].update(status="error", error=str(e))

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"download_id": did})


@app.route("/api/progress/<did>")
def get_progress(did):
    info = download_progress.get(did)
    if not info:
        return jsonify({"error": "Topilmadi"}), 404
    return jsonify({k: v for k, v in info.items() if k != "filepath"})


@app.route("/api/file/<did>")
def serve_file(did):
    info = download_progress.get(did)
    if not info or info.get("status") != "done":
        return jsonify({"error": "Fayl tayyor emas"}), 400
    fp = Path(info["filepath"])
    if not fp.exists():
        return jsonify({"error": "Fayl topilmadi"}), 404

    @after_this_request
    def _cleanup(resp):
        try:
            fp.unlink(missing_ok=True)
            download_progress.pop(did, None)
        except Exception:
            pass
        return resp

    return send_file(fp, as_attachment=True, download_name=fp.name)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
