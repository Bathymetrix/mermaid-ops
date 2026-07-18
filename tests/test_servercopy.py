"""Focused offline tests for servercopy."""

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from io import StringIO
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import MagicMock, patch


SCRIPT = Path(__file__).resolve().parents[1] / "servercopy"
LOADER = SourceFileLoader("servercopy_module", str(SCRIPT))
SPEC = spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
servercopy = module_from_spec(SPEC)
sys.modules[LOADER.name] = servercopy
LOADER.exec_module(servercopy)


def taal_source(user: str = "eso") -> servercopy.Source:
    return servercopy.Source(
        user,
        "automaid",
        "ftps-explicit",
        "taal.unice.fr",
        21,
        f"{user}/",
    )


class SequentialMirrorTests(unittest.TestCase):
    def test_authoritative_suffix_tuple_is_hardcoded_in_required_order(self) -> None:
        self.assertEqual(
            servercopy.SYNC_SUFFIXES,
            (".MER", ".LOG", ".BIN", ".cmd", ".out", ".vit", ".S41", ".S61"),
        )
        self.assertFalse(hasattr(servercopy, "SUFFIX_ALLOWLIST"))
        self.assertFalse(hasattr(servercopy, "load_suffix_globs"))

    def test_one_ordered_file_mirror_per_suffix_uses_remote_root(self) -> None:
        for user in ("eso", "kobeuni"):
            with self.subTest(user=user):
                script = servercopy.build_lftp_script(
                    taal_source(user),
                    "fake-password",
                    Path(f"/tmp/servers/{user}"),
                    False,
                )
                mirrors = [
                    line for line in script.splitlines() if line.startswith("mirror ")
                ]
                expected = [
                    f'mirror "-c" "-f" "{user}/*{suffix}"'
                    for suffix in servercopy.SYNC_SUFFIXES
                ]

                self.assertEqual(mirrors, expected)
                self.assertEqual(script.count("open -u "), 1)
                self.assertEqual(script.count("set cmd:fail-exit yes"), 1)
                self.assertEqual(script.count("bye"), 1)
                self.assertIn(f'lcd "/tmp/servers/{user}"', script)
                self.assertNotIn("include-glob", script)
                self.assertNotIn("exclude-glob", script)
                self.assertNotIn("--parallel", script)
                self.assertNotIn("--overwrite", script)

    def test_each_mirror_has_a_visible_suffix_marker(self) -> None:
        script = servercopy.build_lftp_script(
            taal_source(), "fake-password", Path("/tmp/servers/eso"), True
        )

        markers = [
            line for line in script.splitlines() if "step=mirror suffix=" in line
        ]
        self.assertEqual(
            markers,
            [
                f'echo "[servercopy] step=mirror suffix={suffix}"'
                for suffix in servercopy.SYNC_SUFFIXES
            ],
        )
        self.assertEqual(script.count('"--dry-run"'), len(servercopy.SYNC_SUFFIXES))


