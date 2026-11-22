"""Pruebas de coherencia del puente OpenCode/DeepSeek y el modo nocturno."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODEL = "opencode-go/deepseek-v4.1-flash"
HOOK = ".claude/hooks/opencode_writer.sh"


def _bash_executable() -> str:
    bash = shutil.which("bash")
    if os.name != "nt":
        if bash:
            return bash
        pytest.skip("Bash no está instalado")

    candidates = [
        Path(bash) if bash else None,
        Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        / "Git"
        / "bin"
        / "bash.exe",
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
        / "Git"
        / "bin"
        / "bash.exe",
    ]
    for candidate in candidates:
        if candidate and candidate.is_file() and "git" in str(candidate).lower():
            return str(candidate)
    pytest.skip("El test del preflight requiere Git Bash; bash de WSL no es compatible")


def _auth_check(output: str | None, *, command_fails: bool = False) -> bool:
    env = os.environ.copy()
    env["OPENCODE_AUTH_OUTPUT"] = output or ""
    mock_opencode = (
        "opencode() { return 23; }"
        if command_fails
        else 'opencode() { printf \'%s\\n\' "$OPENCODE_AUTH_OUTPUT"; }'
    )
    result = subprocess.run(
        [
            _bash_executable(),
            "-c",
            f"source {HOOK}; {mock_opencode}; opencode_writer_authenticated",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def test_writer_model_is_pinned_to_configured_deepseek_v41_flash():
    config = json.loads((ROOT / "opencode.json").read_text(encoding="utf-8"))
    hook = (ROOT / HOOK).read_text(encoding="utf-8")
    writer = (ROOT / "scripts" / "run_opencode_writer.sh").read_text(encoding="utf-8")
    assert config["agent"]["implementer"]["model"] == MODEL
    assert (
        config["agent"]["implementer"]["permission"]["edit"][
            "scripts/run_locked_command.py"
        ]
        == "deny"
    )
    assert set(config["provider"]) == {"opencode-go"}
    assert f'readonly OPENCODE_WRITER_MODEL="{MODEL}"' in hook
    assert 'MODEL="$OPENCODE_WRITER_MODEL"' in writer
    assert 'opencode run --agent implementer --model "$MODEL" "$PROMPT"' in writer
    assert 'read -r -a PY_CMD <<< "$PY"' in writer
    assert '"${PY_CMD[@]}" - "$FEATURE"' in writer


def test_supervised_and_nocturno_bridges_share_the_writer_preflight():
    writer = (ROOT / "scripts" / "run_opencode_writer.sh").read_text(encoding="utf-8")
    nocturno = (ROOT / "nocturno.sh").read_text(encoding="utf-8")
    assert "source .claude/hooks/opencode_writer.sh" in writer
    assert "opencode_writer_authenticated" in writer
    assert "source .claude/hooks/opencode_writer.sh" in nocturno
    assert "opencode_writer_authenticated" in nocturno
    assert "OpenCode Go no está conectado" in nocturno
    assert "deepseek/deepseek-flash" not in (ROOT / "README.md").read_text(
        encoding="utf-8"
    )


def test_nocturno_runs_without_default_limits_and_retries_stalls():
    nocturno = (ROOT / "nocturno.sh").read_text(encoding="utf-8")
    assert "MAX_SESIONES=0" in nocturno
    assert "MAX_HORAS=0" in nocturno
    assert "TIMEOUT_MIN=0" in nocturno
    assert (
        "export CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0" in nocturno
    )
    assert 'TIMEOUT_BIN=""' in nocturno
    assert 'run_claude -p \\' in nocturno
    assert 'if [ "$MAX_SESIONES" -gt 0 ] &&' in nocturno
    assert 'if [ "$MAX_HORAS" -gt 0 ] &&' in nocturno
    assert "by_id = {str(f[\"id\"]): f for f in fs}" in nocturno
    assert "deps_done = all(" in nocturno
    assert 'sleep "$retry_wait"' in nocturno
    assert 'reopen_done_feature "$fid"' in nocturno
    assert 'if [ "$sin_cambios" -ge 2 ]; then' not in nocturno
    assert "init.sh en rojo antes de la primera sesión" in nocturno
    assert "falla antes de empezar. Arréglalo y vuelve a lanzar." not in nocturno


def test_locked_command_serializes_writers_and_releases_the_lock(tmp_path):
    lock_helper = ROOT / "scripts" / "run_locked_command.py"
    lock_file = tmp_path / "writer.lock"
    started = tmp_path / "writer_started"
    child = (
        "from pathlib import Path; import time; "
        f"Path({str(started)!r}).write_text('running'); time.sleep(1)"
    )
    command = [
        sys.executable,
        str(lock_helper),
        str(lock_file),
        "0",
        "--",
        sys.executable,
        "-c",
        child,
    ]
    first = subprocess.Popen(
        command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    deadline = time.monotonic() + 5
    while not started.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert started.exists()

    second = subprocess.run(
        [
            sys.executable,
            str(lock_helper),
            str(lock_file),
            "0",
            "--",
            sys.executable,
            "-c",
            "pass",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert second.returncode == 75
    assert "writer OpenCode activo" in second.stderr

    first.communicate(timeout=10)
    assert first.returncode == 0
    assert not lock_file.exists()
    released = subprocess.run(
        [sys.executable, str(lock_helper), str(lock_file), "0", "--", sys.executable, "-c", "pass"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert released.returncode == 0


def test_locked_command_keeps_lock_if_launcher_dies_before_child(tmp_path):
    lock_helper = ROOT / "scripts" / "run_locked_command.py"
    lock_file = tmp_path / "writer.lock"
    started = tmp_path / "child_started"
    child = (
        "from pathlib import Path; import time; "
        f"Path({str(started)!r}).write_text('running'); time.sleep(4)"
    )
    first = subprocess.Popen(
        [
            sys.executable,
            str(lock_helper),
            str(lock_file),
            "0",
            "--",
            sys.executable,
            "-c",
            child,
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 5
    while not started.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert started.exists()

    first.terminate()
    first.wait(timeout=5)

    concurrent = subprocess.run(
        [
            sys.executable,
            str(lock_helper),
            str(lock_file),
            "0",
            "--",
            sys.executable,
            "-c",
            "pass",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert concurrent.returncode == 75, concurrent.stderr

    time.sleep(4)
    released = subprocess.run(
        [
            sys.executable,
            str(lock_helper),
            str(lock_file),
            "0",
            "--",
            sys.executable,
            "-c",
            "pass",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert released.returncode == 0


def test_writer_delegates_to_the_locked_runner():
    writer = (ROOT / "scripts" / "run_opencode_writer.sh").read_text(
        encoding="utf-8"
    )
    assert 'WRITER_LOCK_FILE=".opencode/writer.lock"' in writer
    assert "scripts/run_locked_command.py" in writer


def test_orphan_process_matcher_distinguishes_writer_from_tui():
    helper_path = ROOT / "scripts" / "run_locked_command.py"
    module_spec = importlib.util.spec_from_file_location("run_locked_command", helper_path)
    assert module_spec is not None and module_spec.loader is not None
    helper = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(helper)
    executable = "opencode.exe" if os.name == "nt" else "opencode"

    assert helper._is_opencode_implementer_process(
        executable, f"{executable} run --agent implementer --model deepseek"
    )
    assert not helper._is_opencode_implementer_process(executable, f"{executable} --tui")
    assert not helper._is_opencode_implementer_process(
        "python.exe", "python run_locked_command.py opencode run --agent implementer"
    )


def test_orphan_writer_detection_fails_closed_when_process_query_fails(monkeypatch):
    helper_path = ROOT / "scripts" / "run_locked_command.py"
    module_spec = importlib.util.spec_from_file_location("run_locked_command", helper_path)
    assert module_spec is not None and module_spec.loader is not None
    helper = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(helper)
    commands: list[list[str]] = []

    def failed_query(command, **_kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="query failed")

    monkeypatch.setattr(helper.subprocess, "run", failed_query)
    assert helper._opencode_writer_is_active(ROOT / ".opencode" / "writer.lock")
    if os.name == "nt":
        assert "$ErrorActionPreference = 'Stop'" in " ".join(commands[0])


def test_windows_npm_opencode_shim_resolves_to_the_native_executable(tmp_path):
    helper_path = ROOT / "scripts" / "run_locked_command.py"
    module_spec = importlib.util.spec_from_file_location("run_locked_command", helper_path)
    assert module_spec is not None and module_spec.loader is not None
    helper = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(helper)

    shim = tmp_path / "npm" / "opencode.cmd"
    executable = tmp_path / "npm" / "node_modules" / "opencode-ai" / "bin" / "opencode.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    resolved = helper._resolve_npm_opencode(["opencode", "run"], str(shim))

    assert resolved == [str(executable), "run"]


def test_locked_command_refuses_a_stale_pid_when_orphan_writer_is_detected(
    tmp_path, monkeypatch
):
    helper_path = ROOT / "scripts" / "run_locked_command.py"
    module_spec = importlib.util.spec_from_file_location("run_locked_command", helper_path)
    assert module_spec is not None and module_spec.loader is not None
    helper = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(helper)

    lock_file = tmp_path / "writer.lock"
    lock_file.write_text("0 0\n", encoding="ascii")
    marker = tmp_path / "must_not_start"
    monkeypatch.setattr(helper, "_opencode_writer_is_active", lambda _path: True)
    child = f"from pathlib import Path; Path({str(marker)!r}).touch()"

    result = helper.run_locked_command(
        lock_file, 0, [sys.executable, "-c", child]
    )

    assert result == 75
    assert not marker.exists()


def test_writer_preflight_requires_opencode_go_credential():
    assert _auth_check("● OpenCode Go api")
    assert not _auth_check("● DeepSeek api")
    assert not _auth_check(None, command_fails=True)


def test_writer_accepts_spanish_enye_in_feature_names():
    writer = (ROOT / "scripts" / "run_opencode_writer.sh").read_text(
        encoding="utf-8"
    )
    assert '[[ ! "$FEATURE" =~ ^[a-z0-9_ñ]+$ ]]' in writer
    result = subprocess.run(
        [
            _bash_executable(),
            "-c",
            'FEATURE="rediseño_visual_paneles"; [[ "$FEATURE" =~ ^[a-z0-9_ñ]+$ ]]',
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


def test_claude_modes_enable_agents_and_pin_a_supported_model():
    for name in ("settings.json", "modes/supervisado.json", "modes/nocturno.json"):
        settings = json.loads(
            (ROOT / ".claude" / name).read_text(encoding="utf-8")
        )
        assert settings["model"] == "sonnet"
        assert "Agent" in settings["permissions"]["allow"]


def test_shell_scripts_are_kept_with_lf_endings_on_windows():
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in attrs
