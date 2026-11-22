"""Run a child command while holding a cross-platform, single-writer lock."""
from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator


def _pid_is_alive(pid: int, *, shell_pid: bool = False) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt" and shell_pid:
        try:
            result = subprocess.run(
                ["bash", "-c", 'kill -0 "$1" 2>/dev/null', "writer-lock", str(pid)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return False
        return result.returncode == 0
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return ctypes.get_last_error() != 87
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _owner_pids(lock_file: BinaryIO) -> tuple[int, ...]:
    try:
        lock_file.seek(0)
        values = lock_file.read().decode("ascii").split()
        lock_file.seek(0)
        return tuple(int(value) for value in values)
    except (OSError, ValueError, UnicodeError):
        return ()


def _owner_is_alive(lock_file: BinaryIO) -> bool:
    pids = _owner_pids(lock_file)
    return any(_pid_is_alive(pid, shell_pid=index == 0) for index, pid in enumerate(pids))


def _opencode_writer_is_active(lock_path: Path) -> bool:
    if lock_path.resolve() != Path(".opencode/writer.lock").resolve():
        return False
    try:
        if os.name == "nt":
            command = (
                "$ErrorActionPreference = 'Stop'; try { "
                "Get-CimInstance Win32_Process -Filter \"Name='opencode.exe'\" "
                "| ForEach-Object { Write-Output ($_.Name + [char]9 + $_.CommandLine) }; "
                "exit 0 } catch { exit 1 }"
            )
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command],
                check=False,
                capture_output=True,
                text=True,
            )
        else:
            result = subprocess.run(
                ["ps", "-eo", "comm=,args="],
                check=False,
                capture_output=True,
                text=True,
            )
    except OSError:
        return True
    if result.returncode != 0:
        return True
    for line in result.stdout.splitlines():
        process_name, separator, command_line = line.strip().partition("\t")
        if not separator:
            process_name, _, command_line = line.strip().partition(" ")
        if _is_opencode_implementer_process(process_name, command_line):
            return True
    return False


def _is_opencode_implementer_process(process_name: str, command_line: str) -> bool:
    name = Path(process_name).name.lower()
    expected_name = "opencode.exe" if os.name == "nt" else "opencode"
    return name == expected_name and "run --agent implementer" in command_line.lower()


def _resolve_npm_opencode(command: list[str], shim_path: str) -> list[str]:
    if not command or Path(command[0]).name.lower() not in {"opencode", "opencode.cmd"}:
        return command
    executable = Path(shim_path).parent / "node_modules" / "opencode-ai" / "bin" / "opencode.exe"
    if not executable.is_file():
        return command
    return [str(executable), *command[1:]]


def _resolve_windows_command(command: list[str]) -> list[str]:
    if os.name != "nt" or not command:
        return command
    direct = shutil.which("opencode.exe")
    if direct:
        return [direct, *command[1:]]
    shim = shutil.which("opencode.cmd") or shutil.which("opencode")
    return _resolve_npm_opencode(command, shim) if shim else command


@contextmanager
def _exclusive_guard(guard_path: Path) -> Iterator[object]:
    guard_path.parent.mkdir(parents=True, exist_ok=True)
    with guard_path.open("a+b") as guard:
        guard.seek(0, os.SEEK_END)
        if guard.tell() == 0:
            guard.write(b"\0")
            guard.flush()
        guard.seek(0)
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            try:
                yield guard
            finally:
                guard.seek(0)
                msvcrt.locking(guard.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(guard.fileno(), fcntl.LOCK_EX)
            try:
                yield guard
            finally:
                fcntl.flock(guard.fileno(), fcntl.LOCK_UN)


def _write_owner(lock_file: BinaryIO, owner_pids: tuple[int, ...]) -> None:
    lock_file.seek(0)
    lock_file.truncate()
    lock_file.write((" ".join(str(pid) for pid in owner_pids) + "\n").encode("ascii"))
    lock_file.flush()


def _try_writer_lock(lock_file: BinaryIO) -> bool:
    if os.name == "nt":
        import msvcrt

        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)
        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    import fcntl

    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _release_writer_lock(lock_file: BinaryIO) -> None:
    lock_file.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def run_locked_command(lock_path: Path, owner_shell_pid: int, command: list[str]) -> int:
    command = _resolve_windows_command(command)
    guard_path = lock_path.with_name(f"{lock_path.name}.guard")
    helper_pid = os.getpid()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _exclusive_guard(guard_path):
        lock_file = lock_path.open("a+b")
        if _owner_is_alive(lock_file) or _opencode_writer_is_active(lock_path):
            lock_file.close()
            print("Ya hay un writer OpenCode activo; no inicio otro.", file=sys.stderr)
            return 75
        if not _try_writer_lock(lock_file):
            lock_file.close()
            print("Ya hay un writer OpenCode activo; no inicio otro.", file=sys.stderr)
            return 75
        _write_owner(lock_file, (owner_shell_pid, helper_pid))

    try:
        if os.name == "nt":
            os.set_inheritable(lock_file.fileno(), True)
            child = subprocess.Popen(command, close_fds=False)
            os.set_inheritable(lock_file.fileno(), False)
        else:
            child = subprocess.Popen(command, pass_fds=(lock_file.fileno(),))
        with _exclusive_guard(guard_path):
            _write_owner(lock_file, (owner_shell_pid, helper_pid, child.pid))
        return child.wait()
    except OSError as exc:
        print(f"No pude ejecutar el writer OpenCode: {exc}", file=sys.stderr)
        return 127
    finally:
        with _exclusive_guard(guard_path):
            owners = _owner_pids(lock_file)
            if owners[:2] == (owner_shell_pid, helper_pid):
                _release_writer_lock(lock_file)
                lock_file.close()
                lock_path.unlink(missing_ok=True)
            elif not lock_file.closed:
                _release_writer_lock(lock_file)
                lock_file.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("lock_file", type=Path)
    parser.add_argument("owner_shell_pid", type=int)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("falta el comando que debe ejecutarse bajo el lock")
    return run_locked_command(args.lock_file, args.owner_shell_pid, command)


if __name__ == "__main__":
    raise SystemExit(main())
