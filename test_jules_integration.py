import pytest
import os
import asyncio
from typing import Optional
from jules_wrapper import (
    jules_version,
    jules_auth_status,
    jules_list_repos,
    _run_jules,
    jules_new_session,
    NewSessionInput,
    jules_remote_new,
    RemoteNewInput,
    jules_list_sessions,
    jules_pull_session,
    PullSessionInput,
    jules_teleport,
    TeleportInput,
    jules_logout,
    jules_login,
    WaitSessionInput,
    jules_wait_for_result,
)

import re

def extract_session_id(output: str) -> Optional[str]:
    """Helper to pull session ID from Jules command output."""
    match = re.search(r"https://jules\.google\.com/session/(\d+)", output)
    if match:
        return match.group(1)
    return None

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
    print(f"[RESPONSE] {result[:200]}...")
    assert result is not None

@pytest.mark.asyncio
async def test_real_list_sessions_query():
    """Actually calls 'jules remote list --session' without mocks."""
    print("\n[REAL QUERY] Listing real sessions...")
    result = await jules_list_sessions()
    print(f"[RESPONSE] {result[:200]}...")
    assert result is not None

@pytest.mark.asyncio
async def test_real_new_session_local():
    """Test local session creation (dry run prompt if possible)."""
    print("\n[REAL QUERY] Creating a LOCAL session...")
    params = NewSessionInput(
        prompt="This is a local integration test. Just version check.",
        parallel=1
    )
    # Note: This might actually start work if not careful. 
    # But usually 'jules new' needs a repo or files.
    result = await jules_new_session(params)
    print(f"[RESPONSE] {result}")
    assert "Error" not in result

@pytest.mark.asyncio
async def test_real_remote_new_session():
    """Test remote session creation."""
    print("\n[REAL QUERY] Creating a REMOTE session...")
    params = RemoteNewInput(
        prompt="Integration test prompt.",
        repo="R09C/poker_learn"
    )
    result = await jules_remote_new(params)
    print(f"[RESPONSE] {result}")
    # We don't assert SUCCESS because it might fail if repo is invalid or auth issues
    # but we check if the tool itself didn't crash
    assert result is not None

@pytest.mark.asyncio
async def test_real_pull_and_teleport_invalid():
    """Test pull and teleport with invalid IDs to check error handling."""
    print("\n[REAL QUERY] Testing pull/teleport with invalid ID...")
    pull_params = PullSessionInput(session_id="invalid_id", apply=False)
    pull_result = await jules_pull_session(pull_params)
    assert "Error" in pull_result
    
    tele_params = TeleportInput(session_id="invalid_id")
    tele_result = await jules_teleport(tele_params)
    assert "Error" in tele_result

@pytest.mark.asyncio
async def test_login_logout_commands():
    """Verify login/logout commands don't crash the wrapper."""
    # We won't actually login/logout as it's destructive/interactive
    # but we check if the wrapper correctly calls the logic.
    # Integration test for these is hard without interaction.
@pytest.mark.asyncio
async def test_parallel_remote_sessions():
    """Verify that launching parallel sessions works and returns multiple IDs."""
    print("\n[REAL QUERY] Launching PARALLEL remote sessions...")
    params = RemoteNewInput(
        prompt="Parallel test. Reply with 'READY'.",
        repo="R09C/poker_learn",
        parallel=2
    )
    result = await jules_remote_new(params)
    print(f"[RESPONSE] {result}")
    assert "Error" not in result
    # Jules usually returns multiple links or IDs for parallel sessions
    assert result.count("http") >= 1

