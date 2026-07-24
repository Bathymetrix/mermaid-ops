"""Focused offline tests for servercopy_cron."""

from contextlib import redirect_stderr, redirect_stdout
from http.client import BadStatusLine
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from io import StringIO
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, call, patch
from urllib.error import URLError


SCRIPT = Path(__file__).resolve().parents[1] / "servercopy_cron"
LOADER = SourceFileLoader("servercopy_cron_module", str(SCRIPT))
SPEC = spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
servercopy_cron = module_from_spec(SPEC)
sys.modules[LOADER.name] = servercopy_cron
LOADER.exec_module(servercopy_cron)

CHECK_UUID = "11111111-2222-3333-4444-555555555555"


def git_result(
    returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        ["git"],
        returncode,
        stdout=stdout,
        stderr=stderr,
    )


class FakeResponse:
    def __init__(self, status: int = 200) -> None:
        self.status = status

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def getcode(self) -> int:
        return self.status

    def read(self) -> bytes:
        raise AssertionError("Healthchecks.io response bodies must not be read")


class HealthchecksUuidTests(unittest.TestCase):
    def test_valid_uuid_is_normalized(self) -> None:
        configured = "AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "healthchecks_uuid.txt"
            path.write_text(f"  {configured}  \n", encoding="ascii")

            loaded = servercopy_cron.load_healthchecks_uuid(path)

        self.assertEqual(loaded, configured.lower())

    def test_blank_lines_and_comments_are_ignored(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "healthchecks_uuid.txt"
            path.write_text(
                f"\n  # private check UUID\n\n  {CHECK_UUID}  \n"
                "   # trailing comment line\n",
                encoding="ascii",
            )

            loaded = servercopy_cron.load_healthchecks_uuid(path)

        self.assertEqual(loaded, CHECK_UUID)

    def test_absent_uuid_file_fails(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "missing-healthchecks-uuid.txt"

            with self.assertRaises(FileNotFoundError):
                servercopy_cron.load_healthchecks_uuid(path)

    def test_empty_or_comment_only_uuid_file_fails(self) -> None:
        for contents in ("", "\n  \n", "# comment only\n   # another\n"):
            with self.subTest(contents=contents):
                with TemporaryDirectory() as directory:
                    path = Path(directory) / "healthchecks_uuid.txt"
                    path.write_text(contents, encoding="ascii")

                    with self.assertRaises(
                        servercopy_cron.HealthchecksConfigError
                    ) as raised:
                        servercopy_cron.load_healthchecks_uuid(path)

                self.assertIn("no check UUID", str(raised.exception))

    def test_malformed_uuid_and_internal_whitespace_fail_secret_safely(self) -> None:
        invalid_values = (
            "private-invalid-uuid-value",
            "11111111-2222-3333-4444-55555555 5555",
        )
        for configured in invalid_values:
            with self.subTest(configured=configured):
                with TemporaryDirectory() as directory:
                    path = Path(directory) / "healthchecks_uuid.txt"
                    path.write_text(f"{configured}\n", encoding="ascii")

                    with self.assertRaises(
                        servercopy_cron.HealthchecksConfigError
                    ) as raised:
                        servercopy_cron.load_healthchecks_uuid(path)

                self.assertNotIn(configured, str(raised.exception))

    def test_multiple_values_fail_without_exposing_either_uuid(self) -> None:
        other_uuid = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "healthchecks_uuid.txt"
            path.write_text(
                f"{CHECK_UUID}\n{other_uuid}\n",
                encoding="ascii",
            )

            with self.assertRaises(
                servercopy_cron.HealthchecksConfigError
            ) as raised:
                servercopy_cron.load_healthchecks_uuid(path)

        error = str(raised.exception)
        self.assertIn("multiple values", error)
        self.assertNotIn(CHECK_UUID, error)
        self.assertNotIn(other_uuid, error)


class HealthchecksHttpTests(unittest.TestCase):
    def test_lifecycle_pings_use_exact_empty_post_requests(self) -> None:
        requests: list[tuple[object, int]] = []

        def capture_request(request: object, *, timeout: int) -> FakeResponse:
            requests.append((request, timeout))
            return FakeResponse()

        with patch.object(
            servercopy_cron,
            "urlopen",
            side_effect=capture_request,
        ) as urlopen:
            servercopy_cron.ping_start(CHECK_UUID)
            servercopy_cron.ping_success(CHECK_UUID)
            servercopy_cron.ping_failure(CHECK_UUID)

        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual(
            [request.full_url for request, _ in requests],
            [
                f"https://hc-ping.com/{CHECK_UUID}/start",
                f"https://hc-ping.com/{CHECK_UUID}",
                f"https://hc-ping.com/{CHECK_UUID}/fail",
            ],
        )
        self.assertEqual(
            [request.get_method() for request, _ in requests],
            ["POST", "POST", "POST"],
        )
        self.assertEqual([request.data for request, _ in requests], [b"", b"", b""])
        self.assertEqual([timeout for _, timeout in requests], [15, 15, 15])

    def test_non_success_response_fails_without_reading_body(self) -> None:
        with (
            patch.object(
                servercopy_cron,
                "urlopen",
                return_value=FakeResponse(status=503),
            ) as urlopen,
            self.assertRaises(servercopy_cron.HealthchecksPingError),
        ):
            servercopy_cron.ping_start(CHECK_UUID)

        urlopen.assert_called_once()

    def test_request_exceptions_do_not_expose_private_uuid(self) -> None:
        request_errors = (
            URLError(f"could not reach https://hc-ping.com/{CHECK_UUID}/start"),
            BadStatusLine(f"invalid response containing {CHECK_UUID}"),
        )
        for request_error in request_errors:
            with self.subTest(error_type=type(request_error).__name__):
                with (
                    patch.object(
                        servercopy_cron,
                        "urlopen",
                        side_effect=request_error,
                    ) as urlopen,
                    self.assertRaises(
                        servercopy_cron.HealthchecksPingError
                    ) as raised,
                ):
                    servercopy_cron.ping_start(CHECK_UUID)

                self.assertNotIn(CHECK_UUID, str(raised.exception))
                urlopen.assert_called_once()


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
    def test_start_failure_prevents_servercopy_and_git(self) -> None:
        error_output = StringIO()

        with (
            patch.object(
                servercopy_cron,
                "ping_start",
                side_effect=servercopy_cron.HealthchecksPingError,
            ) as ping_start,
            patch.object(servercopy_cron, "run_servercopy") as run_servercopy,
            patch.object(
                servercopy_cron, "commit_synced_changes"
            ) as commit_changes,
            patch.object(servercopy_cron, "ping_failure") as ping_failure,
            patch.object(servercopy_cron, "ping_success") as ping_success,
            redirect_stderr(error_output),
        ):
            status = servercopy_cron.run_cron_workflow(
                Path("/repo/servercopy"),
                Path("/mermaid/servers"),
                CHECK_UUID,
            )

        self.assertNotEqual(status, 0)
        self.assertIn("start ping failed", error_output.getvalue())
        self.assertNotIn(CHECK_UUID, error_output.getvalue())
        ping_start.assert_called_once_with(CHECK_UUID)
        run_servercopy.assert_not_called()
        commit_changes.assert_not_called()
        ping_failure.assert_not_called()
        ping_success.assert_not_called()

    def test_failed_servercopy_sends_failure_and_performs_no_git_commands(
        self,
    ) -> None:
        lifecycle = Mock()
        start = Mock()
        run_servercopy = Mock(return_value=17)
        failure = Mock()
        lifecycle.attach_mock(start, "start")
        lifecycle.attach_mock(run_servercopy, "servercopy")
        lifecycle.attach_mock(failure, "failure")

        with (
            patch.object(servercopy_cron, "ping_start", start),
            patch.object(servercopy_cron, "run_servercopy", run_servercopy),
            patch.object(servercopy_cron, "ping_failure", failure),
            patch.object(servercopy_cron, "run_git") as run_git,
            patch.object(servercopy_cron, "ping_success") as ping_success,
        ):
            status = servercopy_cron.run_cron_workflow(
                Path("/repo/servercopy"),
                Path("/mermaid/servers"),
                CHECK_UUID,
            )

        self.assertEqual(status, 17)
        self.assertEqual(
            lifecycle.mock_calls,
            [
                call.start(CHECK_UUID),
                call.servercopy(
                    Path("/repo/servercopy"),
                    Path("/mermaid/servers"),
                ),
                call.failure(CHECK_UUID),
            ],
        )
        run_git.assert_not_called()
        ping_success.assert_not_called()

    def test_failure_ping_failure_preserves_servercopy_status(self) -> None:
        error_output = StringIO()

        with (
            patch.object(servercopy_cron, "ping_start"),
            patch.object(servercopy_cron, "run_servercopy", return_value=17),
            patch.object(
                servercopy_cron,
                "ping_failure",
                side_effect=servercopy_cron.HealthchecksPingError,
            ) as ping_failure,
            patch.object(servercopy_cron, "run_git") as run_git,
            redirect_stderr(error_output),
        ):
            status = servercopy_cron.run_cron_workflow(
                Path("/repo/servercopy"),
                Path("/mermaid/servers"),
                CHECK_UUID,
            )

        self.assertEqual(status, 17)
        self.assertIn("failure ping also failed", error_output.getvalue())
        self.assertNotIn(CHECK_UUID, error_output.getvalue())
        ping_failure.assert_called_once_with(CHECK_UUID)
        run_git.assert_not_called()

    def test_preexisting_staged_changes_send_failure_before_git_add(self) -> None:
        with TemporaryDirectory() as directory:
            servers = Path(directory) / "servers"
            responses = [
                git_result(0, f"{servers}\n"),
                git_result(1),
            ]
            error_output = StringIO()

            with (
                patch.object(servercopy_cron, "ping_start"),
                patch.object(servercopy_cron, "run_servercopy", return_value=0),
                patch.object(
                    servercopy_cron,
                    "run_git",
                    side_effect=responses,
                ) as run_git,
                patch.object(servercopy_cron, "ping_failure") as ping_failure,
                patch.object(servercopy_cron, "ping_success") as ping_success,
                redirect_stderr(error_output),
            ):
                status = servercopy_cron.run_cron_workflow(
                    Path("/repo/servercopy"),
                    servers,
                    CHECK_UUID,
                )

        self.assertNotEqual(status, 0)
        self.assertIn("already contains staged changes", error_output.getvalue())
        self.assertNotIn(call(servers, "add", "-A"), run_git.call_args_list)
        ping_failure.assert_called_once_with(CHECK_UUID)
        ping_success.assert_not_called()

    def test_exact_git_root_verification_failure_sends_failure(self) -> None:
        with TemporaryDirectory() as directory:
            parent = Path(directory)
            servers = parent / "servers"

            with (
                patch.object(servercopy_cron, "ping_start"),
                patch.object(servercopy_cron, "run_servercopy", return_value=0),
                patch.object(
                    servercopy_cron,
                    "run_git",
                    return_value=git_result(0, f"{parent}\n"),
                ) as run_git,
                patch.object(servercopy_cron, "ping_failure") as ping_failure,
                patch.object(servercopy_cron, "ping_success") as ping_success,
                redirect_stderr(StringIO()),
            ):
                status = servercopy_cron.run_cron_workflow(
                    Path("/repo/servercopy"),
                    servers,
                    CHECK_UUID,
                )

        self.assertNotEqual(status, 0)
        run_git.assert_called_once_with(servers, "rev-parse", "--show-toplevel")
        ping_failure.assert_called_once_with(CHECK_UUID)
        ping_success.assert_not_called()

    def test_git_status_inspection_failure_sends_failure(self) -> None:
        with TemporaryDirectory() as directory:
            servers = Path(directory) / "servers"
            responses = [
                git_result(0, f"{servers}\n"),
                git_result(2),
            ]

            with (
                patch.object(servercopy_cron, "ping_start"),
                patch.object(servercopy_cron, "run_servercopy", return_value=0),
                patch.object(servercopy_cron, "run_git", side_effect=responses),
                patch.object(servercopy_cron, "ping_failure") as ping_failure,
                patch.object(servercopy_cron, "ping_success") as ping_success,
                redirect_stderr(StringIO()),
            ):
                status = servercopy_cron.run_cron_workflow(
                    Path("/repo/servercopy"),
                    servers,
                    CHECK_UUID,
                )

        self.assertNotEqual(status, 0)
        ping_failure.assert_called_once_with(CHECK_UUID)
        ping_success.assert_not_called()

    def test_git_staging_failure_sends_failure(self) -> None:
        with TemporaryDirectory() as directory:
            servers = Path(directory) / "servers"
            responses = [
                git_result(0, f"{servers}\n"),
                git_result(0),
                git_result(5),
            ]

            with (
                patch.object(servercopy_cron, "ping_start"),
                patch.object(servercopy_cron, "run_servercopy", return_value=0),
                patch.object(
                    servercopy_cron,
                    "run_git",
                    side_effect=responses,
                ) as run_git,
                patch.object(servercopy_cron, "ping_failure") as ping_failure,
                patch.object(servercopy_cron, "ping_success") as ping_success,
                redirect_stderr(StringIO()),
            ):
                status = servercopy_cron.run_cron_workflow(
                    Path("/repo/servercopy"),
                    servers,
                    CHECK_UUID,
                )

        self.assertNotEqual(status, 0)
        self.assertEqual(run_git.call_args_list[-1], call(servers, "add", "-A"))
        ping_failure.assert_called_once_with(CHECK_UUID)
        ping_success.assert_not_called()

    def test_git_commit_failure_sends_failure(self) -> None:
        with TemporaryDirectory() as directory:
            servers = Path(directory) / "servers"
            responses = iter(
                [
                    git_result(0, f"{servers}\n"),
                    git_result(0),
                    git_result(0),
                    git_result(1),
                    git_result(7),
                ]
            )
            events: list[str] = []

            def record_git(repository: Path, *arguments: str) -> object:
                events.append(f"git {' '.join(arguments)}")
                return next(responses)

            with (
                patch.object(servercopy_cron, "ping_start"),
                patch.object(servercopy_cron, "run_servercopy", return_value=0),
                patch.object(servercopy_cron, "run_git", side_effect=record_git),
                patch.object(
                    servercopy_cron,
                    "utc_now",
                    return_value="2026-07-23T22:30:00Z",
                ),
                patch.object(
                    servercopy_cron,
                    "ping_failure",
                    side_effect=lambda uuid: events.append("failure"),
                ) as ping_failure,
                patch.object(servercopy_cron, "ping_success") as ping_success,
                redirect_stderr(StringIO()),
            ):
                status = servercopy_cron.run_cron_workflow(
                    Path("/repo/servercopy"),
                    servers,
                    CHECK_UUID,
                )

        self.assertNotEqual(status, 0)
        self.assertEqual(
            events[-2:],
            [
                "git commit -m servercopy [cron]: 2026-07-23T22:30:00Z",
                "failure",
            ],
        )
        ping_failure.assert_called_once_with(CHECK_UUID)
        ping_success.assert_not_called()

    def test_success_with_no_changes_sends_success_without_committing(self) -> None:
        with TemporaryDirectory() as directory:
            servers = Path(directory) / "servers"
            responses = iter(
                [
                    git_result(0, f"{servers}\n"),
                    git_result(0),
                    git_result(0),
                    git_result(0),
                ]
            )
            events: list[str] = []

            def record_git(repository: Path, *arguments: str) -> object:
                events.append(f"git {' '.join(arguments)}")
                return next(responses)

            with (
                patch.object(
                    servercopy_cron,
                    "ping_start",
                    side_effect=lambda uuid: events.append("start"),
                ),
                patch.object(
                    servercopy_cron,
                    "run_servercopy",
                    side_effect=lambda command, repository: events.append(
                        "servercopy"
                    )
                    or 0,
                ),
                patch.object(
                    servercopy_cron,
                    "run_git",
                    side_effect=record_git,
                ),
                patch.object(
                    servercopy_cron,
                    "ping_success",
                    side_effect=lambda uuid: events.append("success"),
                ) as ping_success,
                patch.object(servercopy_cron, "ping_failure") as ping_failure,
                redirect_stdout(StringIO()),
            ):
                status = servercopy_cron.run_cron_workflow(
                    Path("/repo/servercopy"),
                    servers,
                    CHECK_UUID,
                )

        self.assertEqual(status, 0)
        self.assertEqual(
            events,
            [
                "start",
                "servercopy",
                "git rev-parse --show-toplevel",
                "git diff --cached --quiet --exit-code",
                "git add -A",
                "git diff --cached --quiet --exit-code",
                "success",
            ],
        )
        ping_success.assert_called_once_with(CHECK_UUID)
        ping_failure.assert_not_called()

    def test_success_with_changes_commits_before_success_ping(self) -> None:
        with TemporaryDirectory() as directory:
            servers = Path(directory) / "servers"
            responses = iter(
                [
                    git_result(0, f"{servers}\n"),
                    git_result(0),
                    git_result(0),
                    git_result(1),
                    git_result(0),
                ]
            )
            events: list[str] = []

            def record_git(repository: Path, *arguments: str) -> object:
                events.append(f"git {' '.join(arguments)}")
                return next(responses)

            with (
                patch.object(
                    servercopy_cron,
                    "ping_start",
                    side_effect=lambda uuid: events.append("start"),
                ),
                patch.object(
                    servercopy_cron,
                    "run_servercopy",
                    side_effect=lambda command, repository: events.append(
                        "servercopy"
                    )
                    or 0,
                ),
                patch.object(servercopy_cron, "run_git", side_effect=record_git),
                patch.object(
                    servercopy_cron,
                    "utc_now",
                    return_value="2026-07-23T22:30:00Z",
                ),
                patch.object(
                    servercopy_cron,
                    "ping_success",
                    side_effect=lambda uuid: events.append("success"),
                ),
                patch.object(servercopy_cron, "ping_failure") as ping_failure,
                redirect_stdout(StringIO()),
            ):
                status = servercopy_cron.run_cron_workflow(
                    Path("/repo/servercopy"),
                    servers,
                    CHECK_UUID,
                )

        self.assertEqual(status, 0)
        self.assertEqual(
            events[-2:],
            [
                "git commit -m servercopy [cron]: 2026-07-23T22:30:00Z",
                "success",
            ],
        )
        ping_failure.assert_not_called()

    def test_success_ping_failure_exits_nonzero_without_undoing_commit(self) -> None:
        with TemporaryDirectory() as directory:
            servers = Path(directory) / "servers"
            responses = [
                git_result(0, f"{servers}\n"),
                git_result(0),
                git_result(0),
                git_result(1),
                git_result(0),
            ]
            error_output = StringIO()

            with (
                patch.object(servercopy_cron, "ping_start"),
                patch.object(servercopy_cron, "run_servercopy", return_value=0),
                patch.object(
                    servercopy_cron,
                    "run_git",
                    side_effect=responses,
                ) as run_git,
                patch.object(
                    servercopy_cron,
                    "utc_now",
                    return_value="2026-07-23T22:30:00Z",
                ),
                patch.object(
                    servercopy_cron,
                    "ping_success",
                    side_effect=servercopy_cron.HealthchecksPingError,
                ) as ping_success,
                patch.object(servercopy_cron, "ping_failure") as ping_failure,
                redirect_stdout(StringIO()),
                redirect_stderr(error_output),
            ):
                status = servercopy_cron.run_cron_workflow(
                    Path("/repo/servercopy"),
                    servers,
                    CHECK_UUID,
                )

        self.assertNotEqual(status, 0)
        self.assertIn("success ping failed", error_output.getvalue())
        self.assertNotIn(CHECK_UUID, error_output.getvalue())
        self.assertEqual(
            run_git.call_args_list[-1],
            call(
                servers,
                "commit",
                "-m",
                "servercopy [cron]: 2026-07-23T22:30:00Z",
            ),
        )
        ping_success.assert_called_once_with(CHECK_UUID)
        ping_failure.assert_not_called()


class MainTests(unittest.TestCase):
    def test_version_is_available_without_mermaid_or_monitoring_config(self) -> None:
        for option in ("-v", "--version"):
            with self.subTest(option=option):
                output = StringIO()
                with (
                    patch.dict(servercopy_cron.os.environ, {}, clear=True),
                    patch.object(
                        servercopy_cron,
                        "load_healthchecks_uuid",
                    ) as load_uuid,
                    redirect_stdout(output),
                    self.assertRaises(SystemExit) as raised,
                ):
                    servercopy_cron.main([option])

                self.assertEqual(raised.exception.code, 0)
                self.assertEqual(output.getvalue(), "servercopy_cron 2.0.0\n")
                load_uuid.assert_not_called()

    def test_missing_mermaid_fails_before_any_work(self) -> None:
        error_output = StringIO()

        with (
            patch.dict(servercopy_cron.os.environ, {}, clear=True),
            patch.object(
                servercopy_cron,
                "load_healthchecks_uuid",
            ) as load_uuid,
            patch.object(servercopy_cron, "run_cron_workflow") as workflow,
            redirect_stderr(error_output),
        ):
            status = servercopy_cron.main([])

        self.assertNotEqual(status, 0)
        self.assertIn("MERMAID must be set", error_output.getvalue())
        load_uuid.assert_not_called()
        workflow.assert_not_called()

    def test_overlapping_execution_sends_no_healthcheck_requests_or_work(
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
                patch.object(
                    servercopy_cron,
                    "load_healthchecks_uuid",
                ) as load_uuid,
                patch.object(servercopy_cron, "run_cron_workflow") as workflow,
                patch.object(servercopy_cron, "run_servercopy") as run_servercopy,
                patch.object(servercopy_cron, "run_git") as run_git,
                patch.object(servercopy_cron, "urlopen") as urlopen,
                redirect_stderr(error_output),
            ):
                status = servercopy_cron.main([])

        self.assertNotEqual(status, 0)
        self.assertIn("already running", error_output.getvalue())
        load_uuid.assert_not_called()
        workflow.assert_not_called()
        run_servercopy.assert_not_called()
        run_git.assert_not_called()
        urlopen.assert_not_called()

    def test_absent_uuid_file_fails_before_servercopy_git_or_ping(self) -> None:
        with TemporaryDirectory() as directory:
            error_output = StringIO()

            with (
                patch.dict(
                    servercopy_cron.os.environ,
                    {"MERMAID": directory},
                    clear=True,
                ),
                patch.object(
                    servercopy_cron,
                    "load_healthchecks_uuid",
                    side_effect=FileNotFoundError,
                ) as load_uuid,
                patch.object(servercopy_cron, "run_cron_workflow") as workflow,
                patch.object(servercopy_cron, "run_servercopy") as run_servercopy,
                patch.object(servercopy_cron, "run_git") as run_git,
                patch.object(servercopy_cron, "urlopen") as urlopen,
                redirect_stderr(error_output),
            ):
                status = servercopy_cron.main([])

        self.assertNotEqual(status, 0)
        self.assertIn("UUID file could not be read", error_output.getvalue())
        load_uuid.assert_called_once()
        workflow.assert_not_called()
        run_servercopy.assert_not_called()
        run_git.assert_not_called()
        urlopen.assert_not_called()

    def test_invalid_uuid_file_fails_without_exposing_uuid_or_starting_work(
        self,
    ) -> None:
        private_value = "private-malformed-healthchecks-value"
        error_output = StringIO()

        with TemporaryDirectory() as directory:
            uuid_path = Path(directory) / "invalid-healthchecks-uuid.txt"
            uuid_path.write_text(f"{private_value}\n", encoding="ascii")
            load_healthchecks_uuid = servercopy_cron.load_healthchecks_uuid

            def load_invalid_uuid(_path: Path) -> str:
                return load_healthchecks_uuid(uuid_path)

            with (
                patch.dict(
                    servercopy_cron.os.environ,
                    {"MERMAID": directory},
                    clear=True,
                ),
                patch.object(
                    servercopy_cron,
                    "load_healthchecks_uuid",
                    side_effect=load_invalid_uuid,
                ),
                patch.object(servercopy_cron, "run_cron_workflow") as workflow,
                patch.object(servercopy_cron, "run_servercopy") as run_servercopy,
                patch.object(servercopy_cron, "run_git") as run_git,
                patch.object(servercopy_cron, "urlopen") as urlopen,
                redirect_stderr(error_output),
            ):
                status = servercopy_cron.main([])

        self.assertNotEqual(status, 0)
        self.assertIn("does not contain a valid UUID", error_output.getvalue())
        self.assertNotIn(private_value, error_output.getvalue())
        workflow.assert_not_called()
        run_servercopy.assert_not_called()
        run_git.assert_not_called()
        urlopen.assert_not_called()

    def test_valid_uuid_is_loaded_after_lock_and_passed_to_workflow(self) -> None:
        events: list[str] = []

        with TemporaryDirectory() as directory:
            with (
                patch.dict(
                    servercopy_cron.os.environ,
                    {"MERMAID": directory},
                    clear=True,
                ),
                patch.object(
                    servercopy_cron.fcntl,
                    "flock",
                    side_effect=lambda *args: events.append("lock"),
                ),
                patch.object(
                    servercopy_cron,
                    "load_healthchecks_uuid",
                    side_effect=lambda path: events.append("config")
                    or CHECK_UUID,
                ) as load_uuid,
                patch.object(
                    servercopy_cron,
                    "run_cron_workflow",
                    side_effect=lambda *args: events.append("workflow") or 0,
                ) as workflow,
            ):
                status = servercopy_cron.main([])

        self.assertEqual(status, 0)
        self.assertEqual(events, ["lock", "config", "workflow"])
        loaded_path = load_uuid.call_args.args[0]
        self.assertEqual(
            loaded_path,
            SCRIPT.parent / "data" / "healthchecks_uuid.txt",
        )
        workflow.assert_called_once_with(
            SCRIPT.parent / "servercopy",
            Path(directory) / "servers",
            CHECK_UUID,
        )


if __name__ == "__main__":
    unittest.main()
