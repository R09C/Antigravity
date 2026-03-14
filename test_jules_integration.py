import pytest
import os
from jules_wrapper import (
    jules_version,
    jules_auth_status,
    jules_list_repos,
    _run_jules
)

@pytest.mark.asyncio
async def test_real_version_query():
    """Actually calls 'jules version' without mocks."""
    print("\n[REAL QUERY] Running 'jules version'...")
    result = await jules_version()
    print(f"[RESPONSE] {result}")
    assert "Error" not in result or "not found" not in result

@pytest.mark.asyncio
async def test_real_auth_status_query():
    """Actually calls 'jules auth status' logic without mocks."""
    print("\n[REAL QUERY] Checking real auth status...")
    result = await jules_auth_status()
    print(f"[RESPONSE] {result}")
    assert "Auth status:" in result

@pytest.mark.asyncio
async def test_real_list_repos_query():
    """Actually calls 'jules remote list --repo' without mocks."""
    print("\n[REAL QUERY] Listing real repos...")
    result = await jules_list_repos()
    print(f"[RESPONSE] {result[:200]}...") # Truncate for readability
    assert result is not None

@pytest.mark.asyncio
async def test_real_remote_session_creation():
    """Actually creates a remote Jules session."""
    from jules_wrapper import jules_remote_new, RemoteNewInput
    
    print("\n[REAL QUERY] Creating a REMOTE session (test)...")
    params = RemoteNewInput(
        prompt="This is an automated integration test. Just reply 'SUCCESS' if you read this.",
        repo="R09C/poker_learn"
    )
    result = await jules_remote_new(params)
    print(f"[RESPONSE] {result}")
    assert "Error" not in result
    assert "Session ID" in result or "created" in result.lower()

@pytest.mark.asyncio
async def test_real_list_sessions_query():
    """Actually calls 'jules remote list --session' without mocks."""
    from jules_wrapper import jules_list_sessions
    
    print("\n[REAL QUERY] Listing real sessions...")
    result = await jules_list_sessions()
    print(f"[RESPONSE] {result}")
    assert result is not None
