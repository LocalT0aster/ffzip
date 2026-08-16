"""Unit tests for the ffzip CLI helpers."""

import argparse
import contextlib
import importlib.machinery
import importlib.util
import io
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).parents[1] / "ffzip"
LOADER = importlib.machinery.SourceFileLoader("ffzip", str(SCRIPT_PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
ffzip = importlib.util.module_from_spec(SPEC)
sys.modules[LOADER.name] = ffzip
LOADER.exec_module(ffzip)


class ScaleFilterTests(unittest.TestCase):
    def test_downscales_landscape_to_requested_shorter_side(self) -> None:
        self.assertEqual(
            ffzip._scale_filter(1920, 1080, 480),
            "scale=-2:480:flags=lanczos,setsar=1",
        )

    def test_downscales_portrait_to_requested_shorter_side(self) -> None:
        self.assertEqual(
            ffzip._scale_filter(1080, 1920, 480),
            "scale=480:-2:flags=lanczos,setsar=1",
        )

    def test_does_not_upscale_smaller_input(self) -> None:
        self.assertEqual(ffzip._scale_filter(640, 360, 720), "scale=640:360,setsar=1")


class OutputPathTests(unittest.TestCase):
    def test_default_path_identifies_codec_and_size(self) -> None:
        self.assertEqual(
            ffzip._output_path(
                Path("movie.mkv"), None, 720, ffzip.VideoSettings(bitrate=None, crf=None)
            ),
            Path("movie_h264_720p.mp4"),
        )

    def test_bitrate_path_includes_explicit_bitrate(self) -> None:
        bitrate = ffzip._parse_bitrate("1M")
        self.assertEqual(
            ffzip._output_path(
                Path("movie.mkv"), None, 480, ffzip.VideoSettings(bitrate=bitrate, crf=None)
            ),
            Path("movie_h264_480p_1M.mp4"),
        )

    def test_crf_path_includes_crf(self) -> None:
        self.assertEqual(
            ffzip._output_path(
                Path("movie.mkv"), None, 720, ffzip.VideoSettings(bitrate=None, crf=43)
            ),
            Path("movie_h264_720p_C43.mp4"),
        )

    def test_explicit_output_path_is_unchanged(self) -> None:
        self.assertEqual(
            ffzip._output_path(
                Path("movie.mkv"), "output.webm", 720, ffzip.VideoSettings(None, None)
            ),
            Path("output.webm"),
        )

    def test_implicit_bitrate_is_not_included_in_filename(self) -> None:
        parser = ffzip._build_parser()
        args = parser.parse_args(["movie.mkv"])
        self.assertIsNone(args.video_bitrate)
        self.assertEqual(
            ffzip._video_quality_args(ffzip.VideoSettings(args.video_bitrate, args.crf)),
            ["-b:v", "2000k", "-maxrate", "2100k", "-bufsize", "4000k"],
        )


class VideoBitrateProbeTests(unittest.TestCase):
    def test_probes_first_video_stream_bitrate(self) -> None:
        result = ffzip.subprocess.CompletedProcess([], 0, "1000000\n", "")
        with mock.patch.object(ffzip, "_run_capture", return_value=result) as run_capture:
            bitrate = ffzip._probe_video_bitrate(Path("movie.webm"))

        self.assertEqual(bitrate, ffzip.Bitrate(value="1000k", bits_per_second=1_000_000))
        run_capture.assert_called_once_with(
            [*ffzip.FFPROBE_VIDEO_BITRATE_CMD, "movie.webm"]
        )

    def test_rejects_missing_or_invalid_bitrate(self) -> None:
        for stdout in ("", "N/A\n", "0\n", "-1\n"):
            with self.subTest(stdout=stdout):
                result = ffzip.subprocess.CompletedProcess([], 0, stdout, "")
                with mock.patch.object(ffzip, "_run_capture", return_value=result):
                    with self.assertRaises(RuntimeError):
                        ffzip._probe_video_bitrate(Path("movie.webm"))

    def test_reports_ffprobe_failure(self) -> None:
        result = ffzip.subprocess.CompletedProcess([], 1, "", "unsupported input")
        with mock.patch.object(ffzip, "_run_capture", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "unsupported input"):
                ffzip._probe_video_bitrate(Path("movie.webm"))

    def test_inferred_bitrate_uses_bitrate_mode(self) -> None:
        bitrate = ffzip.Bitrate(value="436k", bits_per_second=436_000)
        self.assertEqual(
            ffzip._video_quality_args(ffzip.VideoSettings(bitrate=bitrate, crf=None)),
            ["-b:v", "436k", "-maxrate", "457800", "-bufsize", "872k"],
        )


class MinSideTests(unittest.TestCase):
    def test_accepts_positive_integer(self) -> None:
        self.assertEqual(ffzip._parse_min_side("480"), 480)

    def test_rejects_non_positive_values(self) -> None:
        for value in ("0", "-1", "480.5", "invalid"):
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    ffzip._parse_min_side(value)


class QualityArgumentTests(unittest.TestCase):
    def test_keep_bitrate_is_mutually_exclusive_with_other_quality_modes(self) -> None:
        parser = ffzip._build_parser()
        for arguments in (
            ["movie.webm", "-k", "-b", "1M"],
            ["movie.webm", "-k", "--crf", "23"],
        ):
            with self.subTest(arguments=arguments):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        parser.parse_args(arguments)


if __name__ == "__main__":
    unittest.main()
