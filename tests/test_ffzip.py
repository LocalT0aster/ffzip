"""Unit tests for the ffzip CLI helpers."""

import argparse
import contextlib
import importlib.machinery
import importlib.util
import io
import sys
import tempfile
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

    def test_frame_rate_path_uses_a_filename_safe_suffix(self) -> None:
        bitrate = ffzip._parse_bitrate("1M")
        self.assertEqual(
            ffzip._output_path(
                Path("movie.mkv"),
                None,
                480,
                ffzip.VideoSettings(bitrate=bitrate, crf=None, frame_rate="30000/1001"),
            ),
            Path("movie_h264_480p_30000-1001fps_1M.mp4"),
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


class FrameRateTests(unittest.TestCase):
    def test_accepts_decimal_and_rational_rates(self) -> None:
        for value in ("24", "29.97", "30000/1001"):
            with self.subTest(value=value):
                self.assertEqual(ffzip._parse_frame_rate(value), value)

    def test_rejects_invalid_or_non_positive_rates(self) -> None:
        for value in ("0", "-24", "24/0", "ntsc", "24/1.001"):
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    ffzip._parse_frame_rate(value)

    def test_passes_frame_rate_as_an_ffmpeg_output_option(self) -> None:
        settings = ffzip.VideoSettings(bitrate=None, crf=None, frame_rate="30000/1001")
        result = mock.Mock(returncode=0)
        with mock.patch.object(ffzip.subprocess, "run", return_value=result) as run:
            self.assertEqual(
                ffzip._run_ffmpeg(
                    Path("input.webm"),
                    Path("output.mp4"),
                    "scale=-2:720,setsar=1",
                    settings,
                ),
                0,
            )

        command = run.call_args.args[0]
        frame_rate_index = command.index("-r")
        self.assertEqual(command[frame_rate_index : frame_rate_index + 2], ["-r", "30000/1001"])


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


class BatchTests(unittest.TestCase):
    def test_expands_and_sorts_glob_matches(self) -> None:
        with mock.patch.object(ffzip.glob, "glob", return_value=["b.webm", "a.webm"]) as expand:
            paths, errors = ffzip._expand_inputs(["*.webm", "clip.mp4"])

        self.assertEqual(paths, [Path("a.webm"), Path("b.webm"), Path("clip.mp4")])
        self.assertEqual(errors, [])
        expand.assert_called_once_with("*.webm", recursive=True)

    def test_converts_each_input_to_its_own_default_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory, "first.webm")
            second = Path(directory, "second.webm")
            first.touch()
            second.touch()
            with (
                mock.patch.object(ffzip, "_probe_resolution", return_value=(1920, 1080)),
                mock.patch.object(ffzip, "_run_ffmpeg", return_value=0) as run_ffmpeg,
            ):
                self.assertEqual(ffzip.main([str(first), str(second)]), 0)

        self.assertEqual(run_ffmpeg.call_count, 2)
        self.assertEqual(run_ffmpeg.call_args_list[0].args[1], first.with_name("first_h264_720p.mp4"))
        self.assertEqual(run_ffmpeg.call_args_list[1].args[1], second.with_name("second_h264_720p.mp4"))

    def test_continues_after_a_per_file_probe_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory, "first.webm")
            second = Path(directory, "second.webm")
            first.touch()
            second.touch()
            with (
                mock.patch.object(
                    ffzip,
                    "_probe_resolution",
                    side_effect=[RuntimeError("invalid video"), (1920, 1080)],
                ),
                mock.patch.object(ffzip, "_run_ffmpeg", return_value=0) as run_ffmpeg,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(ffzip.main([str(first), str(second)]), 1)

        run_ffmpeg.assert_called_once()

    def test_output_option_applies_to_one_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, "source.webm")
            destination = Path(directory, "custom.mp4")
            source.touch()
            with (
                mock.patch.object(ffzip, "_probe_resolution", return_value=(1920, 1080)),
                mock.patch.object(ffzip, "_run_ffmpeg", return_value=0) as run_ffmpeg,
            ):
                self.assertEqual(ffzip.main([str(source), "-o", str(destination)]), 0)

        self.assertEqual(run_ffmpeg.call_args.args[1], destination)

    def test_rejects_output_option_for_multiple_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory, "first.webm")
            second = Path(directory, "second.webm")
            first.touch()
            second.touch()
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    ffzip.main([str(first), str(second), "-o", "custom.mp4"])


if __name__ == "__main__":
    unittest.main()
