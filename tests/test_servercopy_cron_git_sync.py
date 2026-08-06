"""Offline tests for servercopy_cron's optional Git synchronization loop."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import call, patch

from tests.test_servercopy_cron import (
    CHECK_UUID,
    SERVERCOPY_VERSION,
    git_result,
    servercopy_cron,
)


class GitDetectionTests(unittest.TestCase):
    def init_repository(self, root: Path) -> None:
        subprocess.run(
            ["git", "init", "-q", str(root)],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_repository_root_enables_git_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_repository(root)

            with redirect_stdout(StringIO()):
                detected, failure = servercopy_cron.detect_git_root(root)

        self.assertEqual(detected, root.resolve())
        self.assertIsNone(failure)

    def test_managed_subdirectory_enables_git_mode_and_resolves_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            managed = root / "servers"
            managed.mkdir()
            self.init_repository(root)

            with redirect_stdout(StringIO()):
                detected, failure = servercopy_cron.detect_git_root(managed)

        self.assertEqual(detected, root.resolve())
        self.assertIsNone(failure)

    def test_non_git_and_not_yet_created_paths_are_not_applicable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for managed in (root, root / "not-created"):
                with self.subTest(managed=managed), redirect_stdout(StringIO()):
                    detected, failure = servercopy_cron.detect_git_root(managed)

                self.assertIsNone(detected)
                self.assertIsNone(failure)

    def test_non_git_workflow_invokes_only_git_detection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            managed = Path(directory)
            with (
                patch.object(
                    servercopy_cron,
                    "run_git",
                    return_value=git_result(
                        128,
                        stderr="fatal: not a git repository",
                    ),
                ) as run_git,
                patch.object(servercopy_cron, "ping_start"),
                patch.object(
                    servercopy_cron,
                    "get_servercopy_version",
                    return_value=SERVERCOPY_VERSION,
                ),
                patch.object(servercopy_cron, "run_servercopy", return_value=0),
                patch.object(servercopy_cron, "ping_success"),
                redirect_stdout(StringIO()),
            ):
                status = servercopy_cron.run_cron_workflow(
                    Path("/repo/servercopy"),
                    managed,
                    CHECK_UUID,
                )

            self.assertEqual(status, servercopy_cron.EXIT_SUCCESS)
            self.assertEqual(
                run_git.call_args_list,
                [call(managed, "rev-parse", "--show-toplevel")],
            )


class GitPhaseCommandTests(unittest.TestCase):
    def test_clean_preflight_uses_whole_repository_porcelain_status(self) -> None:
        root = Path("/repo")
        with (
            patch.object(
                servercopy_cron,
                "run_git",
                return_value=git_result(0),
            ) as run_git,
            redirect_stdout(StringIO()),
        ):
            result, failure = servercopy_cron.preflight_servers_repository(root)

        self.assertEqual(result, servercopy_cron.PHASE_SUCCESS)
        self.assertIsNone(failure)
        run_git.assert_called_once_with(root, "status", "--porcelain")

    def test_dirty_preflight_reports_status_and_fails(self) -> None:
        error_output = StringIO()
        with (
            patch.object(
                servercopy_cron,
                "run_git",
                return_value=git_result(0, " M changed.txt\n?? new.txt\n"),
            ),
            redirect_stderr(error_output),
        ):
            result, failure = servercopy_cron.preflight_servers_repository(
                Path("/repo")
            )

        self.assertEqual(result, servercopy_cron.PHASE_FAILURE)
        self.assertEqual(failure, servercopy_cron.DIRTY_REPOSITORY_REASON)
        self.assertIn(" M changed.txt", error_output.getvalue())
        self.assertIn("?? new.txt", error_output.getvalue())

    def test_status_inspection_failure_is_reported(self) -> None:
        error_output = StringIO()
        with (
            patch.object(
                servercopy_cron,
                "run_git",
                return_value=git_result(
                    128,
                    stderr="fatal: synthetic status failure",
                ),
            ),
            redirect_stderr(error_output),
        ):
            result, failure = servercopy_cron.preflight_servers_repository(
                Path("/repo")
            )

        self.assertEqual(result, servercopy_cron.PHASE_FAILURE)
        self.assertIn("exit status 128", failure)
        self.assertIn("synthetic status failure", error_output.getvalue())

    def test_pull_is_fast_forward_only_and_uses_configured_upstream(self) -> None:
        root = Path("/repo")
        with (
            patch.object(
                servercopy_cron,
                "run_git",
                return_value=git_result(0, "Updating 123..456\n"),
            ) as run_git,
            redirect_stdout(StringIO()),
        ):
            result, failure = servercopy_cron.pull_repository(root)

        self.assertEqual(result, servercopy_cron.PHASE_SUCCESS)
        self.assertIsNone(failure)
        run_git.assert_called_once_with(root, "pull", "--ff-only")
        arguments = run_git.call_args.args
        self.assertNotIn("--force", arguments)
        self.assertNotIn("origin", arguments)
        self.assertNotIn("main", arguments)

    def test_already_up_to_date_pull_is_reported_as_success(self) -> None:
        output = StringIO()
        with (
            patch.object(
                servercopy_cron,
                "run_git",
                return_value=git_result(0, "Already up to date.\n"),
            ),
            redirect_stdout(output),
        ):
            result, failure = servercopy_cron.pull_repository(Path("/repo"))

        self.assertEqual(result, servercopy_cron.PHASE_SUCCESS)
        self.assertIsNone(failure)
        self.assertIn("already up to date", output.getvalue())

    def test_pull_failure_records_exit_status_and_sanitizes_url_userinfo(
        self,
    ) -> None:
        error_output = StringIO()
        with (
            patch.object(
                servercopy_cron,
                "run_git",
                return_value=git_result(
                    7,
                    stderr=(
                        "fatal: unable to access "
                        "'https://operator:secret@example.test/repo.git/'"
                    ),
                ),
            ),
            redirect_stdout(StringIO()),
            redirect_stderr(error_output),
        ):
            result, failure = servercopy_cron.pull_repository(Path("/repo"))

        self.assertEqual(result, servercopy_cron.PHASE_FAILURE)
        self.assertIn("exit status 7", failure)
        self.assertIn("https://[redacted]@example.test", error_output.getvalue())
        self.assertNotIn("operator:secret", error_output.getvalue())

    def test_root_changes_are_staged_with_existing_add_policy(self) -> None:
        root = Path("/repo")
        responses = [
            git_result(0, f"{root}\n"),
            git_result(0),
            git_result(0),
            git_result(1),
            git_result(0),
        ]
        with (
            patch.object(
                servercopy_cron,
                "run_git",
                side_effect=responses,
            ) as run_git,
            patch.object(
                servercopy_cron,
                "utc_now",
                return_value="2026-07-29T12:00:00Z",
            ),
            redirect_stdout(StringIO()),
        ):
            result = servercopy_cron.commit_synced_changes(
                root,
                root,
                SERVERCOPY_VERSION,
                0,
            )

        self.assertEqual(result, servercopy_cron.PHASE_SUCCESS)
        self.assertIn(call(root, "add", "-A"), run_git.call_args_list)
        commit_call = run_git.call_args_list[-1]
        self.assertEqual(
            commit_call.args[-1],
            "servercopy [cron]: 2026-07-29T12:00:00Z "
            f"[servercopy={SERVERCOPY_VERSION} "
            f"servercopy_cron={servercopy_cron.SERVERCOPY_CRON_VERSION}]\n\n"
            "America/Los_Angeles: 2026-07-29T05:00:00-07:00\n"
            "America/New_York: 2026-07-29T08:00:00-04:00",
        )

    def test_local_timestamp_uses_standard_time_offsets(self) -> None:
        timestamp = "2026-01-15T12:00:00Z"

        self.assertEqual(
            servercopy_cron.local_timestamp(timestamp, "America/Los_Angeles"),
            "2026-01-15T04:00:00-08:00",
        )
        self.assertEqual(
            servercopy_cron.local_timestamp(timestamp, "America/New_York"),
            "2026-01-15T07:00:00-05:00",
        )

    def test_subdirectory_changes_are_staged_only_in_managed_scope(self) -> None:
        root = Path("/repo")
        managed = root / "servers"
        responses = [
            git_result(0, f"{root}\n"),
            git_result(0),
            git_result(0),
            git_result(1),
            git_result(0),
        ]
        with (
            patch.object(
                servercopy_cron,
                "run_git",
                side_effect=responses,
            ) as run_git,
            redirect_stdout(StringIO()),
        ):
            result = servercopy_cron.commit_synced_changes(
                root,
                managed,
                SERVERCOPY_VERSION,
                0,
            )

        self.assertEqual(result, servercopy_cron.PHASE_SUCCESS)
        self.assertIn(
            call(root, "add", "-A", "--", "servers"),
            run_git.call_args_list,
        )

    def test_failed_sync_uses_partial_commit_subject(self) -> None:
        root = Path("/repo")
        responses = [
            git_result(0, f"{root}\n"),
            git_result(0),
            git_result(0),
            git_result(1),
            git_result(0),
        ]
        with (
            patch.object(
                servercopy_cron,
                "run_git",
                side_effect=responses,
            ) as run_git,
            redirect_stdout(StringIO()),
        ):
            result = servercopy_cron.commit_synced_changes(
                root,
                root,
                SERVERCOPY_VERSION,
                17,
            )

        self.assertEqual(result, servercopy_cron.PHASE_SUCCESS)
        self.assertIn(
            "servercopy [cron partial]:",
            run_git.call_args_list[-1].args[-1],
        )

    def test_no_changes_does_not_create_empty_commit(self) -> None:
        root = Path("/repo")
        responses = [
            git_result(0, f"{root}\n"),
            git_result(0),
            git_result(0),
            git_result(0),
        ]
        with (
            patch.object(
                servercopy_cron,
                "run_git",
                side_effect=responses,
            ) as run_git,
            redirect_stdout(StringIO()),
        ):
            result = servercopy_cron.commit_synced_changes(
                root,
                root,
                SERVERCOPY_VERSION,
                0,
            )

        self.assertEqual(result, servercopy_cron.PHASE_NO_CHANGES)
        self.assertFalse(
            any(item.args[1:2] == ("commit",) for item in run_git.call_args_list)
        )

    def test_commit_failure_is_distinct(self) -> None:
        root = Path("/repo")
        responses = [
            git_result(0, f"{root}\n"),
            git_result(0),
            git_result(0),
            git_result(1),
            git_result(9, stderr="synthetic commit failure"),
        ]
        with (
            patch.object(servercopy_cron, "run_git", side_effect=responses),
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()),
        ):
            result = servercopy_cron.commit_synced_changes(
                root,
                root,
                SERVERCOPY_VERSION,
                0,
            )

        self.assertEqual(result, servercopy_cron.PHASE_FAILURE)

    def test_preexisting_staged_changes_prevent_add_and_commit(self) -> None:
        root = Path("/repo")
        responses = [
            git_result(0, f"{root}\n"),
            git_result(1),
        ]
        with (
            patch.object(
                servercopy_cron,
                "run_git",
                side_effect=responses,
            ) as run_git,
            redirect_stderr(StringIO()),
        ):
            result = servercopy_cron.commit_synced_changes(
                root,
                root,
                SERVERCOPY_VERSION,
                0,
            )

        self.assertEqual(result, servercopy_cron.PHASE_FAILURE)
        self.assertFalse(
            any(item.args[1:2] == ("add",) for item in run_git.call_args_list)
        )
        self.assertFalse(
            any(item.args[1:2] == ("commit",) for item in run_git.call_args_list)
        )

    def test_staging_failure_prevents_commit(self) -> None:
        root = Path("/repo")
        responses = [
            git_result(0, f"{root}\n"),
            git_result(0),
            git_result(6, stderr="synthetic add failure"),
        ]
        with (
            patch.object(
                servercopy_cron,
                "run_git",
                side_effect=responses,
            ) as run_git,
            redirect_stderr(StringIO()),
        ):
            result = servercopy_cron.commit_synced_changes(
                root,
                root,
                SERVERCOPY_VERSION,
                0,
            )

        self.assertEqual(result, servercopy_cron.PHASE_FAILURE)
        self.assertFalse(
            any(item.args[1:2] == ("commit",) for item in run_git.call_args_list)
        )

    def test_push_uses_configured_upstream_without_force(self) -> None:
        root = Path("/repo")
        with (
            patch.object(
                servercopy_cron,
                "run_git",
                return_value=git_result(0),
            ) as run_git,
            redirect_stdout(StringIO()),
        ):
            result, failure = servercopy_cron.push_created_commit(root)

        self.assertEqual(result, servercopy_cron.PHASE_SUCCESS)
        self.assertIsNone(failure)
        run_git.assert_called_once_with(root, "push")
        self.assertNotIn("--force", run_git.call_args.args)
        self.assertNotIn("origin", run_git.call_args.args)

    def test_push_failure_retains_local_commit_and_reports_it(self) -> None:
        error_output = StringIO()
        with (
            patch.object(
                servercopy_cron,
                "run_git",
                return_value=git_result(8, stderr="rejected"),
            ),
            redirect_stdout(StringIO()),
            redirect_stderr(error_output),
        ):
            result, failure = servercopy_cron.push_created_commit(Path("/repo"))

        self.assertEqual(result, servercopy_cron.PHASE_FAILURE)
        self.assertIn("exit status 8", failure)
        self.assertIn("committed locally", error_output.getvalue())
        self.assertIn("local commit was retained", error_output.getvalue())


class LocalGitIntegrationTests(unittest.TestCase):
    def run_git(self, repository: Path, *arguments: str) -> None:
        subprocess.run(
            ["git", *arguments],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )

    def test_pull_commit_and_push_round_trip_through_configured_upstream(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            remote = workspace / "remote.git"
            repository = workspace / "working"
            verification = workspace / "verification"
            subprocess.run(
                ["git", "init", "--bare", "-q", str(remote)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "clone", "-q", str(remote), str(repository)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.run_git(repository, "config", "user.name", "Test Operator")
            self.run_git(
                repository,
                "config",
                "user.email",
                "operator@example.test",
            )
            managed = repository / "servers"
            managed.mkdir()
            (managed / "seed.txt").write_text("seed\n", encoding="ascii")
            self.run_git(repository, "add", "-A")
            self.run_git(repository, "commit", "-q", "-m", "seed")
            self.run_git(repository, "push", "-q", "-u", "origin", "HEAD")

            with redirect_stdout(StringIO()):
                pull_result, pull_failure = servercopy_cron.pull_repository(
                    repository
                )
            (managed / "download.txt").write_text(
                "synchronized\n",
                encoding="ascii",
            )
            with redirect_stdout(StringIO()):
                commit_result = servercopy_cron.commit_synced_changes(
                    repository,
                    managed,
                    SERVERCOPY_VERSION,
                    0,
                )
                push_result, push_failure = servercopy_cron.push_created_commit(
                    repository
                )

            subprocess.run(
                ["git", "clone", "-q", str(remote), str(verification)],
                check=True,
                capture_output=True,
                text=True,
            )
            subject = subprocess.run(
                ["git", "log", "-1", "--format=%s"],
                cwd=verification,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            self.assertEqual(pull_result, servercopy_cron.PHASE_SUCCESS)
            self.assertIsNone(pull_failure)
            self.assertEqual(commit_result, servercopy_cron.PHASE_SUCCESS)
            self.assertEqual(push_result, servercopy_cron.PHASE_SUCCESS)
            self.assertIsNone(push_failure)
            self.assertEqual(
                (verification / "servers" / "download.txt").read_text(
                    encoding="ascii"
                ),
                "synchronized\n",
            )
            self.assertTrue(subject.startswith("servercopy [cron]:"))


class GitSynchronizationTests(unittest.TestCase):
    managed = Path("/repo/servers")
    git_root = Path("/repo")

    def run_workflow(
        self,
        *,
        git_managed: bool = True,
        preflight: tuple[str, str | None] | None = None,
        pull: tuple[str, str | None] | None = None,
        sync_status: int = 0,
        commit: str = servercopy_cron.PHASE_NO_CHANGES,
        push: tuple[str, str | None] | None = None,
    ) -> tuple[int, list[str], str, object, object]:
        events: list[str] = []
        preflight = preflight or (servercopy_cron.PHASE_SUCCESS, None)
        pull = pull or (servercopy_cron.PHASE_SUCCESS, None)
        push = push or (servercopy_cron.PHASE_SUCCESS, None)

        def detect(path: Path) -> tuple[Path | None, str | None]:
            events.append("detect")
            return (self.git_root if git_managed else None), None

        def clean(root: Path) -> tuple[str, str | None]:
            events.append("preflight")
            return preflight

        def update(root: Path) -> tuple[str, str | None]:
            events.append("pull")
            return pull

        def sync(command: Path, managed: Path) -> int:
            events.append("sync")
            return sync_status

        def preserve(*args: object) -> str:
            events.append("commit")
            return commit

        def publish(root: Path) -> tuple[str, str | None]:
            events.append("push")
            return push

        def success(uuid: str) -> None:
            events.append("health-success")

        def failure(uuid: str, message: str) -> None:
            events.append("health-failure")

        output = StringIO()
        error_output = StringIO()
        with (
            patch.object(servercopy_cron, "ping_start"),
            patch.object(servercopy_cron, "detect_git_root", side_effect=detect),
            patch.object(
                servercopy_cron,
                "preflight_servers_repository",
                side_effect=clean,
            ),
            patch.object(servercopy_cron, "pull_repository", side_effect=update),
            patch.object(
                servercopy_cron,
                "get_servercopy_version",
                return_value=SERVERCOPY_VERSION,
            ),
            patch.object(servercopy_cron, "run_servercopy", side_effect=sync),
            patch.object(
                servercopy_cron,
                "commit_synced_changes",
                side_effect=preserve,
            ) as commit_changes,
            patch.object(
                servercopy_cron,
                "push_created_commit",
                side_effect=publish,
            ) as push_commit,
            patch.object(servercopy_cron, "ping_success", side_effect=success),
            patch.object(servercopy_cron, "ping_failure", side_effect=failure),
            redirect_stdout(output),
            redirect_stderr(error_output),
        ):
            status = servercopy_cron.run_cron_workflow(
                Path("/repo/servercopy"),
                self.managed,
                CHECK_UUID,
            )

        return (
            status,
            events,
            output.getvalue() + error_output.getvalue(),
            commit_changes,
            push_commit,
        )

    def test_dirty_repository_aborts_before_pull_and_sync(self) -> None:
        status, events, output, commit_changes, push_commit = self.run_workflow(
            preflight=(
                servercopy_cron.PHASE_FAILURE,
                servercopy_cron.DIRTY_REPOSITORY_REASON,
            )
        )

        self.assertEqual(status, servercopy_cron.EXIT_DIRTY_REPOSITORY)
        self.assertEqual(events, ["detect", "preflight", "health-failure"])
        self.assertIn("pull: skipped", output)
        self.assertIn("sync: skipped", output)
        commit_changes.assert_not_called()
        push_commit.assert_not_called()

    def test_clean_repository_pulls_before_sync(self) -> None:
        status, events, _, _, _ = self.run_workflow()

        self.assertEqual(status, servercopy_cron.EXIT_SUCCESS)
        self.assertLess(events.index("pull"), events.index("sync"))

    def test_pull_failure_continues_sync_commit_and_push_but_fails_overall(
        self,
    ) -> None:
        status, events, output, commit_changes, push_commit = self.run_workflow(
            pull=(servercopy_cron.PHASE_FAILURE, "Git pull failed."),
            commit=servercopy_cron.PHASE_SUCCESS,
        )

        self.assertEqual(status, servercopy_cron.EXIT_PULL_FAILURE)
        self.assertEqual(events[-1], "health-failure")
        self.assertLess(events.index("pull"), events.index("sync"))
        self.assertLess(events.index("sync"), events.index("commit"))
        self.assertLess(events.index("commit"), events.index("push"))
        self.assertIn("pull: failure", output)
        self.assertIn("overall: failure", output)
        commit_changes.assert_called_once()
        push_commit.assert_called_once()

    def test_pull_failure_does_not_make_successful_sync_commit_partial(
        self,
    ) -> None:
        _, _, _, commit_changes, _ = self.run_workflow(
            pull=(servercopy_cron.PHASE_FAILURE, "Git pull failed."),
            commit=servercopy_cron.PHASE_SUCCESS,
        )

        self.assertEqual(commit_changes.call_args.args[-1], 0)

    def test_failed_sync_still_commits_partial_changes_and_pushes(self) -> None:
        status, events, output, commit_changes, push_commit = self.run_workflow(
            sync_status=17,
            commit=servercopy_cron.PHASE_SUCCESS,
        )

        self.assertEqual(status, 17)
        self.assertLess(events.index("sync"), events.index("commit"))
        self.assertLess(events.index("commit"), events.index("push"))
        self.assertEqual(commit_changes.call_args.args[-1], 17)
        push_commit.assert_called_once()
        self.assertIn("sync: failure", output)

    def test_successful_commit_triggers_exactly_one_push(self) -> None:
        status, events, _, _, push_commit = self.run_workflow(
            commit=servercopy_cron.PHASE_SUCCESS
        )

        self.assertEqual(status, servercopy_cron.EXIT_SUCCESS)
        self.assertEqual(events.count("push"), 1)
        push_commit.assert_called_once_with(self.git_root)

    def test_no_changes_skips_push_and_succeeds(self) -> None:
        status, events, output, _, push_commit = self.run_workflow()

        self.assertEqual(status, servercopy_cron.EXIT_SUCCESS)
        self.assertNotIn("push", events)
        push_commit.assert_not_called()
        self.assertIn("commit: no-changes", output)
        self.assertIn("push: skipped", output)
        self.assertEqual(events[-1], "health-success")

    def test_commit_failure_skips_push_and_reports_failure(self) -> None:
        status, events, output, _, push_commit = self.run_workflow(
            commit=servercopy_cron.PHASE_FAILURE
        )

        self.assertEqual(status, servercopy_cron.EXIT_COMMIT_FAILURE)
        self.assertNotIn("push", events)
        push_commit.assert_not_called()
        self.assertIn("commit: failure", output)
        self.assertEqual(events[-1], "health-failure")

    def test_push_failure_retains_distinct_overall_failure(self) -> None:
        status, events, output, _, _ = self.run_workflow(
            commit=servercopy_cron.PHASE_SUCCESS,
            push=(servercopy_cron.PHASE_FAILURE, "Git push failed."),
        )

        self.assertEqual(status, servercopy_cron.EXIT_PUSH_FAILURE)
        self.assertIn("push", events)
        self.assertIn("push: failure", output)
        self.assertIn("overall: failure", output)
        self.assertEqual(events[-1], "health-failure")

    def test_non_git_mode_skips_all_git_phases_and_can_succeed(self) -> None:
        status, events, output, commit_changes, push_commit = self.run_workflow(
            git_managed=False
        )

        self.assertEqual(status, servercopy_cron.EXIT_SUCCESS)
        self.assertEqual(events, ["detect", "sync", "health-success"])
        commit_changes.assert_not_called()
        push_commit.assert_not_called()
        for phase in ("preflight-clean", "pull", "commit", "push"):
            self.assertIn(f"{phase}: not-applicable", output)
        self.assertIn("git-mode: not-applicable", output)

    def test_all_phase_results_are_logged_independently(self) -> None:
        _, _, output, _, _ = self.run_workflow(
            commit=servercopy_cron.PHASE_SUCCESS
        )

        for expected in (
            "git-mode: enabled",
            "preflight-clean: success",
            "pull: success",
            "sync: success",
            "commit: success",
            "push: success",
            "overall: success",
        ):
            self.assertIn(expected, output)

    def test_multiple_failures_are_all_logged_and_sync_status_has_precedence(
        self,
    ) -> None:
        status, events, output, _, _ = self.run_workflow(
            pull=(servercopy_cron.PHASE_FAILURE, "Git pull failed."),
            sync_status=17,
            commit=servercopy_cron.PHASE_SUCCESS,
            push=(servercopy_cron.PHASE_FAILURE, "Git push failed."),
        )

        self.assertEqual(status, 17)
        self.assertIn("pull: failure", output)
        self.assertIn("sync: failure", output)
        self.assertIn("commit: success", output)
        self.assertIn("push: failure", output)
        self.assertEqual(events[-1], "health-failure")

    def test_failure_precedence_is_pull_then_commit_then_push_after_sync(
        self,
    ) -> None:
        cases = (
            (
                {
                    "pull": (
                        servercopy_cron.PHASE_FAILURE,
                        "Git pull failed.",
                    ),
                    "commit": servercopy_cron.PHASE_FAILURE,
                },
                servercopy_cron.EXIT_PULL_FAILURE,
            ),
            (
                {"commit": servercopy_cron.PHASE_FAILURE},
                servercopy_cron.EXIT_COMMIT_FAILURE,
            ),
            (
                {
                    "commit": servercopy_cron.PHASE_SUCCESS,
                    "push": (
                        servercopy_cron.PHASE_FAILURE,
                        "Git push failed.",
                    ),
                },
                servercopy_cron.EXIT_PUSH_FAILURE,
            ),
        )
        for arguments, expected in cases:
            with self.subTest(expected=expected):
                status, _, _, _, _ = self.run_workflow(**arguments)
                self.assertEqual(status, expected)

    def test_healthchecks_failure_is_used_for_each_fatal_phase(self) -> None:
        cases = (
            {
                "pull": (
                    servercopy_cron.PHASE_FAILURE,
                    "Git pull failed.",
                )
            },
            {"sync_status": 17},
            {"commit": servercopy_cron.PHASE_FAILURE},
            {
                "commit": servercopy_cron.PHASE_SUCCESS,
                "push": (
                    servercopy_cron.PHASE_FAILURE,
                    "Git push failed.",
                ),
            },
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                status, events, _, _, _ = self.run_workflow(**arguments)
                self.assertNotEqual(status, 0)
                self.assertEqual(events[-1], "health-failure")
                self.assertNotIn("health-success", events)


if __name__ == "__main__":
    unittest.main()
