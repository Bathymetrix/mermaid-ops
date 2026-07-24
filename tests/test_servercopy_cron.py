"""Focused offline tests for servercopy_cron."""

from contextlib import redirect_stderr, redirect_stdout
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from io import StringIO
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import call, patch


SCRIPT = Path(__file__).resolve().parents[1] / "servercopy_cron"
LOADER = SourceFileLoader("servercopy_cron_module", str(SCRIPT))
SPEC = spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
servercopy_cron = module_from_spec(SPEC)
sys.modules[LOADER.name] = servercopy_cron
LOADER.exec_module(servercopy_cron)


def git_result(
    returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        ["git"],
        returncode,
        stdout=stdout,
        stderr=stderr,
    )


class RecipientTests(unittest.TestCase):
    def test_recipient_parsing_ignores_blank_lines_comments_and_invalid_lines(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "recipients.txt"
            path.write_text(
                "\n# test recipients\n  +12065550101  \nnot-a-number\n"
                "   # another comment\n+442079460101\n",
                encoding="ascii",
            )

            self.assertEqual(
                servercopy_cron.load_recipients(path),
                ["+12065550101", "+442079460101"],
            )

    def test_notification_failure_does_not_print_recipient_values(self) -> None:
        recipient = "+12065550101"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "recipients.txt"
            path.write_text(f"{recipient}\n", encoding="ascii")
            error_output = StringIO()
            failed = subprocess.CompletedProcess(
                ["osascript"],
                1,
                stdout="",
                stderr=f"could not contact {recipient}",
            )

            with (
                patch.object(servercopy_cron.subprocess, "run", return_value=failed),
                redirect_stderr(error_output),
            ):
                servercopy_cron.send_failure_notifications(path, "safe message")

        self.assertIn("Messages notification failed", error_output.getvalue())
        self.assertNotIn(recipient, error_output.getvalue())


class SubprocessTests(unittest.TestCase):
    def test_servercopy_inherits_live_output_and_uses_mermaid_servers(self) -> None:
        completed = subprocess.CompletedProcess(["servercopy"], 0)

        with patch.object(
            servercopy_cron.subprocess, "run", return_value=completed
        ) as run:
            status = servercopy_cron.run_servercopy(
                Path("/repo/servercopy"),
                Path("/mermaid/servers"),
            )

        self.assertEqual(status, 0)
        run.assert_called_once_with(
            ["/repo/servercopy", "--output", "/mermaid/servers"],
            check=False,
        )


class WorkflowTests(unittest.TestCase):
    def test_failed_servercopy_notifies_and_performs_no_git_commands(self) -> None:
        recipient_path = Path("/repo/data/notification_recipients.txt")

        with (
            patch.object(servercopy_cron, "run_servercopy", return_value=17),
            patch.object(
                servercopy_cron, "send_failure_notifications"
            ) as notify,
            patch.object(servercopy_cron, "run_git") as run_git,
            patch.object(
                servercopy_cron.socket, "gethostname", return_value="test-host"
            ),
        ):
            status = servercopy_cron.run_cron_workflow(
                Path("/repo/servercopy"),
                Path("/mermaid/servers"),
                recipient_path,
            )

        self.assertEqual(status, 17)
        notify.assert_called_once_with(
            recipient_path,
            "servercopy failed on test-host. Partial downloads were left "
            "uncommitted. Check servercopy_cron.log.",
        )
        run_git.assert_not_called()

    def test_success_with_no_changes_exits_zero_without_committing(self) -> None:
        with TemporaryDirectory() as directory:
            servers = Path(directory) / "servers"
            responses = [
                git_result(0, f"{servers}\n"),
                git_result(0),
                git_result(0),
                git_result(0),
            ]
            output = StringIO()

            with (
                patch.object(servercopy_cron, "run_servercopy", return_value=0),
                patch.object(
                    servercopy_cron, "run_git", side_effect=responses
                ) as run_git,
                redirect_stdout(output),
            ):
                status = servercopy_cron.run_cron_workflow(
                    Path("/repo/servercopy"),
                    servers,
                    Path("/repo/data/notification_recipients.txt"),
                )

        self.assertEqual(status, 0)
        self.assertIn("no changes to commit", output.getvalue())
        self.assertEqual(
            run_git.call_args_list,
            [
                call(servers, "rev-parse", "--show-toplevel"),
                call(servers, "diff", "--cached", "--quiet", "--exit-code"),
                call(servers, "add", "-A"),
                call(servers, "diff", "--cached", "--quiet", "--exit-code"),
            ],
        )

    def test_success_with_changes_stages_and_commits(self) -> None:
        with TemporaryDirectory() as directory:
            servers = Path(directory) / "servers"
            responses = [
                git_result(0, f"{servers}\n"),
                git_result(0),
                git_result(0),
                git_result(1),
                git_result(0),
            ]

            with (
                patch.object(servercopy_cron, "run_servercopy", return_value=0),
                patch.object(
                    servercopy_cron, "run_git", side_effect=responses
                ) as run_git,
                patch.object(
                    servercopy_cron,
                    "utc_now",
                    return_value="2026-07-23T22:30:00Z",
                ),
                redirect_stdout(StringIO()),
            ):
                status = servercopy_cron.run_cron_workflow(
                    Path("/repo/servercopy"),
                    servers,
                    Path("/repo/data/notification_recipients.txt"),
                )

        self.assertEqual(status, 0)
        self.assertEqual(
            run_git.call_args_list[-3:],
            [
                call(servers, "add", "-A"),
                call(servers, "diff", "--cached", "--quiet", "--exit-code"),
                call(
                    servers,
                    "commit",
                    "-m",
                    "servercopy [cron]: 2026-07-23T22:30:00Z",
                ),
            ],
        )

    def test_preexisting_staged_changes_refuse_before_git_add(self) -> None:
        with TemporaryDirectory() as directory:
            servers = Path(directory) / "servers"
            responses = [
                git_result(0, f"{servers}\n"),
                git_result(1),
            ]
            error_output = StringIO()

            with (
                patch.object(servercopy_cron, "run_servercopy", return_value=0),
                patch.object(
                    servercopy_cron, "run_git", side_effect=responses
                ) as run_git,
                redirect_stderr(error_output),
            ):
                status = servercopy_cron.run_cron_workflow(
                    Path("/repo/servercopy"),
                    servers,
                    Path("/repo/data/notification_recipients.txt"),
                )

        self.assertNotEqual(status, 0)
        self.assertIn("already contains staged changes", error_output.getvalue())
        self.assertNotIn(call(servers, "add", "-A"), run_git.call_args_list)


class MainTests(unittest.TestCase):
    def test_version_is_available_without_mermaid(self) -> None:
        for option in ("-v", "--version"):
            with self.subTest(option=option):
                output = StringIO()
                with (
                    patch.dict(servercopy_cron.os.environ, {}, clear=True),
                    redirect_stdout(output),
                    self.assertRaises(SystemExit) as raised,
                ):
                    servercopy_cron.main([option])

                self.assertEqual(raised.exception.code, 0)
                self.assertEqual(output.getvalue(), "servercopy_cron 1.0.0\n")

    def test_missing_mermaid_fails_before_any_work(self) -> None:
        error_output = StringIO()

        with (
            patch.dict(servercopy_cron.os.environ, {}, clear=True),
            patch.object(servercopy_cron, "run_cron_workflow") as workflow,
            redirect_stderr(error_output),
        ):
            status = servercopy_cron.main([])

        self.assertNotEqual(status, 0)
        self.assertIn("MERMAID must be set", error_output.getvalue())
        workflow.assert_not_called()

    def test_overlapping_execution_is_refused_without_operational_actions(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            error_output = StringIO()

            with (
                patch.dict(
                    servercopy_cron.os.environ,
                    {"MERMAID": directory},
                    clear=True,
                ),
                patch.object(
                    servercopy_cron.fcntl,
                    "flock",
                    side_effect=BlockingIOError,
                ),
                patch.object(servercopy_cron, "run_cron_workflow") as workflow,
                patch.object(servercopy_cron, "run_servercopy") as run_servercopy,
                patch.object(servercopy_cron, "run_git") as run_git,
                patch.object(
                    servercopy_cron, "send_failure_notifications"
                ) as notify,
                redirect_stderr(error_output),
            ):
                status = servercopy_cron.main([])

        self.assertNotEqual(status, 0)
        self.assertIn("already running", error_output.getvalue())
        workflow.assert_not_called()
        run_servercopy.assert_not_called()
        run_git.assert_not_called()
        notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