class LftpRunnerTests(unittest.TestCase):
    def test_default_silence_watchdog_is_fifteen_minutes(self) -> None:
        self.assertEqual(servercopy.LFTP_SILENCE_TIMEOUT_SECONDS, 900.0)

    def test_lftp_output_replaces_invalid_text_bytes(self) -> None:
        process = MagicMock()
        process.stdout.readline.side_effect = [b"bad:\xff\n", b""]
        process.wait.return_value = 0
        report = MagicMock()

        with patch.object(servercopy.subprocess, "Popen", return_value=process) as popen:
            code, lines = servercopy.run_lftp(
                "lftp", "bye\n", report, "sync", "eso", heartbeat_seconds=1
            )

        self.assertEqual((code, lines), (0, ["bad:\ufffd"]))
        report.write.assert_called_once_with("bad:\ufffd")
        process.stdin.write.assert_called_once_with(b"bye\n")
        self.assertEqual(popen.call_args.args, (["lftp"],))

    def test_lftp_reports_when_output_is_silent(self) -> None:
        process = MagicMock()

        def delayed_eof() -> bytes:
            time.sleep(0.03)
            return b""

        process.stdout.readline.side_effect = delayed_eof
        process.wait.return_value = 0
        report = MagicMock()

        with patch.object(servercopy.subprocess, "Popen", return_value=process):
            code, lines = servercopy.run_lftp(
                "lftp", "bye\n", report, "sync", "eso", heartbeat_seconds=0.01
            )

        self.assertEqual((code, lines), (0, []))
        messages = [call.args[0] for call in report.write.call_args_list]
        self.assertTrue(any(message.startswith("[sync] still-running") for message in messages))

    def test_lftp_heartbeat_identifies_active_suffix(self) -> None:
        process = MagicMock()
        output_count = 0

        def marker_then_delayed_eof() -> bytes:
            nonlocal output_count
            output_count += 1
            if output_count == 1:
                return b"[servercopy] step=mirror suffix=.LOG\n"
            time.sleep(0.03)
            return b""

        process.stdout.readline.side_effect = marker_then_delayed_eof
        process.wait.return_value = 0
        report = MagicMock()

        with patch.object(servercopy.subprocess, "Popen", return_value=process):
            servercopy.run_lftp(
                "lftp", "bye\n", report, "sync", "eso", heartbeat_seconds=0.01
            )

        messages = [call.args[0] for call in report.write.call_args_list]
        self.assertTrue(
            any("still-running user=eso suffix=.LOG" in message for message in messages)
        )

    def test_lftp_watchdog_returns_124(self) -> None:
        process = MagicMock()

        def delayed_eof() -> bytes:
            time.sleep(0.05)
            return b""

        process.stdout.readline.side_effect = delayed_eof
        process.wait.return_value = -15

        with patch.object(servercopy.subprocess, "Popen", return_value=process):
            code, lines = servercopy.run_lftp(
                "lftp",
                "bye\n",
                MagicMock(),
                "diagnose-listing",
                "eso",
                heartbeat_seconds=0.01,
                silence_timeout_seconds=0.02,
            )

        self.assertEqual(code, 124)
        self.assertIn("lftp timed out", lines[-1])
        process.terminate.assert_called_once_with()

    def test_listing_uses_norc(self) -> None:
        process = MagicMock()
        process.stdout.readline.side_effect = [b""]
        process.wait.return_value = 0

        with patch.object(servercopy.subprocess, "Popen", return_value=process) as popen:
            servercopy.run_lftp(
                "lftp", "bye\n", MagicMock(), "diagnose-listing", "eso", norc=True
            )

        self.assertEqual(popen.call_args.args, (["lftp", "--norc"],))

    def test_lftp_output_redacts_url_credentials(self) -> None:
        output = "get ftp://example-user:pa@ss@example.test/file"

        redacted = servercopy.redact_lftp_output(output)

        self.assertEqual(redacted, "get ftp://[REDACTED]@example.test/file")


class CommandTests(unittest.TestCase):
    def test_output_default_and_override(self) -> None:
        default = servercopy.parse_args([])
        overridden = servercopy.parse_args(["--output", "~/alternate-servers"])

        self.assertEqual(default.output, Path.home() / "mermaid" / "servers")
        self.assertEqual(overridden.output.expanduser(), Path.home() / "alternate-servers")

    def test_source_registry_uses_endpoint_fields_only(self) -> None:
        sources = servercopy.load_sources(SCRIPT.with_name("servercopy_sources.csv"))

        self.assertEqual(len(sources), 20)
        self.assertEqual(sources[-1].user, "kobeuni")

    def test_listing_scripts_change_only_listing_tls(self) -> None:
        protected = servercopy.build_listing_lftp_script(
            taal_source(), "fake-password", "protected"
        )
        unprotected = servercopy.build_listing_lftp_script(
            taal_source(), "fake-password", "unprotected"
        )

        self.assertIn("set ftp:ssl-protect-list yes", protected)
        self.assertIn("set ftp:ssl-protect-list no", unprotected)
        for script in (protected, unprotected):
            self.assertIn("set ftp:ssl-protect-data yes", script)
            self.assertIn('command cd "eso/"', script)
            self.assertIn('command cls -1 -q -B "."', script)
            self.assertIn(f'echo "{servercopy.LISTING_BEGIN_MARKER}"', script)
            self.assertIn(f'echo "{servercopy.LISTING_END_MARKER}"', script)
            self.assertNotIn("mirror ", script)
            self.assertNotIn("get ", script)
            self.assertNotIn("put ", script)

        differing = [
            (left, right)
            for left, right in zip(
                protected.splitlines(), unprotected.splitlines(), strict=True
            )
            if left != right
        ]
        self.assertEqual(
            differing,
            [("set ftp:ssl-protect-list yes", "set ftp:ssl-protect-list no")],
        )

    def test_listing_cli_matches_operational_commands(self) -> None:
        args = servercopy.parse_args(
            [
                "--user",
                "eso",
                "--diagnose-listing",
                "--listing-tls",
                "protected",
            ]
        )

        self.assertTrue(args.diagnose_listing)
        self.assertEqual(args.listing_tls, "protected")

        with patch("sys.stderr", new=StringIO()):
            with self.assertRaises(SystemExit):
                servercopy.parse_args(["--listing-tls", "unprotected"])
            with self.assertRaises(SystemExit):
                servercopy.parse_args(["--dry-run", "--diagnose-listing"])

    def test_failure_detail_keeps_diagnostics_not_transfer_chatter(self) -> None:
        detail = servercopy.lftp_failure_detail(
            1,
            [
                "[servercopy] step=mirror suffix=.MER",
                "Transferring file `one.MER'",
                "cls: Access failed",
            ],
        )

        self.assertEqual(
            detail,
            "lftp exit status 1\n"
            "[servercopy] step=mirror suffix=.MER\n"
            "cls: Access failed",
        )


