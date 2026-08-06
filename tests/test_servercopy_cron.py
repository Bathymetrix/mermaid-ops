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
from threading import Event
from typing import TextIO
import unittest
from unittest.mock import ANY, patch
from urllib.error import URLError


SCRIPT = Path(__file__).resolve().parents[1] / "servercopy_cron"
LOADER = SourceFileLoader("servercopy_cron_module", str(SCRIPT))
SPEC = spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
servercopy_cron = module_from_spec(SPEC)
sys.modules[LOADER.name] = servercopy_cron
LOADER.exec_module(servercopy_cron)

CHECK_UUID = "11111111-2222-3333-4444-555555555555"
SERVERCOPY_VERSION = "2.2.2"


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


class FakeProcess:
    def __init__(
        self,
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
        wait_for: Event | None = None,
    ) -> None:
        self.stdout = StringIO(stdout)
        self.stderr = StringIO(stderr)
        self.returncode = returncode
        self.wait_for = wait_for

    def wait(self) -> int:
        if self.wait_for is not None:
            if not self.wait_for.wait(timeout=1):
                raise AssertionError("output was not forwarded before wait")
        return self.returncode


class SignalingStringIO(StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.written = Event()

    def write(self, text: str) -> int:
        written = super().write(text)
        self.written.set()
        return written


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
    def test_lifecycle_pings_preserve_success_and_include_failure_message(
        self,
    ) -> None:
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
            servercopy_cron.ping_failure(
                CHECK_UUID,
                "servercopy_cron failed: synthetic failure.",
            )

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
        self.assertEqual(
            [request.data for request, _ in requests],
            [
                b"",
                b"",
                b"servercopy_cron failed: synthetic failure.",
            ],
        )
        self.assertEqual(
            [
                request.get_header("Content-type")
                for request, _ in requests
            ],
            [None, None, "text/plain; charset=utf-8"],
        )
        self.assertEqual([timeout for _, timeout in requests], [15, 15, 15])

    def test_failure_summary_includes_excerpt_and_local_log_path(self) -> None:
        terminal = StringIO()
        log = StringIO()
        transcript = servercopy_cron.RunTranscript(log)
        transcript.write(terminal, "Git status:\n M changed.txt\n")
        log_path = Path("/mermaid/logs/servercopy_cron/run.log")

        with patch.object(servercopy_cron, "ping_failure") as ping_failure:
            status = servercopy_cron.finish_failed_run(
                CHECK_UUID,
                7,
                "servers repository is not clean.",
                log_path,
                transcript,
            )

        self.assertEqual(status, 7)
        ping_failure.assert_called_once()
        check_uuid, message = ping_failure.call_args.args
        self.assertEqual(check_uuid, CHECK_UUID)
        self.assertIn("servers repository is not clean", message)
        self.assertIn(" M changed.txt", message)
        self.assertIn(str(log_path), message)

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
    def test_git_uses_repository_as_working_directory(self) -> None:
        completed = git_result(0)
        repository = Path("/mermaid/servers")

        with patch.object(
            servercopy_cron.subprocess,
            "run",
            return_value=completed,
        ) as run:
            result = servercopy_cron.run_git(
                repository,
                "rev-parse",
                "--show-toplevel",
            )

        self.assertIs(result, completed)
        run.assert_called_once_with(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_servercopy_version_is_read_from_exact_version_command(self) -> None:
        completed = subprocess.CompletedProcess(
            ["servercopy", "--version"],
            0,
            stdout=f"servercopy {SERVERCOPY_VERSION}\n",
            stderr="",
        )

        with patch.object(
            servercopy_cron.subprocess,
            "run",
            return_value=completed,
        ) as run:
            version = servercopy_cron.get_servercopy_version(
                Path("/repo/servercopy")
            )

        self.assertEqual(version, SERVERCOPY_VERSION)
        run.assert_called_once_with(
            [sys.executable, "/repo/servercopy", "--version"],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_servercopy_version_probe_failures_return_none(self) -> None:
        failures = (
            subprocess.CompletedProcess(
                ["servercopy", "--version"],
                7,
                stdout="",
                stderr="synthetic failure",
            ),
            subprocess.CompletedProcess(
                ["servercopy", "--version"],
                0,
                stdout="servercopy 1.7.0 unexpected\n",
                stderr="",
            ),
            OSError("synthetic launch failure"),
        )

        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                error_output = StringIO()
                with (
                    patch.object(
                        servercopy_cron.subprocess,
                        "run",
                        side_effect=failure
                        if isinstance(failure, OSError)
                        else None,
                        return_value=None
                        if isinstance(failure, OSError)
                        else failure,
                    ),
                    redirect_stderr(error_output),
                ):
                    version = servercopy_cron.get_servercopy_version(
                        Path("/repo/servercopy")
                    )

                self.assertIsNone(version)
                error = error_output.getvalue()
                self.assertIn("servercopy", error)
                self.assertIn("version", error)

    def test_servercopy_copies_stdout_and_stderr_live(self) -> None:
        output = SignalingStringIO()
        process = FakeProcess(
            stdout="servercopy stdout\n",
            stderr="servercopy stderr\n",
            wait_for=output.written,
        )
        error_output = StringIO()

        with (
            patch.object(
                servercopy_cron.subprocess,
                "Popen",
                return_value=process,
            ) as popen,
            redirect_stdout(output),
            redirect_stderr(error_output),
        ):
            status = servercopy_cron.run_servercopy(
                Path("/repo/servercopy"),
                Path("/mermaid/servers"),
            )

        self.assertEqual(status, 0)
        self.assertEqual(output.getvalue(), "servercopy stdout\n")
        self.assertEqual(error_output.getvalue(), "servercopy stderr\n")
        arguments, keywords = popen.call_args
        self.assertEqual(
            arguments[0],
            [
                sys.executable,
                "/repo/servercopy",
                "--output",
                "/mermaid/servers",
            ],
        )
        self.assertIs(keywords["stdout"], subprocess.PIPE)
        self.assertIs(keywords["stderr"], subprocess.PIPE)
        self.assertEqual(keywords["env"]["PYTHONUNBUFFERED"], "1")


class LoggingTests(unittest.TestCase):
    def run_logged_cron_workflow(
        self,
        mermaid_root: Path,
    ) -> tuple[int, Path]:
        filename = "2026-07-27T19-56-50Z.log"
        log_path = mermaid_root / "logs" / "servercopy_cron" / filename

        def run_locked(
            configured_root: Path,
            repository_root: Path,
            configured_log_path: Path,
            transcript: object,
        ) -> int:
            return servercopy_cron.run_cron_workflow(
                Path("/repo/servercopy"),
                configured_root / "servers",
                CHECK_UUID,
                configured_log_path,
                transcript,
            )

        with (
            patch.object(
                servercopy_cron,
                "utc_log_filename",
                return_value=filename,
            ),
            patch.object(
                servercopy_cron,
                "run_locked_workflow",
                side_effect=run_locked,
            ),
        ):
            status = servercopy_cron.run_logged_invocation(
                mermaid_root,
                Path("/repo"),
                ["/repo/servercopy_cron"],
            )

        return status, log_path

    def test_healthchecks_start_failure_is_logged(self) -> None:
        with TemporaryDirectory() as directory:
            with (
                patch.object(
                    servercopy_cron,
                    "ping_start",
                    side_effect=servercopy_cron.HealthchecksPingError,
                ),
                redirect_stdout(StringIO()),
                redirect_stderr(StringIO()),
            ):
                status, log_path = self.run_logged_cron_workflow(
                    Path(directory)
                )

            transcript = log_path.read_text(encoding="utf-8")

        self.assertNotEqual(status, 0)
        self.assertIn("Healthchecks.io start ping failed", transcript)
        self.assertIn("servercopy_cron exit status: 1", transcript)

    def test_servercopy_failure_is_logged_and_reported(self) -> None:
        with TemporaryDirectory() as directory:
            with (
                patch.object(servercopy_cron, "ping_start"),
                patch.object(
                    servercopy_cron,
                    "preflight_servers_repository",
                    return_value=None,
                ),
                patch.object(
                    servercopy_cron,
                    "get_servercopy_version",
                    return_value=SERVERCOPY_VERSION,
                ),
                patch.object(
                    servercopy_cron.subprocess,
                    "Popen",
                    return_value=FakeProcess(
                        stdout="live synchronization output\n",
                        returncode=17,
                    ),
                ),
                patch.object(
                    servercopy_cron,
                    "commit_synced_changes",
                    return_value=0,
                ) as commit_changes,
                patch.object(
                    servercopy_cron,
                    "ping_failure",
                    side_effect=servercopy_cron.HealthchecksPingError,
                ) as ping_failure,
                redirect_stdout(StringIO()),
                redirect_stderr(StringIO()),
            ):
                status, log_path = self.run_logged_cron_workflow(
                    Path(directory)
                )

            transcript = log_path.read_text(encoding="utf-8")

        self.assertEqual(status, 17)
        self.assertIn(
            f"servercopy version: {SERVERCOPY_VERSION}",
            transcript,
        )
        self.assertIn("live synchronization output", transcript)
        self.assertIn("servercopy failed (exit status 17)", transcript)
        self.assertIn("failure ping also failed", transcript)
        self.assertIn("servercopy_cron exit status: 17", transcript)
        commit_changes.assert_not_called()
        ping_failure.assert_called_once()
        self.assertIn("servercopy failed", ping_failure.call_args.args[1])
        self.assertIn(str(log_path), ping_failure.call_args.args[1])

    def test_healthchecks_success_failure_is_logged(self) -> None:
        with TemporaryDirectory() as directory:
            with (
                patch.object(servercopy_cron, "ping_start"),
                patch.object(
                    servercopy_cron,
                    "preflight_servers_repository",
                    return_value=None,
                ),
                patch.object(
                    servercopy_cron,
                    "get_servercopy_version",
                    return_value=SERVERCOPY_VERSION,
                ),
                patch.object(servercopy_cron, "run_servercopy", return_value=0),
                patch.object(
                    servercopy_cron,
                    "commit_synced_changes",
                    return_value=0,
                ),
                patch.object(
                    servercopy_cron,
                    "ping_success",
                    side_effect=servercopy_cron.HealthchecksPingError,
                ),
                redirect_stdout(StringIO()),
                redirect_stderr(StringIO()),
            ):
                status, log_path = self.run_logged_cron_workflow(
                    Path(directory)
                )

            transcript = log_path.read_text(encoding="utf-8")

        self.assertNotEqual(status, 0)
        self.assertIn("Healthchecks.io success ping failed", transcript)
        self.assertIn("servercopy_cron exit status: 1", transcript)

    def test_git_failure_is_logged_and_reported(self) -> None:
        def fail_git(
            git_root: Path,
            managed_path: Path,
            version: str,
            servercopy_status: int,
        ) -> str:
            print("Error: git commit failed (exit status 7).", file=sys.stderr)
            print("Git reported: synthetic commit failure", file=sys.stderr)
            return servercopy_cron.PHASE_FAILURE

        with TemporaryDirectory() as directory:
            with (
                patch.object(servercopy_cron, "ping_start"),
                patch.object(
                    servercopy_cron,
                    "detect_git_root",
                    side_effect=lambda managed_path: (managed_path, None),
                ),
                patch.object(
                    servercopy_cron,
                    "preflight_servers_repository",
                    return_value=(servercopy_cron.PHASE_SUCCESS, None),
                ),
                patch.object(
                    servercopy_cron,
                    "pull_repository",
                    return_value=(servercopy_cron.PHASE_SUCCESS, None),
                ),
                patch.object(
                    servercopy_cron,
                    "get_servercopy_version",
                    return_value=SERVERCOPY_VERSION,
                ),
                patch.object(servercopy_cron, "run_servercopy", return_value=0),
                patch.object(
                    servercopy_cron,
                    "commit_synced_changes",
                    side_effect=fail_git,
                ),
                patch.object(
                    servercopy_cron,
                    "ping_failure",
                ) as ping_failure,
                redirect_stdout(StringIO()),
                redirect_stderr(StringIO()),
            ):
                status, log_path = self.run_logged_cron_workflow(
                    Path(directory)
                )

            transcript = log_path.read_text(encoding="utf-8")

        self.assertNotEqual(status, 0)
        self.assertIn("synthetic commit failure", transcript)
        self.assertIn("servercopy_cron exit status: 4", transcript)
        ping_failure.assert_called_once()
        message = ping_failure.call_args.args[1]
        self.assertIn("Git staging or commit processing failed", message)
        self.assertIn("synthetic commit failure", message)
        self.assertIn(str(log_path), message)

    def test_timestamp_collision_creates_distinct_log(self) -> None:
        with TemporaryDirectory() as directory:
            log_directory = Path(directory)
            with patch.object(
                servercopy_cron,
                "utc_log_filename",
                return_value="2026-07-27T19-56-50Z.log",
            ):
                first_path, first_log = servercopy_cron.open_run_log(
                    log_directory
                )
                first_log.close()
                second_path, second_log = servercopy_cron.open_run_log(
                    log_directory
                )
                second_log.close()

        self.assertEqual(first_path.name, "2026-07-27T19-56-50Z.log")
        self.assertEqual(second_path.name, "2026-07-27T19-56-50Z_1.log")


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
                    patch.object(
                        servercopy_cron,
                        "run_logged_invocation",
                    ) as logged_workflow,
                    patch.object(
                        servercopy_cron.fcntl,
                        "flock",
                    ) as flock,
                    redirect_stdout(output),
                    self.assertRaises(SystemExit) as raised,
                ):
                    servercopy_cron.main([option])

                self.assertEqual(raised.exception.code, 0)
                self.assertEqual(output.getvalue(), "servercopy_cron 2.7.0\n")
                load_uuid.assert_not_called()
                logged_workflow.assert_not_called()
                flock.assert_not_called()

    def test_missing_mermaid_fails_before_any_work(self) -> None:
        error_output = StringIO()

        with (
            patch.dict(servercopy_cron.os.environ, {}, clear=True),
            patch.object(
                servercopy_cron,
                "load_healthchecks_uuid",
            ) as load_uuid,
            patch.object(
                servercopy_cron,
                "run_logged_invocation",
            ) as logged_invocation,
            redirect_stderr(error_output),
        ):
            status = servercopy_cron.main([])

        self.assertNotEqual(status, 0)
        self.assertIn("MERMAID must be set", error_output.getvalue())
        load_uuid.assert_not_called()
        logged_invocation.assert_not_called()

    def test_overlapping_execution_sends_no_healthcheck_requests_or_work(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            mermaid_root = Path(directory).resolve()
            output = StringIO()
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
                redirect_stdout(output),
                redirect_stderr(error_output),
            ):
                status = servercopy_cron.main([])

            logs = list(
                (mermaid_root / "logs" / "servercopy_cron").glob("*.log")
            )
            self.assertEqual(len(logs), 1)
            transcript = logs[0].read_text(encoding="utf-8")

        self.assertNotEqual(status, 0)
        self.assertIn("already running", error_output.getvalue())
        self.assertIn("already running", transcript)
        self.assertIn("servercopy_cron exit status: 1", transcript)
        load_uuid.assert_not_called()
        workflow.assert_not_called()
        run_servercopy.assert_not_called()
        run_git.assert_not_called()
        urlopen.assert_not_called()

    def test_absent_uuid_file_fails_before_servercopy_git_or_ping(self) -> None:
        with TemporaryDirectory() as directory:
            mermaid_root = Path(directory).resolve()
            output = StringIO()
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
                redirect_stdout(output),
                redirect_stderr(error_output),
            ):
                status = servercopy_cron.main([])

            logs = list(
                (mermaid_root / "logs" / "servercopy_cron").glob("*.log")
            )
            self.assertEqual(len(logs), 1)
            transcript = logs[0].read_text(encoding="utf-8")

        self.assertNotEqual(status, 0)
        self.assertIn("UUID file could not be read", error_output.getvalue())
        self.assertIn("UUID file could not be read", transcript)
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
            mermaid_root = Path(directory).resolve()
            output = StringIO()
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
                redirect_stdout(output),
                redirect_stderr(error_output),
            ):
                status = servercopy_cron.main([])

            logs = list(
                (mermaid_root / "logs" / "servercopy_cron").glob("*.log")
            )
            self.assertEqual(len(logs), 1)
            transcript = logs[0].read_text(encoding="utf-8")

        self.assertNotEqual(status, 0)
        self.assertIn("does not contain a valid UUID", error_output.getvalue())
        self.assertIn("does not contain a valid UUID", transcript)
        self.assertNotIn(private_value, error_output.getvalue())
        self.assertNotIn(private_value, transcript)
        workflow.assert_not_called()
        run_servercopy.assert_not_called()
        run_git.assert_not_called()
        urlopen.assert_not_called()

    def test_lock_preparation_failure_is_logged(self) -> None:
        original_open = Path.open

        def fail_lock_open(
            path: Path,
            *args: object,
            **kwargs: object,
        ) -> TextIO:
            if path.name == "servercopy_cron.lock":
                raise OSError("synthetic lock preparation failure")
            return original_open(path, *args, **kwargs)

        with TemporaryDirectory() as directory:
            mermaid_root = Path(directory).resolve()
            output = StringIO()
            error_output = StringIO()
            with (
                patch.dict(
                    servercopy_cron.os.environ,
                    {"MERMAID": directory},
                    clear=True,
                ),
                patch.object(Path, "open", new=fail_lock_open),
                redirect_stdout(output),
                redirect_stderr(error_output),
            ):
                status = servercopy_cron.main([])

            logs = list(
                (mermaid_root / "logs" / "servercopy_cron").glob("*.log")
            )
            self.assertEqual(len(logs), 1)
            transcript = logs[0].read_text(encoding="utf-8")

        self.assertNotEqual(status, 0)
        self.assertIn("could not prepare", error_output.getvalue())
        self.assertIn("synthetic lock preparation failure", transcript)
        self.assertIn("servercopy_cron exit status: 1", transcript)

    def test_unexpected_logged_exception_records_traceback_and_status(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            mermaid_root = Path(directory).resolve()
            output = StringIO()
            error_output = StringIO()
            with (
                patch.dict(
                    servercopy_cron.os.environ,
                    {"MERMAID": directory},
                    clear=True,
                ),
                patch.object(
                    servercopy_cron,
                    "run_locked_workflow",
                    side_effect=RuntimeError("synthetic unexpected failure"),
                ),
                redirect_stdout(output),
                redirect_stderr(error_output),
            ):
                status = servercopy_cron.main([])

            logs = list(
                (mermaid_root / "logs" / "servercopy_cron").glob("*.log")
            )
            self.assertEqual(len(logs), 1)
            transcript = logs[0].read_text(encoding="utf-8")

        self.assertNotEqual(status, 0)
        self.assertIn("unexpected servercopy_cron failure", transcript)
        self.assertIn("RuntimeError: synthetic unexpected failure", transcript)
        self.assertIn("servercopy_cron exit status: 1", transcript)
        self.assertIn("unexpected servercopy_cron failure", error_output.getvalue())

    def test_successful_workflow_creates_one_complete_timestamped_log(
        self,
    ) -> None:
        events: list[str] = []
        output = StringIO()
        error_output = StringIO()

        with TemporaryDirectory() as directory:
            mermaid_root = Path(directory).resolve()
            filename = "2026-07-27T19-56-50Z.log"

            def run_workflow(
                command: Path,
                repository: Path,
                check_uuid: str,
                log_path: Path,
                transcript: object,
            ) -> int:
                events.append("workflow")
                print("wrapper stdout")
                print("wrapper stderr", file=sys.stderr)
                return servercopy_cron.run_servercopy(command, repository)

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
                    "utc_log_filename",
                    return_value=filename,
                ),
                patch.object(
                    servercopy_cron,
                    "utc_now",
                    return_value="2026-07-27T19:56:50Z",
                ),
                patch.object(
                    servercopy_cron.getpass,
                    "getuser",
                    return_value="operator",
                ),
                patch.object(
                    servercopy_cron.socket,
                    "getfqdn",
                    return_value="host.example.org",
                ),
                patch.object(
                    servercopy_cron.platform,
                    "platform",
                    return_value="TestOS-1.0",
                ),
                patch.object(
                    servercopy_cron,
                    "run_cron_workflow",
                    side_effect=run_workflow,
                ) as workflow,
                patch.object(
                    servercopy_cron.subprocess,
                    "Popen",
                    return_value=FakeProcess(
                        stdout="servercopy stdout\n",
                        stderr="servercopy stderr\n",
                    ),
                ),
                redirect_stdout(output),
                redirect_stderr(error_output),
            ):
                status = servercopy_cron.main([])

            self.assertEqual(status, 0)
            self.assertEqual(events, ["lock", "config", "workflow"])
            loaded_path = load_uuid.call_args.args[0]
            self.assertEqual(
                loaded_path,
                SCRIPT.parent / "data" / "healthchecks_uuid.txt",
            )

            logs = list(
                (mermaid_root / "logs" / "servercopy_cron").glob("*.log")
            )
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0].name, filename)
            transcript_text = logs[0].read_text(encoding="utf-8")
            for expected in (
                "servercopy_cron started: 2026-07-27T19:56:50Z",
                "servercopy_cron version: 2.7.0",
                "invocation: operator@host.example.org",
                "system: TestOS-1.0",
                f"MERMAID: {mermaid_root}",
                f"repository: {SCRIPT.parent}",
                f"python: {sys.executable}",
                f"command: {SCRIPT}",
                f"log: {logs[0]}",
                "wrapper stdout",
                "wrapper stderr",
                "servercopy stdout",
                "servercopy stderr",
                "servercopy_cron exit status: 0",
            ):
                self.assertIn(expected, transcript_text)
            self.assertIn("wrapper stdout", output.getvalue())
            self.assertIn("servercopy stdout", output.getvalue())
            self.assertIn("wrapper stderr", error_output.getvalue())
            self.assertIn("servercopy stderr", error_output.getvalue())

            workflow.assert_called_once_with(
                SCRIPT.parent / "servercopy",
                mermaid_root / "servers",
                CHECK_UUID,
                logs[0],
                ANY,
            )


if __name__ == "__main__":
    unittest.main()
