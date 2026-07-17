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


class SuffixAllowlistTests(unittest.TestCase):
    def test_parses_comments_blank_lines_and_numeric_glob(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "suffixes.txt"
            path.write_text(
                "# comment\n\n[0-9][0-9][0-9]\n   # another comment\nMER\nvit\n",
                encoding="ascii",
            )

            suffixes = servercopy.load_suffix_globs(path)

        self.assertEqual(suffixes, (".[0-9][0-9][0-9]", ".MER", ".vit"))

    def test_rejects_malformed_duplicate_and_empty_allowlists(self) -> None:
        invalid_contents = (
            "",
            "# comments only\n",
            ".MER\n",
            "*.MER\n",
            "MER extra\n",
            "foo/bar\n",
            "MER\nMER\n",
        )
        for content in invalid_contents:
            with self.subTest(content=content), TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "suffixes.txt"
                path.write_text(content, encoding="ascii")
                with self.assertRaises(servercopy.ConfigError):
                    servercopy.load_suffix_globs(path)

    def test_runtime_file_drives_generated_include_globs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "suffixes.txt"
            path.write_text("ABC\n[0-9][0-9][0-9]\n", encoding="ascii")
            suffixes = servercopy.load_suffix_globs(path)

        script = servercopy.build_lftp_script(
            taal_source(),
            "fake-password",
            Path("/tmp/servers/eso"),
            True,
            suffixes,
        )

        self.assertIn('"--include-glob=*.ABC"', script)
        self.assertIn('"--include-glob=*.[0-9][0-9][0-9]"', script)
        self.assertNotIn('"--include-glob=*.MER"', script)
        self.assertIn("patterns=2", script)

    def test_tracked_allowlist_loads(self) -> None:
        suffixes = servercopy.load_suffix_globs(servercopy.SUFFIX_ALLOWLIST)

        self.assertEqual(len(suffixes), 8)
        self.assertEqual(suffixes[0], ".[0-9][0-9][0-9]")


class LftpRunnerTests(unittest.TestCase):
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
            ["Transferring file `one.MER'", "cls: Access failed"],
        )

        self.assertEqual(detail, "lftp exit status 1\ncls: Access failed")


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
            patch.object(servercopy, "load_suffix_globs", return_value=(".MER",)),
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
            ((124, ["lftp timed out after 300s"]), 1, "listing timed out"),
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
