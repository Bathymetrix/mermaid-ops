"""Focused offline tests for servercopy."""

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
import sys
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


def rudics_source(user: str = "s_m0057") -> servercopy.Source:
    return servercopy.Source(
        user,
        user,
        "sftp",
        "rudics.thorium.cls.fr",
        22,
        ".",
    )


class NumberedSuffixParsingTests(unittest.TestCase):
    def test_no_numbered_suffixes(self) -> None:
        self.assertEqual(servercopy.parse_numbered_suffixes("foo.MER\nbar.LOG\n"), ())

    def test_one_zero_suffix(self) -> None:
        self.assertEqual(servercopy.parse_numbered_suffixes("foo.000\n"), (".000",))

    def test_contiguous_suffixes_are_numerically_sorted(self) -> None:
        listing = "root/foo.002\nfoo.000\nother/path/bar.001\n"

        self.assertEqual(
            servercopy.parse_numbered_suffixes(listing),
            (".000", ".001", ".002"),
        )

    def test_duplicate_suffixes_are_reduced_to_one(self) -> None:
        listing = "foo.000\nbar.000\nbaz.001\n"

        self.assertEqual(servercopy.parse_numbered_suffixes(listing), (".000", ".001"))

    def test_invalid_forms_and_numbered_directories_are_ignored(self) -> None:
        listing = (
            "short.00\nlong.0000\nletters.ABC\ntrailing.001.tmp\n"
            "digits001\ndirectory.000/\nordinary.MER\n"
        )

        self.assertEqual(servercopy.parse_numbered_suffixes(listing), ())

    def test_sequence_must_begin_at_zero(self) -> None:
        with self.assertRaisesRegex(
            servercopy.ConfigError,
            r"found \.001 after missing \.000",
        ):
            servercopy.parse_numbered_suffixes("foo.001\n")

    def test_sequence_cannot_contain_a_gap(self) -> None:
        with self.assertRaisesRegex(
            servercopy.ConfigError,
            r"found \.003 after missing \.002",
        ):
            servercopy.parse_numbered_suffixes("foo.003\nfoo.000\nfoo.001\n")


class RecoveredMirrorTests(unittest.TestCase):
    def test_authoritative_suffix_tuple_is_hardcoded_in_required_order(self) -> None:
        self.assertEqual(
            servercopy.FIXED_SYNC_SUFFIXES,
            (".MER", ".LOG", ".BIN", ".cmd", ".out", ".vit", ".S41", ".S61"),
        )
        self.assertFalse(hasattr(servercopy, "SUFFIX_ALLOWLIST"))
        self.assertFalse(hasattr(servercopy, "load_suffix_globs"))

    def test_historical_mer_shape_is_repeated_in_stable_suffix_order(self) -> None:
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
                    'mirror "--verbose" "--continue" "--overwrite" "--no-perms" '
                    '"--no-empty-dirs" "--parallel=4" '
                    f'"--file={user}/*{suffix}" '
                    f'"--target-directory=/tmp/servers/{user}"'
                    for suffix in servercopy.FIXED_SYNC_SUFFIXES
                ]

                self.assertEqual(mirrors, expected)
                self.assertEqual(script.count("open -u "), 1)
                self.assertEqual(script.count("set cmd:fail-exit yes"), 1)
                self.assertEqual(script.count("bye"), 1)
                self.assertEqual(
                    mirrors[0],
                    'mirror "--verbose" "--continue" "--overwrite" "--no-perms" '
                    '"--no-empty-dirs" "--parallel=4" '
                    f'"--file={user}/*.MER" '
                    f'"--target-directory=/tmp/servers/{user}"',
                )
                self.assertNotIn("lcd ", script)
                self.assertNotIn('mirror "-c" "-f"', script)
                self.assertNotIn("include-glob", script)
                self.assertNotIn("exclude-glob", script)

                for suffix, command in zip(
                    servercopy.FIXED_SYNC_SUFFIXES, mirrors, strict=True
                ):
                    self.assertEqual(command.count(f'--file={user}/*{suffix}'), 1)
                    self.assertEqual(command.count(f'--target-directory=/tmp/servers/{user}'), 1)

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
                for suffix in servercopy.FIXED_SYNC_SUFFIXES
            ],
        )
        self.assertEqual(
            script.count('"--dry-run"'), len(servercopy.FIXED_SYNC_SUFFIXES)
        )

    def test_numbered_mirrors_follow_fixed_mirrors_in_order(self) -> None:
        script = servercopy.build_lftp_script(
            taal_source(),
            "fake-password",
            Path("/tmp/servers/eso"),
            False,
            (".000", ".001", ".002"),
        )
        mirrors = [line for line in script.splitlines() if line.startswith("mirror ")]

        self.assertEqual(len(mirrors), len(servercopy.FIXED_SYNC_SUFFIXES) + 3)
        self.assertIn('"--file=eso/*.S61"', mirrors[-4])
        for suffix, command in zip((".000", ".001", ".002"), mirrors[-3:], strict=True):
            self.assertEqual(
                command,
                'mirror "--verbose" "--continue" "--overwrite" "--no-perms" '
                '"--no-empty-dirs" "--parallel=4" '
                f'"--file=eso/*{suffix}" '
                '"--target-directory=/tmp/servers/eso"',
            )

    def test_numbered_mirrors_keep_common_options_and_dry_run(self) -> None:
        script = servercopy.build_lftp_script(
            taal_source(),
            "fake-password",
            Path("/tmp/servers/eso"),
            True,
            (".000", ".001"),
        )
        numbered = [
            line
            for line in script.splitlines()
            if line.startswith("mirror ") and ("/*.000" in line or "/*.001" in line)
        ]

        self.assertEqual(len(numbered), 2)
        for command in numbered:
            for option in servercopy.COMMON_OPTIONS:
                self.assertIn(f'"{option}"', command)
            self.assertIn('"--dry-run"', command)
            self.assertIn('"--target-directory=/tmp/servers/eso"', command)


