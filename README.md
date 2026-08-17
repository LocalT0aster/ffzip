# ffzip

Small FFmpeg command-line tools for inspecting media and producing compact H.264 MP4 files.

- `ffp` prints a compact `ffprobe` summary, one line per stream.
- `ffzip` resizes and reencodes videos. It can process multiple files and glob patterns.

## Requirements

- [FFmpeg](https://ffmpeg.org/) provides `ffmpeg` and `ffprobe`.
- [uv](https://docs.astral.sh/uv/) runs the scripts and installs Python 3.14 when needed.

## Install

Clone the repository wherever you want to keep it, then create symlinks in `~/.local/bin` that point back to that clone:

```bash
git clone https://github.com/LocalT0aster/ffzip.git ~/src/ffzip
cd ~/src/ffzip

mkdir -p ~/.local/bin
ln -sfn "$PWD/ffzip" ~/.local/bin/ffzip
ln -sfn "$PWD/ffp" ~/.local/bin/ffp
```

Ensure `~/.local/bin` is on your `PATH`, then verify the installation:

```bash
ffzip --help
ffp --help
```

If you move the clone, enter its new directory and rerun the two `ln -sfn` commands. The symlinks will point at the new location without reinstalling anything.

## Usage

Inspect one or more media files:

```bash
ffp video.webm
ffp "**/*.mp4"
```

Convert files with the default 720px shorter-side cap:

```bash
ffzip input.webm
ffzip first.webm second.webm
ffzip "**/*.webm"
```

Use `-o` only when converting one input to a custom output path:

```bash
ffzip input.webm -o converted.mp4
```

Useful `ffzip` options:

```bash
ffzip input.webm -s 480          # Cap the shorter side at 480px.
ffzip input.webm -r 30000/1001  # Set the output frame rate.
ffzip input.webm -b 1M          # Use a 1 Mbit/s video bitrate.
ffzip input.webm --crf 23       # Use x264 CRF quality mode.
ffzip input.webm -k             # Keep the declared source video bitrate.
```

`-b`, `--crf`, and `-k` are mutually exclusive. Default filenames describe the selected codec, size, frame rate, and explicit quality option, for example `input_h264_720p_30fps_1M.mp4`.
