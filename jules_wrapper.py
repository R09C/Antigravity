import asyncio
import os
import sys
import shutil
from typing import Optional, List
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

from dotenv import load_dotenv

load_dotenv()

CLI_NAME = "jules.cmd" if sys.platform == "win32" else "jules"
JULES_BIN = os.getenv("JULES_BIN_PATH") or shutil.which(CLI_NAME) or CLI_NAME
JULES_TIMEOUT = 120

mcp = FastMCP("jules-wrapper")

@mcp.tool(name="agent_sleep")
async def agent_sleep(seconds: int = 30) -> str:
    """
    Use this tool to pause execution when Jules status is THINKING. 
    This allows you to wait asynchronously without timing out. 
    Immediately call jules_check_status after this tool returns.
    """
    # Cap sleep to 60s to avoid IDE timeouts
    sleep_time = min(seconds, 60)
    await asyncio.sleep(sleep_time)
    return f"Slept for {sleep_time} seconds. You must now call jules_check_status to continue polling."

ANTI_SPAM_DIRECTIVE = """
IMPORTANT SYSTEM RULES:
1. DO NOT open a Pull Request under any circumstances.
2. DO NOT push changes to the remote repository.
3. Keep all changes in a local branch or provide a diff/patch.
"""

def find_git_repo(path: str) -> Optional[str]:
    """Search for the nearest .git directory upward from path."""
    curr = os.path.abspath(path)
    # Protection against infinite loops on some systems
    last = None
    while curr != last:
        if os.path.isdir(os.path.join(curr, ".git")):
            return curr
        last = curr
        curr = os.path.dirname(curr)
    return None


async def _run_jules(args: List[str], stdin_content: Optional[str] = None, timeout: Optional[int] = None, extra_env: Optional[dict] = None, cwd: Optional[str] = None) -> str:
    timeout = timeout or JULES_TIMEOUT
    input_bytes = stdin_content.encode("utf-8") if stdin_content else None
    
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    run_cwd = cwd or os.getcwd()

    # Auto-discovery: if JULES_REPO is not set, try to find it from run_cwd
    if not env.get("JULES_REPO"):
        repo_path = find_git_repo(run_cwd)
        if repo_path:
            env["JULES_REPO"] = repo_path

    # Using stdin for prompts is much safer than flags
    try:
        proc = await asyncio.create_subprocess_exec(
            JULES_BIN, *args,
            stdin=asyncio.subprocess.PIPE if stdin_content else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=run_cwd,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=input_bytes), 
            timeout=timeout
        )
        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()

        combined = out
        if err:
            combined = f"{out}\n{err}".strip() if out else err

        if proc.returncode != 0:
            return f"Error (exit {proc.returncode}):\n{combined}"
        return combined if combined else "(no output)"
    except asyncio.TimeoutError:
        return f"Error: jules command timed out after {timeout}s. Args: {args}"
    except FileNotFoundError:
        return f"Error: '{JULES_BIN}' not found. Make sure Node.js/npm is installed."
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class NewSessionInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    prompt: str = Field(
        ...,
        description="Task description for Jules, e.g. 'write unit tests for auth module'",
        min_length=1,
        max_length=4000,
    )
    repo: str = Field(
        ...,
        description="GitHub repo in owner/name format, e.g. 'torvalds/linux'. Required.",
    )
    parallel: Optional[int] = Field(
        default=1,
        description="Number of parallel sessions (1-5)",
        ge=1,
        le=5,
    )


class RemoteNewInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    prompt: str = Field(
        ...,
        description="Task description for Jules remote session",
        min_length=1,
        max_length=4000,
    )
    repo: str = Field(
        ...,
        description="GitHub repo in owner/name format. Required.",
    )
    parallel: Optional[int] = Field(
        default=1,
        description="Number of parallel sessions (1-5)",
        ge=1,
        le=5,
    )


class PullSessionInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    session_id: str = Field(
        ...,
        description="Session ID to pull results for",
        min_length=1,
    )
    repo: str = Field(
        ...,
        description="Repository name (e.g. 'owner/repo'). Required.",
    )
    apply: bool = Field(
        default=False,
        description="If true, apply the patch to the local repository after pulling",
    )


class TeleportInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    session_id: str = Field(
        ...,
        description="Session ID to teleport to (clone repo + checkout branch + apply patch)",
        min_length=1,
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool(
    name="jules_new_session",
    description="Create a NEW Jules session in the current directory or specified repo. Uses stdin for prompt reliability.",
)
async def jules_new_session(params: NewSessionInput) -> str:
    args = ["new"]
    safe_prompt = f"{params.prompt}\n\n{ANTI_SPAM_DIRECTIVE}"
    
    extra_env = {}
    if params.repo:
        args += ["--repo", params.repo]
        extra_env["JULES_REPO"] = params.repo
    
    # Note: --parallel is not formally supported by the 'new' command but kept in model for parity
    if params.parallel and params.parallel > 1:
        # If Jules supports piping multiple tasks, we might need a different approach
        # For now, we follow the user intent if possible, but the CLI help didn't show it.
        pass

    return await _run_jules(args, stdin_content=safe_prompt, extra_env=extra_env)


@mcp.tool(
    name="jules_remote_new",
    description="Create a REMOTE Jules session. Uses stdin for the prompt for better Windows compatibility.",
)
async def jules_remote_new(params: RemoteNewInput) -> str:
    args = ["remote", "new"]
    extra_env = {}
    if params.repo:
        args += ["--repo", params.repo]
        extra_env["JULES_REPO"] = params.repo
    
    if params.parallel and params.parallel > 1:
        # CLI help didn't show --parallel, removing from execution
        pass
    
    # Passing prompt via stdin is safest on Windows
    safe_prompt = f"{params.prompt}\n\n{ANTI_SPAM_DIRECTIVE}"
    return await _run_jules(args, stdin_content=safe_prompt, extra_env=extra_env)


@mcp.tool()
async def jules_login() -> str:
    """Trigger Jules login flow."""
    return await _run_jules(["login"])


@mcp.tool()
async def jules_logout() -> str:
    """Logout from Jules."""
    return await _run_jules(["logout"])


@mcp.tool(
    name="jules_list_sessions",
    annotations={
        "title": "List Jules Sessions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def jules_list_sessions() -> str:
    return await _run_jules(["remote", "list", "--session"])


@mcp.tool(
    name="jules_list_repos",
    annotations={
        "title": "List Jules Repos",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def jules_list_repos() -> str:
    return await _run_jules(["remote", "list", "--repo"])


@mcp.tool(
    name="jules_pull_session",
    annotations={
        "title": "Pull Jules Session Result",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def jules_pull_session(params: PullSessionInput) -> str:
    # Use full --session flag for maximum compatibility
    args = ["remote", "pull", "--session", str(params.session_id)]
    if params.apply:
        args.append("--apply")
    
    extra_env = {}
    if params.repo:
        extra_env["JULES_REPO"] = params.repo
        
    return await _run_jules(args, extra_env=extra_env)


class CheckStatusInput(BaseModel):
    session_id: str = Field(..., description="Session ID to check status for")
    repo: str = Field(..., description="Repository name for this session. Required.")
    apply: bool = Field(default=True, description="Apply patch automatically when ready")

@mcp.tool(
    name="jules_check_status",
    description=(
        "Atomic, non-blocking check for Jules session status. "
        "Returns the current state: THINKING, BLOCKED_BY_QUESTION, COMPLETED, READY, FINISHED_NO_CHANGES. "
        "IMPORTANT SYSTEM INSTRUCTION FOR AGENT: "
        "If the status is THINKING, you MUST NOT hang or block. You MUST NOT output a final message to the user. "
        "Instead, immediately call the agent_sleep tool, and then check the status again, creating an autonomous loop until the task is COMPLETED."
    )
)
async def jules_check_status(params: CheckStatusInput) -> str:
    """
    Checks the current status of the session in an atomic, non-blocking way.
    """
    session_url = f"https://jules.google.com/session/{params.session_id}"
    
    # Poll progress/diff
    res = await jules_pull_session(PullSessionInput(session_id=params.session_id, repo=params.repo, apply=False))
    lower_res = res.lower()

    # 1. Identify "Finished" states
    is_finished = "finished" in lower_res or "completed" in lower_res

    # 2. Extract strictly "interactive/question" blocks
    blocked_indicators = [
        "waiting for input",
        "select an option",
        "please enter",
        "confirm?",
        "provide feedback",
        "interaction required"
    ]

    progress_part = res.split("diff --git")[0]

    is_blocked = any(ind in progress_part.lower() for ind in blocked_indicators)

    if is_blocked or ("?" in progress_part and not is_finished):
         lines = progress_part.strip().splitlines()
         question_snippet = "\n".join(lines[-3:]) if lines else progress_part

         return (
             f"RESULT_STATE: BLOCKED_BY_QUESTION\n"
             f"SESSION_ID: {params.session_id}\n"
             f"SESSION_URL: {session_url}\n"
             f"DETECTED_QUESTION: {question_snippet}\n\n"
             f"AGENT_INSTRUCTION: Jules is waiting for an answer. You (the agent) can try to "
             f"visit the SESSION_URL using your browser tool to answer the question, or ask the user for help."
         )

    # 3. Handle successful completion
    if "diff --git" in res:
        if params.apply:
            apply_res = await jules_pull_session(PullSessionInput(session_id=params.session_id, repo=params.repo, apply=True))
            if any(x in apply_res.lower() for x in ["patch applied", "applying patch", "already exists"]):
                return f"RESULT_STATE: COMPLETED\nPATCH_STATUS: APPLIED\nSESSION_ID: {params.session_id}\n\nDETAILS:\n{apply_res}"
            return f"RESULT_STATE: READY\nPATCH_STATUS: APPLY_FAILED\nSESSION_ID: {params.session_id}\n\nERROR:\n{apply_res}"
        return f"RESULT_STATE: READY\nPATCH_STATUS: PENDING\nSESSION_ID: {params.session_id}\n\nDIFF_PREVIEW:\n{res[:1000]}"

    # 4. Handle finished without changes
    if is_finished and "no diff found" in lower_res:
        return f"RESULT_STATE: FINISHED_NO_CHANGES\nSESSION_ID: {params.session_id}\n\nOUTPUT:\n{res}"

    # 5. Still thinking
    return f"RESULT_STATE: THINKING\nSESSION_ID: {params.session_id}\n\nOUTPUT:\n{res[:500]}"


@mcp.tool(
    name="jules_teleport",
    annotations={
        "title": "Teleport to Jules Session",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def jules_teleport(params: TeleportInput) -> str:
    return await _run_jules(["teleport", "--session", params.session_id])


@mcp.tool(
    name="jules_version",
    annotations={
        "title": "Jules Version",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def jules_version() -> str:
    return await _run_jules(["version"])


@mcp.tool(
    name="jules_auth_status",
    annotations={
        "title": "Jules Auth Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def jules_auth_status() -> str:
    result = await _run_jules(["version"])
    if "error" in result.lower() or "not logged in" in result.lower():
        return "Auth status: NOT authenticated. Run 'jules login' to authenticate."
    return f"Auth status: authenticated.\n{result}"


if __name__ == "__main__":
    mcp.run()