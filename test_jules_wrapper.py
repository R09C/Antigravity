import asyncio
import pytest
import os
import importlib
from unittest.mock import AsyncMock, patch, MagicMock
from jules_wrapper import (
    _run_jules,
    jules_new_session,
    jules_remote_new,
    jules_list_sessions,
    jules_list_repos,
    jules_pull_session,
    jules_teleport,
    jules_version,
    jules_auth_status,
    jules_login,
    jules_logout,
    NewSessionInput,
    RemoteNewInput,
    PullSessionInput,
    TeleportInput,
    CheckStatusInput,
    jules_check_status,
    JULES_BIN,
    find_git_repo,
    JULES_TIMEOUT,
)

def test_jules_bin_resolution_env_var():
    with patch("os.getenv", return_value="/custom/env/jules"):
        with patch("shutil.which", return_value="/usr/bin/jules"):
            import jules_wrapper
            importlib.reload(jules_wrapper)
            assert jules_wrapper.JULES_BIN == "/custom/env/jules"

def test_jules_bin_resolution_shutil():
    with patch("os.getenv", return_value=None):
        with patch("shutil.which", return_value="/usr/bin/jules"):
            import jules_wrapper
            importlib.reload(jules_wrapper)
            assert jules_wrapper.JULES_BIN == "/usr/bin/jules"

def test_jules_bin_resolution_fallback():
    with patch("os.getenv", return_value=None):
        with patch("shutil.which", return_value=None):
            import jules_wrapper
            importlib.reload(jules_wrapper)
            assert jules_wrapper.JULES_BIN == "jules"

@pytest.mark.asyncio
async def test_run_jules_success():
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"success output", b"")
    mock_proc.returncode = 0
    
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await _run_jules(["test", "arg"])
        assert result == "success output"
        mock_exec.assert_called_once()
        # Verify default cwd behavior
        kwargs = mock_exec.call_args[1]
        assert "cwd" in kwargs

@pytest.mark.asyncio
async def test_run_jules_with_cwd():
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"success output", b"")
    mock_proc.returncode = 0

    custom_cwd = "/custom/path"
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        with patch("jules_wrapper.find_git_repo", return_value=None) as mock_find_repo:
            result = await _run_jules(["test", "arg"], cwd=custom_cwd)
            assert result == "success output"
            mock_exec.assert_called_once()
            kwargs = mock_exec.call_args[1]
            assert kwargs["cwd"] == custom_cwd
            mock_find_repo.assert_called_once_with(custom_cwd)

@pytest.mark.asyncio
async def test_run_jules_empty_output():
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"")
    mock_proc.returncode = 0
    
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await _run_jules(["test"])
        assert result == "(no output)"

@pytest.mark.asyncio
async def test_run_jules_failure():
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"part out", b"error message")
    mock_proc.returncode = 1
    
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await _run_jules(["test"])
        assert "Error (exit 1):" in result
        assert "error message" in result
        assert "part out" in result

@pytest.mark.asyncio
async def test_run_jules_timeout():
    mock_proc = AsyncMock()
    # wait_for itself raises the error, communicate might not have finished
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
            result = await _run_jules(["test"], timeout=1)
            assert "timed out" in result

@pytest.mark.asyncio
async def test_run_jules_file_not_found():
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError()):
        result = await _run_jules(["test"])
        assert "not found" in result

@pytest.mark.asyncio
async def test_run_jules_generic_exception():
    with patch("asyncio.create_subprocess_exec", side_effect=RuntimeError("boom")):
        result = await _run_jules(["test"])
        assert "Error: RuntimeError: boom" in result

@pytest.mark.asyncio
async def test_find_git_repo_not_found():
    with patch("os.path.isdir", return_value=False):
        with patch("os.path.dirname", side_effect=lambda x: x): # stop at /
             # This might loop if not careful, but find_git_repo has curr != last
             # let's mock it properly
             def mock_dirname(path):
                 if path == "C:\\": return "C:\\"
                 return "C:\\"
             with patch("os.path.dirname", side_effect=mock_dirname):
                assert find_git_repo("C:\\some\\path") is None

@pytest.mark.asyncio
async def test_jules_new_session_tool():
    params = NewSessionInput(prompt="test prompt", repo="owner/repo", parallel=1)
    mock_run = AsyncMock(return_value="done")
    with patch("jules_wrapper._run_jules", mock_run):
        await jules_new_session(params)
        mock_run.assert_called_once()
        args, stdin, timeout, extra_env = mock_run.call_args[0] if len(mock_run.call_args[0]) > 2 else (mock_run.call_args[0][0], mock_run.call_args[1].get('stdin_content'), mock_run.call_args[1].get('timeout'), mock_run.call_args[1].get('extra_env'))
        assert "new" in args
        assert "--repo" in args
        assert "owner/repo" in args
        assert extra_env["JULES_REPO"] == "owner/repo"

