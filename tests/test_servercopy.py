"""Focused tests for servercopy lftp command generation."""

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


class LftpCommandTests(unittest.TestCase):
    def test_lftp_output_replaces_invalid_text_bytes(self) -> None:
        process = MagicMock()
        process.stdout.readline.side_effect = [b"bad:\xff\n", b""]
        process.wait.return_value = 0
        report = MagicMock()

        with patch.object(servercopy.subprocess, "Popen", return_value=process) as popen:
            code, lines = servercopy.run_lftp(
                "lftp", "bye\n", report, "sync", "kobeuni", heartbeat_seconds=1
            )

        self.assertEqual((code, lines), (0, ["bad:\ufffd"]))
        report.write.assert_called_once_with("bad:\ufffd")
        process.stdin.write.assert_called_once_with(b"bye\n")
        process.stdin.close.assert_called_once_with()
        self.assertEqual(popen.call_args.args, (["lftp"],))
        self.assertNotIn("text", popen.call_args.kwargs)

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
                "lftp", "bye\n", report, "sync", "kobeuni", heartbeat_seconds=0.01
            )

        self.assertEqual((code, lines), (0, []))
        messages = [call.args[0] for call in report.write.call_args_list]
        self.assertTrue(
            any(message.startswith("[sync] still-running user=kobeuni") for message in messages)
        )

    def test_lftp_output_redacts_url_credentials(self) -> None:
        output = "get sftp://example-user:fake-password@example.test/file"

        redacted = servercopy.redact_lftp_output(output)

        self.assertEqual(redacted, "get sftp://[REDACTED]@example.test/file")
        self.assertNotIn("fake-password", redacted)

    def test_output_default_and_override(self) -> None:
        default = servercopy.parse_args([])
        overridden = servercopy.parse_args(["--output", "~/alternate-servers"])

        self.assertEqual(default.output, Path.home() / "mermaid" / "servers")
        self.assertEqual(overridden.output.expanduser(), Path.home() / "alternate-servers")

    def test_source_registry_uses_endpoint_fields_only(self) -> None:
        sources = servercopy.load_sources(SCRIPT.with_name("servercopy_sources.csv"))

        self.assertEqual(len(sources), 20)
        self.assertEqual(sources[-1].user, "kobeuni")
        self.assertFalse(hasattr(sources[-1], "policy"))

    def test_rudics_preview_uses_shared_suffix_allowlist(self) -> None:
        source = servercopy.Source(
            "s_m0057",
            "s_m0057",
            "sftp",
            "rudics.thorium.cls.fr",
            22,
            ".",
        )

        script = servercopy.build_lftp_script(
            source, "fake-password", Path("/tmp/servers/s_m0057"), True
        )

        self.assertIn('open -u "s_m0057","fake-password"', script)
        self.assertIn('"sftp://rudics.thorium.cls.fr:22"', script)
        self.assertIn('"--dry-run"', script)
        self.assertIn('"--continue"', script)
        self.assertIn('"--no-perms"', script)
        self.assertIn('"--file=./*.[0-9][0-9][0-9]"', script)
        self.assertIn('"--file=./*.MER"', script)
        self.assertNotIn('"--file=./*.cmd"', script)
        self.assertIn('echo "[servercopy] step=selected-files patterns=8"', script)
        self.assertEqual(script.count("mirror "), 1)

    def test_taal_preview_uses_explicit_ftps_and_shared_suffix_allowlist(self) -> None:
        source = servercopy.Source(
            "eso",
            "automaid",
            "ftps-explicit",
            "taal.unice.fr",
            21,
            "eso/",
        )

        script = servercopy.build_lftp_script(
            source, "fake-password", Path("/tmp/servers/eso"), True
        )

        self.assertIn("set ftp:ssl-force yes", script)
        self.assertIn("set ssl:verify-certificate yes", script)
        self.assertIn('"ftp://taal.unice.fr:21"', script)
        self.assertEqual(script.count("mirror "), 1)
        for suffix in servercopy.MIRROR_SUFFIX_GLOBS:
            self.assertIn(f'"--file=eso/*{suffix}"', script)
        self.assertIn('"--target-directory=/tmp/servers/eso"', script)

    def test_suffix_reference_matches_top_level_allowlist(self) -> None:
        reference = SCRIPT.parent / "data" / "filename_suffixes.txt"
        patterns = tuple(
            f".{line}"
            for line in reference.read_text(encoding="ascii").splitlines()
            if line
        )

        self.assertEqual(patterns, servercopy.MIRROR_SUFFIX_GLOBS)

    def test_failure_detail_keeps_diagnostics_not_transfer_chatter(self) -> None:
        detail = servercopy.lftp_failure_detail(
            1,
            [
                "Transferring file `one.MER'",
                "Transferring file `two.MER'",
                "mirror: two.MER: permission denied",
            ],
        )

        self.assertEqual(detail, "lftp exit status 1\nmirror: two.MER: permission denied")
        self.assertNotIn("Transferring", detail)


if __name__ == "__main__":
    unittest.main()
