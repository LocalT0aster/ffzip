"""Unit tests for the ffp CLI helpers."""

import importlib.machinery
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).parents[1] / "ffp"
LOADER = importlib.machinery.SourceFileLoader("ffp", str(SCRIPT_PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
ffp = importlib.util.module_from_spec(SPEC)
sys.modules[LOADER.name] = ffp
LOADER.exec_module(ffp)


class DurationTests(unittest.TestCase):
    def test_omits_seconds_when_duration_has_hours(self) -> None:
        self.assertEqual(ffp._format_duration("5025.8"), "1h 23m")

    def test_includes_seconds_when_duration_has_no_hours(self) -> None:
        self.assertEqual(ffp._format_duration("1425.8"), "23m 45s")


class RenderTests(unittest.TestCase):
    def test_renders_compact_lines_for_common_streams(self) -> None:
        probe = {
            "format": {"duration": "5025.8", "size": "44669337", "bit_rate": "71099"},
            "streams": [
                {
                    "index": 0,
                    "codec_type": "video",
                    "codec_name": "av1",
                    "profile": "Main",
                    "width": 1920,
                    "height": 1080,
                    "avg_frame_rate": "24000/1001",
                    "bit_rate": "64000",
                },
                {
                    "index": 1,
                    "codec_type": "audio",
                    "codec_name": "opus",
                    "channels": 2,
                    "sample_rate": "48000",
                    "bit_rate": "7000",
                    "tags": {"language": "eng"},
                },
                {
                    "index": 2,
                    "codec_type": "subtitle",
                    "codec_name": "webvtt",
                    "tags": {"language": "eng"},
                    "disposition": {"default": 1},
                },
            ],
        }

        self.assertEqual(
            ffp._render(Path("clip.webm"), probe),
            "\n".join(
                (
                    "clip.webm | 1h 23m | 42.6 MiB | 71.1 kb/s",
                    "#0 | video | av1 Main | 1920x1080 | 23.976 fps | 64 kb/s",
                    "#1 | audio | opus | stereo | 48 kHz | 7 kb/s | eng",
                    "#2 | subtitle | webvtt | eng | default",
                )
            ),
        )

    def test_omits_unavailable_stream_fields(self) -> None:
        self.assertEqual(
            ffp._render(Path("unknown.bin"), {"streams": [{"index": 3, "codec_type": "data"}]}),
            "unknown.bin\n#3 | data",
        )


class ProbeTests(unittest.TestCase):
    def test_parses_ffprobe_json(self) -> None:
        result = ffp.subprocess.CompletedProcess([], 0, '{"streams": []}', "")
        with mock.patch.object(ffp.subprocess, "run", return_value=result) as run:
            self.assertEqual(ffp._probe(Path("clip.webm")), {"streams": []})

        run.assert_called_once_with(
            [*ffp.FFPROBE_CMD, "clip.webm"], check=False, text=True, capture_output=True
        )

    def test_rejects_failed_or_invalid_ffprobe_output(self) -> None:
        for result in (
            ffp.subprocess.CompletedProcess([], 1, "", "invalid file"),
            ffp.subprocess.CompletedProcess([], 0, "not json", ""),
            ffp.subprocess.CompletedProcess([], 0, "[]", ""),
        ):
            with self.subTest(result=result):
                with mock.patch.object(ffp.subprocess, "run", return_value=result):
                    with self.assertRaises(RuntimeError):
                        ffp._probe(Path("clip.webm"))


if __name__ == "__main__":
    unittest.main()
