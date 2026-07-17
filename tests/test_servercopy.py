"""Focused tests for servercopy lftp command generation."""

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "servercopy"
LOADER = SourceFileLoader("servercopy_module", str(SCRIPT))
SPEC = spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
servercopy = module_from_spec(SPEC)
sys.modules[LOADER.name] = servercopy
LOADER.exec_module(servercopy)


class LftpCommandTests(unittest.TestCase):
    def test_lftp_output_replaces_invalid_text_bytes(self) -> None:
        completed = servercopy.subprocess.CompletedProcess(["lftp"], 0, "bad:\ufffd")

        with patch.object(servercopy.subprocess, "run", return_value=completed) as run:
            code, output = servercopy.run_lftp("lftp", "bye\n")

        self.assertEqual((code, output), (0, "bad:\ufffd"))
        self.assertEqual(run.call_args.kwargs["errors"], "replace")

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

    def test_rudics_broad_preview_preserves_current_policy(self) -> None:
        source = servercopy.Source(
            "s_m0057",
            "s_m0057",
            "sftp",
            "rudics.thorium.cls.fr",
            22,
            ".",
            "rudics-broad",
        )

        script = servercopy.build_lftp_script(
            source, "fake-password", Path("/tmp/servers/s_m0057"), True
        )

        self.assertIn('open -u "s_m0057","fake-password"', script)
        self.assertIn('"sftp://rudics.thorium.cls.fr:22"', script)
        self.assertIn('"--dry-run"', script)
        self.assertIn('"--continue"', script)
        self.assertIn('"--no-perms"', script)
        self.assertIn('"--exclude-glob=backups/*"', script)
        self.assertIn('"--exclude-glob=*~"', script)
        self.assertEqual(script.count("mirror "), 1)

    def test_taal_preview_uses_explicit_ftps_and_selected_extensions(self) -> None:
        source = servercopy.Source(
            "eso",
            "automaid",
            "ftps-explicit",
            "taal.unice.fr",
            21,
            "eso/",
            "mermaid-selected",
        )

        script = servercopy.build_lftp_script(
            source, "fake-password", Path("/tmp/servers/eso"), True
        )

        self.assertIn("set ftp:ssl-force yes", script)
        self.assertIn("set ssl:verify-certificate yes", script)
        self.assertIn('"ftp://taal.unice.fr:21"', script)
        self.assertEqual(script.count("mirror "), 6)
        for extension in servercopy.MERMAID_EXTENSIONS:
            self.assertIn(f'"--file=eso/*{extension}"', script)
        self.assertIn('"--target-directory=/tmp/servers/eso"', script)


if __name__ == "__main__":
    unittest.main()
