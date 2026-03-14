import asyncio
import os
import sys
from typing import Optional, List
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

from dotenv import load_dotenv

load_dotenv()

JULES_BIN = r"C:\Users\Администратор\AppData\Roaming\npm\jules.cmd"

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


async def _run_jules(args: List[str], stdin_content: Optional[str] = None, timeout: Optional[int] = None, extra_env: Optional[dict] = None) -> str:
    timeout = timeout or JULES_TIMEOUT
    input_bytes = stdin_content.encode("utf-8") if stdin_content else None
    
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    # Auto-discovery: if JULES_REPO is not set, try to find it from CWD
    if not env.get("JULES_REPO"):
        repo_path = find_git_repo(os.getcwd())
        if repo_path:
            env["JULES_REPO"] = repo_path

    # On Windows, we need to be careful with long argument lists
    # Using stdin for prompts is much safer than flags
    try:
        proc = await asyncio.create_subprocess_exec(
            JULES_BIN, *args,
            stdin=asyncio.subprocess.PIPE if stdin_content else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
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
    repo: Optional[str] = Field(
        default=None,
        description="GitHub repo in owner/name format, e.g. 'torvalds/linux'. Defaults to CWD repo.",
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
    repo: Optional[str] = Field(
        default=None,
        description="GitHub repo in owner/name format. Defaults to CWD repo.",
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
    if params.parallel and params.parallel > 1:
        args += ["--parallel", str(params.parallel)]

    return await _run_jules(args, stdin_content=safe_prompt, extra_env=extra_env)


@mcp.tool(
    name="jules_remote_new",
    description="Create a REMOTE Jules session. Uses stdin for the prompt for better Windows compatibility.",
)
async def jules_remote_new(params: RemoteNewInput) -> str:
    # Based on help: jules remote new --repo jiahao42/jules-cli --session "..."
    # 'jules remote new' help says --session can take piped input.
    # We use --session without a value (empty string or just omit) and pipe.
    # Actually, if we omit --session value, some CLIs might fail. 
    # But usually 'jules remote new --repo X' with stdin works.
    args = ["remote", "new"]
    extra_env = {}
    if params.repo:
        args += ["--repo", params.repo]
        extra_env["JULES_REPO"] = params.repo
    if params.parallel and params.parallel > 1:
        args += ["--parallel", str(params.parallel)]
    
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
    args = ["remote", "pull", "--session", params.session_id]
    if params.apply:
        args.append("--apply")
    return await _run_jules(args)


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
    return await _run_jules(["teleport", params.session_id])


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