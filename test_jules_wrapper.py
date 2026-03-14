import asyncio
import pytest
import os
from unittest.mock import AsyncMock, patch
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
)

@pytest.mark.asyncio
async def test_run_jules_success():
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"success output", b"")
    mock_proc.returncode = 0
    
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await _run_jules(["test", "arg"])
        assert result == "success output"
        mock_exec.assert_called_once_with(
            JULES_BIN, "test", "arg",
            stdin=None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ
        )

@pytest.mark.asyncio
async def test_run_jules_failure():
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"error message")
    mock_proc.returncode = 1
    
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await _run_jules(["test"])
        assert "Error (exit 1):" in result
        assert "error message" in result

@pytest.mark.asyncio
async def test_run_jules_timeout():
    mock_proc = AsyncMock()
    mock_proc.communicate.side_effect = asyncio.TimeoutError()
    
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
async def test_jules_new_session_tool():
    params = NewSessionInput(prompt="test prompt", repo="owner/repo", parallel=2)
    mock_run = AsyncMock(return_value="done")
    with patch("jules_wrapper._run_jules", mock_run):
        await jules_new_session(params)
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert "new" in args[0]
        assert "stdin_content" in kwargs
        assert "test prompt" in kwargs["stdin_content"]
        assert "extra_env" in kwargs
        assert kwargs["extra_env"].get("JULES_REPO") == "owner/repo"


@pytest.mark.asyncio
async def test_jules_remote_new_tool():
    params = RemoteNewInput(prompt="remote prompt")
    with patch("jules_wrapper._run_jules", new_callable=AsyncMock) as mock_run:
        await jules_remote_new(params)
        args, kwargs = mock_run.call_args
        cmd_args = args[0]
        # jules_remote_new uses stdin for the prompt
        assert "remote" in cmd_args
        assert "new" in cmd_args
        assert "stdin_content" in kwargs
        assert "remote prompt" in kwargs["stdin_content"]
        # In this test params.repo is None, so extra_env should be {} or None or not have JULES_REPO
        assert kwargs.get("extra_env", {}).get("JULES_REPO") is None


@pytest.mark.asyncio
async def test_find_git_repo():
    # We are in the project root which has a .git
    root = os.getcwd()
    repo = find_git_repo(root)
    assert repo is not None
    # Subdir should also find it
    subdir = os.path.join(root, "tests")
    if not os.path.exists(subdir):
        os.makedirs(subdir, exist_ok=True)
    assert find_git_repo(subdir) is not None


@pytest.mark.asyncio
async def test_jules_login_tool():
    with patch("jules_wrapper._run_jules", new_callable=AsyncMock) as mock_run:
        await jules_login()
        mock_run.assert_called_with(["login"])


@pytest.mark.asyncio
async def test_jules_logout_tool():
    with patch("jules_wrapper._run_jules", new_callable=AsyncMock) as mock_run:
        await jules_logout()
        mock_run.assert_called_with(["logout"])

@pytest.mark.asyncio
async def test_jules_list_sessions_tool():
    with patch("jules_wrapper._run_jules", new_callable=AsyncMock) as mock_run:
        await jules_list_sessions()
        mock_run.assert_called_once_with(["remote", "list", "--session"])

@pytest.mark.asyncio
async def test_jules_list_repos_tool():
    with patch("jules_wrapper._run_jules", new_callable=AsyncMock) as mock_run:
        await jules_list_repos()
        mock_run.assert_called_once_with(["remote", "list", "--repo"])

@pytest.mark.asyncio
async def test_jules_pull_session_tool():
    params = PullSessionInput(session_id="sess_123", apply=True)
    with patch("jules_wrapper._run_jules", new_callable=AsyncMock) as mock_run:
        await jules_pull_session(params)
        mock_run.assert_called_once_with(["remote", "pull", "--session", "sess_123", "--apply"])

@pytest.mark.asyncio
async def test_jules_teleport_tool():
    params = TeleportInput(session_id="sess_456")
    with patch("jules_wrapper._run_jules", new_callable=AsyncMock) as mock_run:
        await jules_teleport(params)
        mock_run.assert_called_once_with(["teleport", "sess_456"])

@pytest.mark.asyncio
async def test_jules_version_tool():
    with patch("jules_wrapper._run_jules", new_callable=AsyncMock) as mock_run:
        await jules_version()
        mock_run.assert_called_once_with(["version"])

@pytest.mark.asyncio
async def test_jules_auth_status_authenticated():
    with patch("jules_wrapper._run_jules", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = "jules v1.0.0"
        result = await jules_auth_status()
        assert "authenticated" in result.lower()
        assert "not authenticated" not in result.lower()

@pytest.mark.asyncio
async def test_jules_auth_status_not_authenticated():
    with patch("jules_wrapper._run_jules", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = "Error: NOT LOGGED IN"
        result = await jules_auth_status()
        assert "not authenticated" in result.lower()