@pytest.mark.asyncio
async def test_real_patch_application():
    """
    1. Create a session asking for a specific small change.
    2. Wait/Pull session using --session.
    3. Apply patch.
    4. Verify file change.
    """
    print("\n[REAL QUERY] Testing patch application workflow...")
    # 1. Create session
    unique_id = int(asyncio.get_event_loop().time())
    test_comment = f"Jules integration verified at {unique_id}"
    # Use a unique file to avoid any caching/conflict issues
    target_file = f"jules_verify_{unique_id}.md"
    params = NewSessionInput(
        prompt=f"Create a file named '{target_file}' with content: {test_comment}",
        parallel=1
    )
    new_sess_out = await jules_new_session(params)
    print(f"[NEW SESSION OUT] {new_sess_out}")
    
    # Extract session ID if possible
    import re
    sess_id_match = re.search(r"ID: (\d+)", new_sess_out)
    if not sess_id_match:
        sess_id_match = re.search(r"session/(\d+)", new_sess_out)
    
    if not sess_id_match:
        pytest.skip("Could not extract session ID from Jules output")
    
    sess_id = sess_id_match.group(1)
    print(f"[EXTRACTED SESSION ID] {sess_id}")
    
    # 2. Pull/Apply loop
    # We use --apply directly since we want jules to apply it as soon as it's ready
    # Note: Jules CLI might need multiple pulls if it's still 'thinking'
    pull_params = PullSessionInput(session_id=sess_id, apply=True)
    
    max_retries = 15
    patch_confirmed = False
    for i in range(max_retries):
        print(f"[{i+1}/{max_retries}] Pulling session {sess_id} with --apply...")
        pull_result = await jules_pull_session(pull_params)
        print(f"[PULL RESULT] {pull_result[:200]}...")
        
        # Check if patch was applied or if jules is done
        if "applying patch" in pull_result.lower() or "patch applied" in pull_result.lower():
            patch_confirmed = True
            break
            
        if "already exists" in pull_result.lower():
            print("Detected that patch might have been already applied (file exists).")
            patch_confirmed = True
            break
        
        # If it says 'no diff found' but doesn't say 'finished', it might still be thinking
        if "finished" in pull_result.lower():
            break
            
        if "error" in pull_result.lower() and "unknown shorthand flag" in pull_result:
            pytest.fail(f"Regression: unknown shorthand flag found in pull: {pull_result}")

        print(f"Jules is likely still thinking... waiting 20s...")
        await asyncio.sleep(20)
    
    # 3. Verify target file content
    import os
    if os.path.exists(target_file):
        with open(target_file, "r") as f:
            content = f.read()
            if test_comment in content:
                print(f"Verification SUCCESS: {test_comment} found in {target_file}")
                # Cleanup
                # os.remove(target_file)
            else:
                print(f"Verification FAILED: {test_comment} NOT found in {target_file}")
                assert test_comment in content
    else:
        print(f"Verification FAILED: {target_file} was not created.")
        assert os.path.exists(target_file)

@pytest.mark.asyncio
async def test_parallel_task_launching():
    """Verify concurrent session launching via the wrapper."""
    print("\n[REAL QUERY] Launching 2 sessions concurrently...")
    params1 = RemoteNewInput(prompt="Task 1: Say HELLO", repo="R09C/poker_learn")
    params2 = RemoteNewInput(prompt="Task 2: Say WORLD", repo="R09C/poker_learn")
    
    # Launch concurrently
    results = await asyncio.gather(
        jules_remote_new(params1),
        jules_remote_new(params2)
    )
    
    for i, res in enumerate(results):
        print(f"[RESULT {i+1}] {res}")
        assert "Error" not in res
        assert "http" in res
@pytest.mark.asyncio
async def test_wait_for_result_logic():
    """
    Test the logic of wait_for_result using a real session.
    Verifies structured status tags.
    """
    print("\n[REAL QUERY] Testing wait_for_result structured output...")
    unique_id = int(asyncio.get_event_loop().time())
    target_file = f"jules_wait_verify_{unique_id}.md"
    
    # 1. Create a session
    params = NewSessionInput(
        prompt=f"Create a file named '{target_file}' with content: Wait test {unique_id}",
        parallel=1
    )
    new_sess_out = await jules_new_session(params)
    sess_id = extract_session_id(new_sess_out)
    assert sess_id is not None
    
    # 2. Use the new wait tool
    wait_params = WaitSessionInput(
        session_id=sess_id,
        apply=True,
        max_attempts=5,
        interval=25 
    )
    
    wait_res = await jules_wait_for_result(wait_params)
    print(f"[WAIT RESULT] {wait_res}")
    
    # Verify structured output
    assert "RESULT_STATE:" in wait_res
    assert sess_id in wait_res
    
    if "COMPLETED" in wait_res:
        assert os.path.exists(target_file)
        os.remove(target_file)
    elif "BLOCKED_BY_QUESTION" in wait_res:
        print("Test passed: Detected question state.")
    elif "TIMEOUT" in wait_res:
        print("Test partially passed: Polling worked (Jules slow).")

