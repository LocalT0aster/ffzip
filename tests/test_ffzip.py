"""Unit tests for the ffzip CLI helpers."""

import argparse
import importlib.machinery
import importlib.util
import sys
import unittest
from pathlib import Path


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


class MinSideTests(unittest.TestCase):
    def test_accepts_positive_integer(self) -> None:
        self.assertEqual(ffzip._parse_min_side("480"), 480)

    def test_rejects_non_positive_values(self) -> None:
        for value in ("0", "-1", "480.5", "invalid"):
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    ffzip._parse_min_side(value)


if __name__ == "__main__":
    unittest.main()
