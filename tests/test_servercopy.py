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


class RecoveredMirrorTests(unittest.TestCase):
    def test_authoritative_suffix_tuple_is_hardcoded_in_required_order(self) -> None:
        self.assertEqual(
            servercopy.TAAL_SYNC_SUFFIXES,
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
                    for suffix in servercopy.TAAL_SYNC_SUFFIXES
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
                    servercopy.TAAL_SYNC_SUFFIXES, mirrors, strict=True
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
                for suffix in servercopy.TAAL_SYNC_SUFFIXES
            ],
        )
        self.assertEqual(
            script.count('"--dry-run"'), len(servercopy.TAAL_SYNC_SUFFIXES)
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


if __name__ == "__main__":
    unittest.main()
