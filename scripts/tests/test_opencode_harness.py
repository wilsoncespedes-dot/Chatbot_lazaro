"""Pruebas de coherencia del puente OpenCode/DeepSeek y el modo nocturno."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
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
