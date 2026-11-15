"""Repositorio del segundo factor y sesiones restringidas (#54)."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from orchestrator.adapters.repository import FakeRepository

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _repo_with_profile() -> tuple[FakeRepository, str]:
    repo = FakeRepository()
    profile = repo.create_profile("ana", "admin", "hash", NOW)
    return repo, profile.id


def test_activation_and_step_advance_are_monotonic():
    """R17, R18, R19, R20: el paso solo avanza y nunca se repite."""
    repo, profile_id = _repo_with_profile()
    assert repo.save_pending_two_factor(profile_id, "cifrado", NOW) is True
    assert repo.activate_two_factor(profile_id, 100, ["h1"], NOW) is True
    record = repo.get_two_factor(profile_id)
    assert record is not None and record.enabled_at == NOW
    assert record.last_used_step == 100
    assert repo.advance_two_factor_step(profile_id, 100) is False
    assert repo.advance_two_factor_step(profile_id, 99) is False
    assert repo.advance_two_factor_step(profile_id, 101) is True
    assert repo.advance_two_factor_step(profile_id, 101) is False


def test_concurrent_same_step_advance_accepts_only_one():
    """R19: dos verificaciones concurrentes del mismo paso aceptan como máximo una."""
    repo, profile_id = _repo_with_profile()
    repo.save_pending_two_factor(profile_id, "cifrado", NOW)
    repo.activate_two_factor(profile_id, 10, [], NOW)
    barrier = threading.Barrier(2)
    results: list[bool] = []
    lock = threading.Lock()

    def worker():
        barrier.wait(timeout=5)
        result = repo.advance_two_factor_step(profile_id, 11)
        with lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert sorted(results) == [False, True]


def test_save_pending_never_replaces_an_active_secret():
    """R8: con el factor activo no se cambia el secreto."""
    repo, profile_id = _repo_with_profile()
    repo.save_pending_two_factor(profile_id, "primero", NOW)
    repo.activate_two_factor(profile_id, 1, ["h1"], NOW)
    assert repo.save_pending_two_factor(profile_id, "segundo", NOW) is False
    record = repo.get_two_factor(profile_id)
    assert record is not None and record.secret_ciphertext == "primero"


def test_recovery_codes_are_single_use():
    """R32, R33: un código solo se consume una vez."""
    repo, profile_id = _repo_with_profile()
    repo.save_pending_two_factor(profile_id, "cifrado", NOW)
    repo.activate_two_factor(profile_id, 1, ["hash-a", "hash-b"], NOW)
    assert repo.consume_recovery_code(profile_id, "hash-a", NOW) is True
    assert repo.consume_recovery_code(profile_id, "hash-a", NOW) is False
    assert repo.consume_recovery_code("otro", "hash-b", NOW) is False
    assert repo.consume_recovery_code(profile_id, "hash-b", NOW) is True


def test_delete_two_factor_removes_secret_and_codes():
    """R35: el restablecimiento borra secreto y códigos."""
    repo, profile_id = _repo_with_profile()
    repo.save_pending_two_factor(profile_id, "cifrado", NOW)
    repo.activate_two_factor(profile_id, 1, ["hash-a"], NOW)
    assert repo.delete_two_factor(profile_id) is True
    assert repo.get_two_factor(profile_id) is None
    assert repo.consume_recovery_code(profile_id, "hash-a", NOW) is False
    assert repo.delete_two_factor(profile_id) is False


def test_restricted_sessions_are_hidden_from_normal_reads():
    """R23, R24: get_session y get_session_for_roles excluyen sesiones restringidas."""
    repo, profile_id = _repo_with_profile()
    repo.create_session("restringida", profile_id, "csrf", NOW + timedelta(hours=1), True)
    assert repo.get_session_any("restringida", NOW) is not None
    assert repo.get_session("restringida", NOW) is None
    assert repo.get_session_for_roles("restringida", NOW, ["admin"]) is None
    repo.promote_session("restringida")
    assert repo.get_session("restringida", NOW) is not None


def test_delete_sessions_for_profile_can_keep_current():
    """R25: se conserva solo la sesión que confirmó el registro."""
    repo, profile_id = _repo_with_profile()
    other = repo.create_profile("bea", "admin", "hash", NOW)
    repo.create_session("actual", profile_id, "csrf", NOW + timedelta(hours=1))
    repo.create_session("otra", profile_id, "csrf2", NOW + timedelta(hours=1))
    repo.create_session("ajena", other.id, "csrf3", NOW + timedelta(hours=1))
    repo.delete_sessions_for_profile(profile_id, keep_token_hash="actual")
    assert set(repo.sessions) == {"actual", "ajena"}
