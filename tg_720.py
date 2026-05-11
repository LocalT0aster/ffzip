#!/usr/bin/env python3
"""Reencode a video to 720p (smallest side) with Telegram-friendly settings."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Final


FFPROBE_CMD: Final[list[str]] = [
    "ffprobe",
    "-v",
    "error",
    "-select_streams",
    "v:0",
    "-show_entries",
    "stream=width,height",
    "-of",
    "csv=p=0",
]


def _run_capture(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a command and capture stdout/stderr.

    Parameters
    ----------
    cmd
        Command and arguments.

    Returns
    -------
    subprocess.CompletedProcess[str]
        Completed process result with captured output.
    """

    return subprocess.run(cmd, check=False, text=True, capture_output=True)


def _probe_resolution(path: Path) -> tuple[int, int]:
    """Get width and height for the first video stream.

    Parameters
    ----------
    path
        Input video path.

    Returns
    -------
    tuple[int, int]
        Width and height in pixels.

    Raises
    ------
    RuntimeError
        If ffprobe fails or the resolution cannot be parsed.
    """

    result = _run_capture([*FFPROBE_CMD, str(path)])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffprobe failed")

    text = result.stdout.strip()
    if not text:
        raise RuntimeError("ffprobe returned empty resolution")

    parts = [p for p in re.split(r"[,\sx]+", text) if p]
    if len(parts) < 2:
        raise RuntimeError(f"unexpected ffprobe output: {text!r}")

    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError as exc:
        raise RuntimeError(f"invalid resolution values: {text!r}") from exc

    if width < 1 or height < 1:
        raise RuntimeError("could not read resolution")

    return width, height


def _scale_filter(width: int, height: int) -> str:
    """Compute the scale filter for the target size.

    Parameters
    ----------
    width
        Input width in pixels.
    height
        Input height in pixels.

    Returns
    -------
    str
        ffmpeg scale filter expression.
    """

    min_side = min(width, height)
    if min_side > 720:
        if width < height:
            return "scale=720:-2:flags=lanczos,setsar=1"
        return "scale=-2:720:flags=lanczos,setsar=1"

    return f"scale={width}:{height},setsar=1"


def _output_path(input_path: Path, output: str | None) -> Path:
    if output:
        return Path(output)
    return input_path.with_name(f"{input_path.stem}_tg720.mp4")


def _run_ffmpeg(input_path: Path, output_path: Path, scale_filter: str) -> int:
    cmd = [
        "ffmpeg",
        "-i",
        str(input_path),
        "-vf",
        scale_filter,
        "-c:v",
        "libx264",
        "-profile:v",
        "baseline",
        "-level",
        "3.1",
        "-b:v",
        "2000k",
        "-maxrate",
        "2100k",
        "-bufsize",
        "4000k",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    return subprocess.run(cmd, check=False).returncode


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reencode a video to 720p on the smallest side with Telegram-friendly settings."
        )
    )
    parser.add_argument("input", help="Input video file path")
    parser.add_argument(
        "output",
        nargs="?",
        help="Output file path (default: <input>_tg720.mp4)",
    )
    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 1

    try:
        width, height = _probe_resolution(input_path)
    except (RuntimeError, OSError) as exc:
        print(f"Resolution probe failed: {exc}", file=sys.stderr)
        return 1

    scale_filter = _scale_filter(width, height)
    output_path = _output_path(input_path, args.output)

    try:
        return _run_ffmpeg(input_path, output_path, scale_filter)
    except FileNotFoundError as exc:
        print(f"ffmpeg not found: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