class NumberedSuffixDiscoveryTests(unittest.TestCase):
    def test_discovery_uses_cls_not_mirror_for_each_protocol(self) -> None:
        for source in (taal_source(), rudics_source()):
            with self.subTest(protocol=source.protocol):
                script = servercopy.build_discovery_lftp_script(source, "fake-password")

                self.assertIn("set cmd:fail-exit yes", script)
                self.assertIn("set cmd:trace no", script)
                self.assertIn("set net:timeout 30s", script)
                self.assertIn("set net:max-retries 2", script)
                self.assertIn("set xfer:timeout 5m", script)
                self.assertIn("cls -1 ", script)
                self.assertIn('set cmd:cls-default ""', script)
                self.assertNotIn("mirror ", script)

    def test_discovery_preserves_ftps_protected_listing_settings(self) -> None:
        script = servercopy.build_discovery_lftp_script(
            taal_source(), "fake-password"
        )

        self.assertIn("set ftp:ssl-force yes", script)
        self.assertIn("set ftp:ssl-protect-data yes", script)
        self.assertIn("set ftp:ssl-protect-list yes", script)
        self.assertIn("set ssl:verify-certificate yes", script)
        self.assertIn('cls -1 "eso/"', script)

    def test_discovery_returns_suffixes_without_printing_inventory(self) -> None:
        report = MagicMock()
        with patch.object(
            servercopy,
            "run_lftp",
            return_value=(0, ["foo.001", "bar.000", "baz.001"]),
        ) as run_lftp:
            suffixes = servercopy.discover_remote_numbered_suffixes(
                "/mock/lftp",
                rudics_source(),
                "fake-password",
                report,
                "dry-run",
            )

        self.assertEqual(suffixes, (".000", ".001"))
        self.assertTrue(run_lftp.call_args.kwargs["stream_output"] is False)
        messages = [call.args[0] for call in report.write.call_args_list]
        self.assertEqual(
            messages,
            [
                "[servercopy] step=discover-numbered-suffixes",
                "[servercopy] discovered-numbered-suffixes=.000,.001",
            ],
        )
        self.assertNotIn("foo.001", messages)

    def test_empty_discovery_reports_none(self) -> None:
        report = MagicMock()
        with patch.object(servercopy, "run_lftp", return_value=(0, ["foo.MER"])):
            suffixes = servercopy.discover_remote_numbered_suffixes(
                "/mock/lftp", taal_source(), "fake-password", report, "sync"
            )

        self.assertEqual(suffixes, ())
        report.write.assert_any_call("[servercopy] discovered-numbered-suffixes=none")

    def test_discovery_failure_is_identified(self) -> None:
        with patch.object(
            servercopy,
            "run_lftp",
            return_value=(1, ["cls: Access failed"]),
        ):
            with self.assertRaisesRegex(
                servercopy.ConfigError,
                "numbered suffix discovery failed",
            ):
                servercopy.discover_remote_numbered_suffixes(
                    "/mock/lftp",
                    taal_source(),
                    "fake-password",
                    MagicMock(),
                    "sync",
                )


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
                "sync",
                "eso",
                heartbeat_seconds=0.01,
                silence_timeout_seconds=0.02,
            )

        self.assertEqual(code, 124)
        self.assertIn("lftp timed out", lines[-1])
        process.terminate.assert_called_once_with()

    def test_lftp_output_redacts_url_credentials(self) -> None:
        output = "get ftp://example-user:pa@ss@example.test/file"

        redacted = servercopy.redact_lftp_output(output)

        self.assertEqual(redacted, "get ftp://[REDACTED]@example.test/file")

    def test_discovery_credentials_are_absent_from_argv_output_and_errors(self) -> None:
        password = "fake-secret-password"
        process = MagicMock()
        process.stdout.readline.side_effect = [
            f"open: Access failed: ftp://automaid:{password}@taal.example/\n".encode(),
            b"",
        ]
        process.wait.return_value = 1
        report = MagicMock()

        with patch.object(servercopy.subprocess, "Popen", return_value=process) as popen:
            with self.assertRaises(servercopy.ConfigError) as raised:
                servercopy.discover_remote_numbered_suffixes(
                    "lftp", taal_source(), password, report, "sync"
                )

        self.assertEqual(popen.call_args.args, (["lftp"],))
        self.assertNotIn(password, str(raised.exception))
        self.assertNotIn(
            password,
            "\n".join(call.args[0] for call in report.write.call_args_list),
        )
        self.assertIn(b'"fake-secret-password"', process.stdin.write.call_args.args[0])


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


