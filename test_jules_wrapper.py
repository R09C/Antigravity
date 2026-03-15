import asyncio
import pytest
import os
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
    JULES_BIN,
    find_git_repo,
    JULES_TIMEOUT,
)

@pytest.mark.asyncio
async def test_run_jules_success():
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"success output", b"")
    mock_proc.returncode = 0
    
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await _run_jules(["test", "arg"])
        assert result == "success output"
        mock_exec.assert_called_once()

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
