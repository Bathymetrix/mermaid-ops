"""Focused offline tests for servercopy."""

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, call, patch


SCRIPT = Path(__file__).resolve().parents[1] / "servercopy"
LOADER = SourceFileLoader("servercopy_module", str(SCRIPT))
SPEC = spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
servercopy = module_from_spec(SPEC)
sys.modules[LOADER.name] = servercopy
LOADER.exec_module(servercopy)


def ftps_source(user: str = "eso") -> servercopy.Source:
    return servercopy.Source(
        user,
        "automaid",
        "ftps-explicit",
        "taal.unice.fr",
        21,
        f"{user}/",
    )


def sftp_source(user: str = "s_m0057") -> servercopy.Source:
    return servercopy.Source(
        user,
        user,
        "sftp",
        "rudics.thorium.cls.fr",
        22,
        ".",
    )


class MirrorScriptTests(unittest.TestCase):
    forbidden_fragments = (
        "--file",
        "--target-directory",
        "--overwrite",
        "--delete",
        "xfer:timeout",
        "sftp:auto-confirm",
        "cls ",
        "find ",
        "glob ",
        "ls ",
        "suffix=",
    )

    @staticmethod
    def mirror_lines(script: str) -> list[str]:
        return [line for line in script.splitlines() if line.startswith("mirror ")]

    def assert_include_filters(self, mirror: str) -> None:
        self.assertEqual(len(servercopy.MIRROR_INCLUDE_GLOBS), 9)
        for pattern in servercopy.MIRROR_INCLUDE_GLOBS:
            self.assertEqual(mirror.count(f"--include-glob={pattern}"), 1)

    def test_each_protocol_uses_one_suffix_filtered_mirror(self) -> None:
        for source in (sftp_source(), ftps_source()):
            with self.subTest(protocol=source.protocol):
                destination = Path("/tmp/servers") / source.user
                script = servercopy.build_lftp_script(
                    source,
                    "fake-password",
                    destination,
                    False,
                )
                lines = script.splitlines()
                mirrors = self.mirror_lines(script)

                self.assertEqual(len(mirrors), 1)
                mirror = mirrors[0]
                self.assertEqual(mirror.count('--exclude="(^|/)backups/$"'), 1)
                self.assert_include_filters(mirror)
                self.assertEqual(lines[-4], f'cd "{source.remote_root}"')
                self.assertEqual(lines[-3], f'lcd "{destination}"')
                self.assertEqual(lines[-2], mirror)
                self.assertEqual(lines[-1], "bye")
                self.assertEqual(script.count("open -u "), 1)
                for fragment in self.forbidden_fragments:
                    self.assertNotIn(fragment, script)

    def test_ftps_uses_only_validated_tls_settings(self) -> None:
        script = servercopy.build_lftp_script(
            ftps_source(),
            "fake-password",
            Path("/tmp/servers/eso"),
            False,
        )

        self.assertIn("set ftp:ssl-force yes", script)
        self.assertIn("set ftp:ssl-protect-data yes", script)
        self.assertIn("set ftp:ssl-protect-list yes", script)
        self.assertNotIn("set ssl:verify-certificate", script)
        self.assertIn(
            'open -u "automaid","fake-password" "ftp://taal.unice.fr:21"',
            script,
        )
        self.assertNotIn("ftps://", script)

    def test_sftp_has_no_unnecessary_protocol_settings(self) -> None:
        script = servercopy.build_lftp_script(
            sftp_source(),
            "fake-password",
            Path("/tmp/servers/s_m0057"),
            False,
        )

        self.assertNotIn("set sftp:", script)
        self.assertNotIn("set ftp:", script)
        self.assertIn(
            'open -u "s_m0057","fake-password" '
            '"sftp://rudics.thorium.cls.fr:22"',
            script,
        )

    def test_dry_run_adds_only_dry_run_to_mirror_options(self) -> None:
        destination = Path("/tmp/servers/s_m0057")
        source = sftp_source()
        normal_script = servercopy.build_lftp_script(
            source,
            "fake-password",
            destination,
            False,
        )
        script = servercopy.build_lftp_script(
            source,
            "fake-password",
            destination,
            True,
        )
        normal_mirror = self.mirror_lines(normal_script)[0]
        mirrors = self.mirror_lines(script)

        self.assertEqual(len(mirrors), 1)
        self.assertEqual(
            mirrors[0],
            normal_mirror.replace(" --verbose", " --dry-run --verbose"),
        )
        self.assertEqual(mirrors[0].count("--dry-run"), 1)
        self.assert_include_filters(mirrors[0])
        for fragment in self.forbidden_fragments:
            self.assertNotIn(fragment, script)

    def test_three_digit_glob_is_included_without_discovery_commands(self) -> None:
        script = servercopy.build_lftp_script(
            sftp_source(),
            "fake-password",
            Path("/tmp/servers/s_m0057"),
            False,
        )
        mirror = self.mirror_lines(script)[0]

        self.assertEqual(mirror.count("--include-glob=*.[0-9][0-9][0-9]"), 1)
        self.assertFalse(hasattr(servercopy, "build_discovery_lftp_script"))
        self.assertFalse(hasattr(servercopy, "parse_numbered_suffixes"))