@pytest.mark.asyncio
async def test_jules_remote_new_tool():
    params = RemoteNewInput(prompt="remote prompt", repo="owner/repo", parallel=1)
    with patch("jules_wrapper._run_jules", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = "session 12345 created"
        await jules_remote_new(params)
        args, kwargs = mock_run.call_args
        cmd_args = args[0]
        extra_env = kwargs.get('extra_env', {})
        assert "remote" in cmd_args
        assert "new" in cmd_args
        assert "--repo" in cmd_args
        assert "owner/repo" in cmd_args
        assert extra_env["JULES_REPO"] == "owner/repo"

@pytest.mark.asyncio
async def test_jules_auth_status_variants():
    with patch("jules_wrapper._run_jules", new_callable=AsyncMock) as mock_run:
        # Not logged in
        mock_run.return_value = "Error: not logged in"
        assert "NOT authenticated" in await jules_auth_status()
        
        # Logged in
        mock_run.return_value = "Jules v1.2.3"
        assert "authenticated" in (await jules_auth_status()).lower()
        # jules_auth_status internally calls version, so we check that
        mock_run.assert_called_with(["version"])

@pytest.mark.asyncio
async def test_jules_check_status_thinking():
    with patch("jules_wrapper.jules_pull_session", new_callable=AsyncMock) as mock_pull:
        mock_pull.return_value = "Some log output without diff or finish"
        params = CheckStatusInput(session_id="123", repo="test/repo")
        result = await jules_check_status(params)
        assert "RESULT_STATE: THINKING" in result
        assert "SESSION_ID: 123" in result

@pytest.mark.asyncio
async def test_jules_check_status_awaiting_user_feedback():
    with patch("jules_wrapper.jules_pull_session", new_callable=AsyncMock) as mock_pull:
        mock_pull.return_value = "Waiting for input from the user"
        params = CheckStatusInput(session_id="123", repo="test/repo")
        result = await jules_check_status(params)
        assert "RESULT_STATE: AWAITING_USER_FEEDBACK" in result

@pytest.mark.asyncio
async def test_jules_check_status_awaiting_plan_approval():
    with patch("jules_wrapper.jules_pull_session", new_callable=AsyncMock) as mock_pull:
        mock_pull.return_value = "Here is the plan:\n1. do this\n2. do that\nProceed with this plan?"
        params = CheckStatusInput(session_id="123", repo="test/repo")
        result = await jules_check_status(params)
        assert "RESULT_STATE: AWAITING_PLAN_APPROVAL" in result

@pytest.mark.asyncio
async def test_jules_check_status_completed_pending_confirmation():
    with patch("jules_wrapper.jules_pull_session", new_callable=AsyncMock) as mock_pull:
        mock_pull.return_value = "diff --git a/test.py b/test.py\n--- a/test.py\n+++ b/test.py\n+ new code\ndeleted file mode 100644\ndiff --git a/del.py b/del.py\n--- a/del.py\n+++ /dev/null\n"

        # apply=False -> should return PENDING_CONFIRMATION
        params = CheckStatusInput(session_id="123", repo="test/repo", apply=False)
        result = await jules_check_status(params)

        assert "RESULT_STATE: READY" in result
        assert "PATCH_STATUS: PENDING_CONFIRMATION" in result
        assert "test.py" in result
        assert "del.py" in result

@pytest.mark.asyncio
async def test_jules_check_status_completed_smart_applied():
    with patch("jules_wrapper.jules_pull_session", new_callable=AsyncMock) as mock_pull:
        with patch("jules_wrapper._run_jules", new_callable=AsyncMock) as mock_run_jules:
            with patch("jules_wrapper.find_git_repo", return_value="/fake/repo"):
                with patch("os.path.exists", return_value=True):
                    with patch("os.remove") as mock_remove:
                        with patch("shutil.copy2") as mock_copy2:
                            with patch("os.makedirs"):
                                # Simulated diff output with one modification and one deletion
                                mock_pull.return_value = "diff --git a/test.py b/test.py\n--- a/test.py\n+++ b/test.py\n+ new code\ndiff --git a/del.py b/del.py\ndeleted file mode 100644\n--- a/del.py\n+++ /dev/null\n"
                                mock_run_jules.return_value = "teleport success"

                                # apply=True -> should return SMART_APPLIED
                                params = CheckStatusInput(session_id="123", repo="test/repo", apply=True)
                                result = await jules_check_status(params)

                                assert "RESULT_STATE: COMPLETED" in result
                                assert "PATCH_STATUS: SMART_APPLIED" in result
                                assert "UPDATED: test.py" in result
                                assert "DELETED: del.py" in result
                                mock_remove.assert_called_once_with("/fake/repo/del.py")
                                mock_copy2.assert_called_once()

@pytest.mark.asyncio
async def test_jules_check_status_finished_no_changes():
    with patch("jules_wrapper.jules_pull_session", new_callable=AsyncMock) as mock_pull:
        mock_pull.return_value = "Job finished. No diff found."
        params = CheckStatusInput(session_id="123", repo="test/repo")
        result = await jules_check_status(params)
        assert "RESULT_STATE: FINISHED_NO_CHANGES" in result

@pytest.mark.asyncio
async def test_jules_check_status_system_error():
    with patch("jules_wrapper.jules_pull_session", new_callable=AsyncMock) as mock_pull:
        mock_pull.return_value = "Error: Something failed\n"
        params = CheckStatusInput(session_id="123", repo="test/repo")
        result = await jules_check_status(params)
        assert "RESULT_STATE: SYSTEM_ERROR" in result

@pytest.mark.asyncio
async def test_session_cache_validation():
    import jules_wrapper
    jules_wrapper.SESSION_CACHE["cached_sess"] = "cached/repo"

    # Try with wrong repo
    params = PullSessionInput(session_id="cached_sess", repo="wrong/repo")
    result = await jules_wrapper.jules_pull_session(params)
    assert "Error: Session cached_sess is cached for repo cached/repo" in result

    # Try check_status with wrong repo
    status_params = CheckStatusInput(session_id="cached_sess", repo="wrong/repo")
    status_result = await jules_wrapper.jules_check_status(status_params)
    assert "Error: Session cached_sess is cached for repo cached/repo" in status_result

    # Try with correct repo
    with patch("jules_wrapper._run_jules", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = "success"
        params_correct = PullSessionInput(session_id="cached_sess", repo="cached/repo")
        res_correct = await jules_wrapper.jules_pull_session(params_correct)
        assert res_correct == "success"
        mock_run.assert_called_once()
