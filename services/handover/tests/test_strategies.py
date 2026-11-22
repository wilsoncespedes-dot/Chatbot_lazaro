"""Estrategias de asignación automática en handover (feature #69)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from lazaro_contracts import ASSIGNMENT_STRATEGIES, CaseAutoAssignRequest, ErrorResponse

from handover.domain import auto_assign_case
from handover.strategies import (
    ESTRATEGIAS,
    ContextoAsignacion,
    RoundRobin,
    obtener_estrategia,
    registrar_estrategia,
)

HEADERS = {"X-Service-Token": "svc-token"}
CANDIDATES = ["111", "222", "333"]


def _auto(
    env,
    case_id: str = "case-1",
    candidate_ids: list[str] | None = None,
    strategy: str = "por_carga",
):
    return env.client.post(
        f"/cases/{case_id}/auto-assign",
        json={
            "candidate_ids": CANDIDATES if candidate_ids is None else candidate_ids,
            "strategy": strategy,
        },
        headers=HEADERS,
    )


def test_interfaz_estrategia_elige_entre_candidatos():
    """R1: la interfaz expone `elegir(candidatos, contexto)` que devuelve un candidato."""
    estrategia = obtener_estrategia("por_carga")
    elegido = estrategia.elegir(
        ["111", "222"], ContextoAsignacion(cargas={"111": 1}, ultimo=None)
    )
    assert elegido in {"111", "222"}
    assert elegido == "222"


def test_por_carga_regression(env):
    """R2: por_carga elige menos carga y desempata por el menor advisor_id."""
    env.add_case("busy-1", status="assigned", advisor_id="111", assigned_at=env.clock())
    env.add_case("busy-2", status="assigned", advisor_id="111", assigned_at=env.clock())
    env.add_case("busy-3", status="assigned", advisor_id="222", assigned_at=env.clock())
    env.add_case("case-1", status="open")

    response = _auto(env, candidate_ids=CANDIDATES, strategy="por_carga")

    assert response.status_code == 200
    assert response.json() == {
        "status": "assigned",
        "case_id": "case-1",
        "advisor_id": "333",
    }
    assert env.repo.cases["case-1"].advisor_id == "333"
    assert obtener_estrategia("por_carga").elegir(
        ["333", "222", "111"], ContextoAsignacion(cargas={}, ultimo=None)
    ) == "111"


def test_round_robin_reparte_en_orden_y_vuelve_al_inicio(env):
    """R3: rota en orden lexicográfico y vuelve al primer candidato."""
    for index in range(4):
        env.add_case(f"case-{index}", status="open")

    chosen = []
    for index in range(4):
        response = _auto(env, case_id=f"case-{index}", strategy="round_robin")
        assert response.status_code == 200
        chosen.append(response.json()["advisor_id"])

    assert chosen == ["111", "222", "333", "111"]
    assert env.repo.pointers["round_robin"] == "111"


def test_round_robin_salta_no_validos(env):
    """R10, R11: ignora candidatos no válidos y salta al siguiente del turno."""
    env.repo.pointers["round_robin"] = "111"
    env.add_case("case-1", status="open")

    response = _auto(
        env, candidate_ids=["999", "222", "333", "222"], strategy="round_robin"
    )

    assert response.status_code == 200
    assert response.json()["advisor_id"] == "222"
    assert env.repo.pointers["round_robin"] == "222"

    env.add_case("case-2", status="open")
    next_response = _auto(
        env, case_id="case-2", candidate_ids=["111", "333"], strategy="round_robin"
    )
    assert next_response.json()["advisor_id"] == "333"


def test_puntero_persiste_y_no_cambia_si_skipped(env, env_factory):
    """R6, R8: el puntero sobrevive a un reinicio y no cambia si la escritura no ocurre."""
    env.add_case("case-1", status="open")
    assert _auto(env, strategy="round_robin").json()["advisor_id"] == "111"
    assert env.repo.pointers["round_robin"] == "111"

    restarted = env_factory(repo=env.repo)
    restarted.add_case("case-2", status="open")
    response = _auto(restarted, case_id="case-2", strategy="round_robin")
    assert response.json()["advisor_id"] == "222"
    assert restarted.repo.pointers["round_robin"] == "222"

    restarted.add_case(
        "case-taken", status="assigned", advisor_id="111", assigned_at=restarted.clock()
    )
    skipped = _auto(restarted, case_id="case-taken", strategy="round_robin")

    assert skipped.status_code == 200
    assert skipped.json() == {
        "status": "skipped",
        "case_id": "case-taken",
        "advisor_id": "111",
    }
    assert restarted.repo.pointers["round_robin"] == "222"


def test_round_robin_concurrente_sin_repetir(env):
    """R7, R9: solicitudes concurrentes no repiten ni saltan asesores del turno."""
    case_ids = [f"case-{index}" for index in range(6)]
    for case_id in case_ids:
        env.add_case(case_id, status="open")
    request = CaseAutoAssignRequest(
        candidate_ids=CANDIDATES, strategy="round_robin"
    )

    def assign(case_id: str):
        return auto_assign_case(case_id, request, env.settings, env.adapters)

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(assign, case_ids))

    assert sorted(result.status for result in results) == ["assigned"] * 6
    advisors = [env.repo.cases[case_id].advisor_id for case_id in case_ids]
    counts = {advisor_id: advisors.count(advisor_id) for advisor_id in CANDIDATES}
    assert counts == {"111": 2, "222": 2, "333": 2}
    assert env.repo.pointers["round_robin"] in set(CANDIDATES)


def test_registro_sin_ramas_estrategia_nueva(env):
    """R4: una clase registrada se usa sin ramas por nombre en el flujo."""

    @registrar_estrategia
    class _EstrategiaDePrueba:
        nombre = "estrategia_de_prueba"

        def elegir(self, candidatos, contexto):
            return candidatos[-1]

    try:
        assert isinstance(obtener_estrategia("estrategia_de_prueba"), _EstrategiaDePrueba)
        env.add_case("case-1", status="open")
        response = _auto(
            env,
            candidate_ids=["111", "222"],
            strategy="estrategia_de_prueba",
        )
        assert response.status_code == 200
        assert response.json()["advisor_id"] == "222"
        assert env.repo.pointers["estrategia_de_prueba"] == "222"
    finally:
        ESTRATEGIAS.pop("estrategia_de_prueba", None)


def test_registro_coincide_con_contrato():
    """R4: el registro y la constante del contrato enumeran las mismas estrategias."""
    assert set(ESTRATEGIAS) == set(ASSIGNMENT_STRATEGIES)
    assert isinstance(ESTRATEGIAS["round_robin"], RoundRobin)


def test_estrategia_desconocida_422(env):
    """R5: una estrategia no registrada responde 422 sin modificar el caso."""
    env.add_case("case-1", status="open")

    response = _auto(env, strategy="no_existe")

    assert response.status_code == 422
    ErrorResponse.model_validate(response.json())
    assert response.json()["error"] == "validation_error"
    assert env.repo.cases["case-1"].status == "open"
    assert env.repo.auto_assignments == []
    assert env.repo.pointers == {}


def test_sin_candidatos_queued_sin_tocar_puntero(env):
    """R14: sin candidatos válidos responde queued y no toca el puntero."""
    env.repo.pointers["round_robin"] = "111"
    env.add_case("case-1", status="open")

    response = _auto(env, candidate_ids=["999", "otro"], strategy="round_robin")

    assert response.status_code == 200
    assert response.json() == {
        "status": "queued",
        "case_id": "case-1",
        "advisor_id": None,
    }
    assert env.repo.cases["case-1"].status == "open"
    assert env.repo.pointers == {"round_robin": "111"}
    assert env.repo.auto_assignments == []


def test_caso_asignado_por_persona_skipped(env):
    """R13: un caso ya asignado por una persona no se modifica y responde skipped."""
    env.add_case(
        "case-1", status="assigned", advisor_id="111", assigned_at=env.clock()
    )

    response = _auto(env, strategy="round_robin")

    assert response.status_code == 200
    assert response.json() == {
        "status": "skipped",
        "case_id": "case-1",
        "advisor_id": "111",
    }
    assert env.repo.pointers == {}
    assert env.repo.auto_assignments == []