class WorkflowTests(unittest.TestCase):
    def test_sftp_source_discovers_then_receives_numbered_mirror_suffixes(self) -> None:
        source = rudics_source()
        args = servercopy.parse_args(
            ["--dry-run", "--user", source.user, "--output", "/tmp/servercopy-test"]
        )
        report = MagicMock()

        with (
            patch.object(servercopy.shutil, "which", return_value="/mock/lftp"),
            patch.object(servercopy, "load_sources", return_value=[source]),
            patch.object(
                servercopy, "load_credentials", return_value={source.login: "fake-password"}
            ),
            patch.object(
                servercopy,
                "discover_remote_numbered_suffixes",
                return_value=(".000", ".001"),
            ) as discover,
            patch.object(servercopy, "run_lftp", return_value=(0, [])) as run_lftp,
            patch.dict(servercopy.os.environ, {}, clear=True),
        ):
            code = servercopy.run_workflow(args, Path("/unused"), report)

        self.assertEqual(code, 0)
        discover.assert_called_once_with(
            "/mock/lftp", source, "fake-password", report, "dry-run"
        )
        mirror_script = run_lftp.call_args.args[1]
        self.assertLess(mirror_script.index("suffix=.S61"), mirror_script.index("suffix=.000"))
        self.assertLess(mirror_script.index("suffix=.000"), mirror_script.index("suffix=.001"))
        self.assertEqual(
            mirror_script.count('"--dry-run"'),
            len(servercopy.FIXED_SYNC_SUFFIXES) + 2,
        )

    def test_check_performs_no_discovery_or_remote_execution(self) -> None:
        source = rudics_source()
        args = servercopy.parse_args(
            ["--check", "--user", source.user, "--output", "/tmp/servercopy-check"]
        )

        with (
            patch.object(servercopy.shutil, "which", return_value="/mock/lftp"),
            patch.object(servercopy, "load_sources", return_value=[source]),
            patch.object(
                servercopy, "load_credentials", return_value={source.login: "fake-password"}
            ),
            patch.object(servercopy, "discover_remote_numbered_suffixes") as discover,
            patch.object(servercopy, "run_lftp") as run_lftp,
            patch.dict(servercopy.os.environ, {}, clear=True),
        ):
            code = servercopy.run_workflow(args, Path("/unused"), MagicMock())

        self.assertEqual(code, 0)
        discover.assert_not_called()
        run_lftp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
