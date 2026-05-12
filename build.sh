#!/usr/bin/env bash
set -e

pip install -r requirements.txt

# Download static ffmpeg binary for audio (MP3) conversion
mkdir -p bin
echo "Downloading ffmpeg..."
wget -q -O /tmp/ffmpeg.tar.xz \
  "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"
tar -xf /tmp/ffmpeg.tar.xz -C /tmp/
mv /tmp/ffmpeg-master-latest-linux64-gpl/bin/ffmpeg bin/ffmpeg
mv /tmp/ffmpeg-master-latest-linux64-gpl/bin/ffprobe bin/ffprobe
chmod +x bin/ffmpeg bin/ffprobe
rm -rf /tmp/ffmpeg*
echo "ffmpeg ready: $(bin/ffmpeg -version | head -1)"
