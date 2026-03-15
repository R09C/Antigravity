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
async def test_jules_check_status_blocked_by_question():
    with patch("jules_wrapper.jules_pull_session", new_callable=AsyncMock) as mock_pull:
        mock_pull.return_value = "Please confirm? [y/N]"
        params = CheckStatusInput(session_id="123", repo="test/repo")
        result = await jules_check_status(params)
        assert "RESULT_STATE: BLOCKED_BY_QUESTION" in result
        assert "Please confirm? [y/N]" in result

@pytest.mark.asyncio
async def test_jules_check_status_completed():
    with patch("jules_wrapper.jules_pull_session", new_callable=AsyncMock) as mock_pull:
        # First call gets diff
        # Second call (apply) gets "patch applied"
        mock_pull.side_effect = [
            "Here is the code\ndiff --git a/file b/file\n+ new code",
            "patch applied successfully"
        ]
        params = CheckStatusInput(session_id="123", repo="test/repo")
        result = await jules_check_status(params)
        assert "RESULT_STATE: COMPLETED" in result
        assert "PATCH_STATUS: APPLIED" in result

@pytest.mark.asyncio
async def test_jules_check_status_finished_no_changes():
    with patch("jules_wrapper.jules_pull_session", new_callable=AsyncMock) as mock_pull:
        mock_pull.return_value = "Job finished. No diff found."
        params = CheckStatusInput(session_id="123", repo="test/repo")
        result = await jules_check_status(params)
        assert "RESULT_STATE: FINISHED_NO_CHANGES" in result