class ListingWorkflowTests(unittest.TestCase):
    def run_diagnostic(
        self, lftp_result: tuple[int, list[str]], temp_dir: str
    ) -> tuple[int, MagicMock, MagicMock, Path]:
        output = Path(temp_dir) / "unused-output"
        args = servercopy.parse_args(
            [
                "--user",
                "eso",
                "--diagnose-listing",
                "--listing-tls",
                "protected",
                "--output",
                str(output),
            ]
        )
        report = MagicMock()
        with (
            patch.object(servercopy.shutil, "which", return_value="/mock/lftp"),
            patch.object(servercopy, "load_sources", return_value=[taal_source()]),
            patch.object(
                servercopy,
                "load_credentials",
                return_value={"automaid": "fake-password"},
            ),
            patch.object(servercopy, "run_lftp", return_value=lftp_result) as run_lftp,
            patch.dict(servercopy.os.environ, {}, clear=True),
        ):
            code = servercopy.run_workflow(
                args, Path(temp_dir) / "fake-mermaid-root", report
            )
        return code, report, run_lftp, output

    def test_listing_success_failure_and_timeout_are_clear(self) -> None:
        cases = (
            (
                (
                    0,
                    [
                        servercopy.LISTING_BEGIN_MARKER,
                        "one.MER",
                        "two.LOG",
                        servercopy.LISTING_END_MARKER,
                    ],
                ),
                0,
                "listing succeeded",
            ),
            ((1, ["cls: Access failed"]), 1, "listing failed"),
            ((124, ["lftp timed out after 900s"]), 1, "listing timed out"),
        )
        for lftp_result, expected_code, message in cases:
            with self.subTest(message=message), TemporaryDirectory() as temp_dir:
                code, report, run_lftp, output = self.run_diagnostic(
                    lftp_result, temp_dir
                )
                messages = [
                    call.args[0] for call in report.write.call_args_list if call.args
                ]

                self.assertEqual(code, expected_code)
                self.assertTrue(any(message in line for line in messages))
                self.assertFalse(output.exists())
                run_lftp.assert_called_once()
                self.assertTrue(run_lftp.call_args.kwargs["norc"])
                self.assertNotIn("mirror ", run_lftp.call_args.args[1])

    def test_main_listing_mode_creates_no_log_or_lock_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "diagnostic-output"
            with (
                patch.object(servercopy, "guarded_workflow", return_value=0),
                patch.dict(
                    os.environ,
                    {"MERMAID": str(Path(temp_dir) / "fake-mermaid-root")},
                    clear=True,
                ),
            ):
                code = servercopy.main(
                    [
                        "--user",
                        "eso",
                        "--diagnose-listing",
                        "--listing-tls",
                        "protected",
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(code, 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