class LftpRunnerTests(unittest.TestCase):
    @staticmethod
    def process(
        *,
        output: list[bytes] | None = None,
        waits: list[object] | None = None,
    ) -> MagicMock:
        process = MagicMock()
        process.stdin = MagicMock()
        process.stdout = MagicMock()
        process.stdout.read1.side_effect = [*(output or []), b""]
        process.wait.side_effect = waits or [0]
        return process

    def test_child_exit_status_is_propagated(self) -> None:
        process = self.process(waits=[7])
        report = MagicMock()

        with patch.object(
            servercopy.subprocess,
            "Popen",
            return_value=process,
        ) as popen:
            status = servercopy.run_lftp(
                "/mock/lftp",
                "mirror\nbye\n",
                report,
                "sync",
                "eso",
            )

        self.assertEqual(status, 7)
        self.assertEqual(popen.call_args.args, (["/mock/lftp"],))
        self.assertIn(b"mirror\nbye\n", process.stdin.write.call_args.args)

    def test_native_carriage_return_output_is_forwarded_without_line_parsing(self) -> None:
        process = self.process(output=[b"10%\r20%\r", b"done\n"])
        report = MagicMock()

        with patch.object(servercopy.subprocess, "Popen", return_value=process):
            status = servercopy.run_lftp(
                "/mock/lftp",
                "bye\n",
                report,
                "sync",
                "eso",
            )

        self.assertEqual(status, 0)
        self.assertEqual(
            "".join(item.args[0] for item in report.write_raw.call_args_list),
            "10%\r20%\rdone\n",
        )

    def test_invalid_output_bytes_are_replaced(self) -> None:
        process = self.process(output=[b"bad:\xff\n"])
        report = MagicMock()

        with patch.object(servercopy.subprocess, "Popen", return_value=process):
            servercopy.run_lftp(
                "/mock/lftp",
                "bye\n",
                report,
                "sync",
                "eso",
            )

        report.write_raw.assert_called_once_with("bad:\ufffd\n")

    def test_output_redacts_credential_bearing_urls(self) -> None:
        process = self.process(
            output=[
                b"open: sf",
                b"tp://login:secret@exam",
                b"ple.test/path failed\n",
            ]
        )
        report = MagicMock()

        with patch.object(servercopy.subprocess, "Popen", return_value=process):
            servercopy.run_lftp(
                "/mock/lftp",
                "bye\n",
                report,
                "sync",
                "eso",
            )

        report.write_raw.assert_called_once_with(
            "open: sftp://[REDACTED]@example.test/path failed\n"
        )

    def test_heartbeat_reports_only_process_liveness(self) -> None:
        timeout = subprocess.TimeoutExpired("/mock/lftp", 30)
        process = self.process(waits=[timeout, 0])
        report = MagicMock()

        with (
            patch.object(servercopy.subprocess, "Popen", return_value=process),
            patch.object(servercopy.time, "monotonic", side_effect=[100.0, 131.0]),
        ):
            status = servercopy.run_lftp(
                "/mock/lftp",
                "bye\n",
                report,
                "sync",
                "eso",
            )

        self.assertEqual(status, 0)
        report.write.assert_called_once_with(
            "[sync] still-running user=eso elapsed=31s (process alive)"
        )
        process.terminate.assert_not_called()

    def test_long_output_silence_never_triggers_a_watchdog_failure(self) -> None:
        timeout = subprocess.TimeoutExpired("/mock/lftp", 30)
        process = self.process(waits=[timeout, timeout, timeout, 0])
        report = MagicMock()

        with (
            patch.object(servercopy.subprocess, "Popen", return_value=process),
            patch.object(
                servercopy.time,
                "monotonic",
                side_effect=[0.0, 300.0, 600.0, 900.0],
            ),
        ):
            status = servercopy.run_lftp(
                "/mock/lftp",
                "bye\n",
                report,
                "sync",
                "kobeuni",
                heartbeat_seconds=300,
            )

        self.assertEqual(status, 0)
        self.assertEqual(report.write.call_count, 3)
        self.assertTrue(
            all(
                "(process alive)" in item.args[0]
                for item in report.write.call_args_list
            )
        )
        process.terminate.assert_not_called()
        process.kill.assert_not_called()

    def test_start_failure_is_reported_cleanly(self) -> None:
        report = MagicMock()

        with patch.object(
            servercopy.subprocess,
            "Popen",
            side_effect=OSError("not found"),
        ):
            status = servercopy.run_lftp(
                "/mock/lftp",
                "bye\n",
                report,
                "sync",
                "eso",
            )

        self.assertEqual(status, 1)
        report.write.assert_called_once_with(
            "could not start lftp: not found",
            error=True,
        )


class ConfigurationTests(unittest.TestCase):
    def test_output_default_and_override(self) -> None:
        default = servercopy.parse_args([])
        overridden = servercopy.parse_args(["--output", "~/alternate-servers"])

        self.assertEqual(default.output, Path.home() / "mermaid" / "servers")
        self.assertEqual(overridden.output.expanduser(), Path.home() / "alternate-servers")

    def test_source_registry_uses_endpoint_fields_only(self) -> None:
        sources = servercopy.load_sources(
            SCRIPT.with_name("data") / "servercopy_sources.csv"
        )

        self.assertEqual(len(sources), 19)
        self.assertEqual(sources[-1].user, "kobeuni")
        self.assertEqual(
            servercopy.SOURCE_FIELDS,
            ("user", "login", "protocol", "host", "port", "remote_root"),
        )

    def test_source_registry_skips_full_line_comments(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "sources.csv"
            path.write_text(
                ",".join(servercopy.SOURCE_FIELDS)
                + "\n# inactive endpoint\n"
                + "active,active,sftp,example.com,22,.\n",
                encoding="ascii",
            )

            self.assertEqual(
                servercopy.load_sources(path),
                [
                    servercopy.Source(
                        "active", "active", "sftp", "example.com", 22, "."
                    )
                ],
            )

    def test_comment_only_credentials_file_is_an_empty_registry(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.csv"
            path.write_text("# inactive endpoints\n\n", encoding="ascii")

            self.assertEqual(servercopy.load_credentials(path), {})

    def test_malformed_credentials_remain_fatal(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.csv"
            path.write_text("login,password,extra\n", encoding="ascii")

            with self.assertRaisesRegex(
                servercopy.ConfigError,
                "malformed credentials line 1",
            ):
                servercopy.load_credentials(path)

    def test_duplicate_credential_logins_remain_fatal(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.csv"
            path.write_text("login,one\nlogin,two\n", encoding="ascii")

            with self.assertRaisesRegex(
                servercopy.ConfigError,
                "duplicate credential login on line 2",
            ):
                servercopy.load_credentials(path)


class WorkflowTests(unittest.TestCase):
    def run_dry_workflow(
        self,
        sources: list[servercopy.Source],
        credentials: dict[str, str],
        lftp_results: list[int] | None = None,
    ) -> tuple[int, MagicMock, MagicMock]:
        report = MagicMock()
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name)
        for source in sources:
            (output / source.user).mkdir()
        args = servercopy.parse_args(["--dry-run", "--output", str(output)])

        with (
            patch.object(servercopy.shutil, "which", return_value="/mock/lftp"),
            patch.object(servercopy, "load_sources", return_value=sources),
            patch.object(servercopy, "load_credentials", return_value=credentials),
            patch.object(
                servercopy,
                "run_lftp",
                side_effect=lftp_results or ([0] * len(sources)),
            ) as run_lftp,
            patch.dict(servercopy.os.environ, {}, clear=True),
        ):
            status = servercopy.run_workflow(args, Path("/unused"), report)

        return status, report, run_lftp

    def test_one_mirror_invocation_per_configured_source(self) -> None:
        sources = [sftp_source(), ftps_source(), ftps_source("kobeuni")]
        credentials = {
            source.login: f"password-{source.login}"
            for source in sources
        }

        status, _, run_lftp = self.run_dry_workflow(sources, credentials)

        self.assertEqual(status, 0)
        self.assertEqual(run_lftp.call_count, 3)
        for source, invocation in zip(sources, run_lftp.call_args_list, strict=True):
            script = invocation.args[1]
            mirrors = MirrorScriptTests.mirror_lines(script)
            self.assertEqual(len(mirrors), 1)
            for pattern in servercopy.MIRROR_INCLUDE_GLOBS:
                self.assertEqual(
                    mirrors[0].count(f"--include-glob={pattern}"),
                    1,
                )
            self.assertIn(f'cd "{source.remote_root}"', script)
            lcd_line = next(
                line for line in script.splitlines() if line.startswith("lcd ")
            )
            self.assertTrue(lcd_line.endswith(f"/{source.user}\""))

    def test_nonzero_lftp_status_fails_source_cleanly(self) -> None:
        source = sftp_source()

        status, report, run_lftp = self.run_dry_workflow(
            [source],
            {source.login: "fake-password"},
            [23],
        )

        self.assertEqual(status, 1)
        run_lftp.assert_called_once()
        report.write.assert_has_calls(
            [
                call(
                    "[dry-run] result=failure user=s_m0057 "
                    "lftp-exit=23 elapsed=0s"
                ),
                call("    lftp exit status 23; see inline lftp output", error=True),
            ],
            any_order=True,
        )

    def test_normal_run_uses_one_filtered_mirror_and_records_version(self) -> None:
        source = ftps_source()
        report = MagicMock()
        with TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "_runs").mkdir()
            args = servercopy.parse_args(["--output", str(output)])
            with (
                patch.object(servercopy.shutil, "which", return_value="/mock/lftp"),
                patch.object(servercopy, "load_sources", return_value=[source]),
                patch.object(
                    servercopy,
                    "load_credentials",
                    return_value={source.login: "fake-password"},
                ),
                patch.object(servercopy, "run_lftp", return_value=0) as run_lftp,
                patch.object(
                    servercopy,
                    "utc_now",
                    side_effect=[
                        "2026-07-28T01:00:00Z",
                        "2026-07-28T01:10:00Z",
                    ],
                ),
                patch.dict(servercopy.os.environ, {}, clear=True),
            ):
                status = servercopy.run_workflow(args, Path("/unused"), report)

            self.assertEqual(status, 0)
            script = run_lftp.call_args.args[1]
            mirrors = MirrorScriptTests.mirror_lines(script)
            self.assertEqual(len(mirrors), 1)
            for pattern in servercopy.MIRROR_INCLUDE_GLOBS:
                self.assertEqual(
                    mirrors[0].count(f"--include-glob={pattern}"),
                    1,
                )
            self.assertTrue((output / source.user).is_dir())
            self.assertEqual(
                (output / "_runs" / "servercopy_runs.csv").read_text(
                    encoding="ascii"
                ),
                "user,result,start,end,ver\n"
                "eso,success,2026-07-28T01:00:00Z,"
                "2026-07-28T01:10:00Z,2.1.0\n",
            )

    def test_missing_credential_skips_source_and_runs_others(self) -> None:
        missing = sftp_source("s_m0056")
        runnable = sftp_source("s_m0057")

        status, report, run_lftp = self.run_dry_workflow(
            [missing, runnable],
            {runnable.login: "fake-password"},
        )

        self.assertEqual(status, 0)
        run_lftp.assert_called_once()
        report.write.assert_any_call("  s_m0056 (missing credentials)", error=True)

    def test_all_missing_credentials_exit_nonzero_without_lftp(self) -> None:
        sources = [sftp_source("s_m0055"), sftp_source("s_m0056")]

        status, report, run_lftp = self.run_dry_workflow(sources, {})

        self.assertEqual(status, 1)
        run_lftp.assert_not_called()
        report.write.assert_any_call(
            "\nError: no runnable sources; all selected sources are missing credentials.",
            error=True,
        )

    def test_dry_run_requires_existing_destination_without_creating_it(self) -> None:
        source = sftp_source()
        report = MagicMock()
        with TemporaryDirectory() as directory:
            output = Path(directory)
            args = servercopy.parse_args(["--dry-run", "--output", str(output)])
            with (
                patch.object(servercopy.shutil, "which", return_value="/mock/lftp"),
                patch.object(servercopy, "load_sources", return_value=[source]),
                patch.object(
                    servercopy,
                    "load_credentials",
                    return_value={source.login: "fake-password"},
                ),
                patch.object(servercopy, "run_lftp") as run_lftp,
                patch.dict(servercopy.os.environ, {}, clear=True),
            ):
                status = servercopy.run_workflow(args, Path("/unused"), report)

            self.assertEqual(status, 1)
            self.assertFalse((output / source.user).exists())
            run_lftp.assert_not_called()

    def test_check_performs_no_remote_execution(self) -> None:
        source = sftp_source()
        args = servercopy.parse_args(
            ["--check", "--user", source.user, "--output", "/tmp/servercopy-check"]
        )

        with (
            patch.object(servercopy.shutil, "which", return_value="/mock/lftp"),
            patch.object(servercopy, "load_sources", return_value=[source]),
            patch.object(
                servercopy,
                "load_credentials",
                return_value={source.login: "fake-password"},
            ),
            patch.object(servercopy, "run_lftp") as run_lftp,
            patch.dict(servercopy.os.environ, {}, clear=True),
        ):
            status = servercopy.run_workflow(args, Path("/unused"), MagicMock())

        self.assertEqual(status, 0)
        run_lftp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
