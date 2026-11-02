"""Tests del worker de retención y su configuración en Render (#28)."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT = ROOT / "render.yaml"
DOCS = ROOT / "docs" / "despliegue.md"
ENV_EXAMPLE = ROOT / ".env.example"
DOCKERFILE = ROOT / "services" / "handover" / "Dockerfile"

WORKER = "retention-worker"
NOTICE_KEYS = (
    "PRIVACY_NOTICE_TEXT",
    "PRIVACY_NOTICE_VERSION",
    "PRIVACY_ACCEPT_PHRASE",
    "PRIVACY_ACCEPTED_REPLY",
)
MECHANISM_KEYS = (
    "PRIVACY_PURGE_INTERVAL_SECONDS",
    "PRIVACY_PURGE_HTTP_TIMEOUT_SECONDS",
)
OWNER_KEYS = NOTICE_KEYS + ("PRIVACY_RETENTION_DAYS", "PRIVACY_ACTIVE_CASE_MAX_DAYS")


def _blueprint() -> dict:
    return yaml.safe_load(BLUEPRINT.read_text(encoding="utf-8"))


def _services() -> list[dict]:
    return _blueprint()["services"]


def _service(name: str) -> dict:
    return next(service for service in _services() if service["name"] == name)


def _env_var(service: dict, key: str) -> dict:
    return next(var for var in service.get("envVars", []) if var.get("key") == key)


def _all_env_vars() -> list[tuple[str, dict]]:
    data = _blueprint()
    entries = [
        (service["name"], var)
        for service in data["services"]
        for var in service.get("envVars", [])
    ]
    entries += [
        (group["name"], var)
        for group in data.get("envVarGroups", [])
        for var in group.get("envVars", [])
    ]
    return entries


def _docs_text() -> str:
    """Markdown con saltos de línea normalizados para no partir frases."""
    return " ".join(DOCS.read_text(encoding="utf-8").split())


def _env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def test_r1_retention_worker_uses_handover_image_in_shared_region():
    """R1: retention-worker es un worker docker con la imagen de handover."""
    worker = _service(WORKER)
    assert worker["type"] == "worker"
    assert worker["runtime"] == "docker"
    assert worker["dockerContext"] == "."
    assert worker["dockerfilePath"] == "services/handover/Dockerfile"
    regions = {service["region"] for service in _services()}
    assert worker["region"] in regions
    assert len(regions) == 1


def test_r2_retention_worker_runs_interval_loop():
    """R2: el worker ejecuta purgar_datos.py en modo bucle."""
    assert _service(WORKER)["dockerCommand"] == "python purgar_datos.py --intervalo"


def test_r3_handover_image_copies_purge_script_to_workdir():
    """R3: el Dockerfile copia el script al directorio de trabajo del comando."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY scripts/purgar_datos.py ./purgar_datos.py" in text
    assert "WORKDIR /app" in text


def test_r4_retention_worker_has_no_public_surface():
    """R4: ni health check ni puerto ni dominio; solo dos servicios web."""
    worker = _service(WORKER)
    assert "healthCheckPath" not in worker
    assert "port" not in worker
    assert "domains" not in worker
    web = {service["name"] for service in _services() if service["type"] == "web"}
    assert web == {"telegram-gateway", "orchestrator"}


def test_r5_retention_worker_joins_shared_env_group():
    """R5: el worker enlaza el env group lazaro-compartido."""
    groups = [
        var.get("fromGroup")
        for var in _service(WORKER).get("envVars", [])
        if "key" not in var
    ]
    assert "lazaro-compartido" in groups


def test_r6_handover_url_is_a_private_service_reference():
    """R6: HANDOVER_URL sale de fromService pserv hostport, sin value."""
    var = _env_var(_service(WORKER), "HANDOVER_URL")
    assert var["fromService"] == {
        "type": "pserv",
        "name": "handover",
        "property": "hostport",
    }
    assert "value" not in var


def test_r7_orchestrator_url_is_a_web_service_reference():
    """R7: ORCHESTRATOR_URL sale de fromService web hostport, sin value."""
    var = _env_var(_service(WORKER), "ORCHESTRATOR_URL")
    assert var["fromService"] == {
        "type": "web",
        "name": "orchestrator",
        "property": "hostport",
    }
    assert "value" not in var


def test_r8_retention_worker_matches_env_example_mechanism_values():
    """R8: las variables del mecanismo copian los valores de .env.example."""
    expected = _env_example()
    for key in MECHANISM_KEYS:
        assert _env_var(_service(WORKER), key)["value"] == expected[key]


def test_r9_retention_worker_has_minimum_privileges():
    """R9: el worker no recibe base de datos ni plazos de privacidad."""
    variables = _service(WORKER).get("envVars", [])
    keys = {var["key"] for var in variables if "key" in var}
    assert "DATABASE_URL" not in keys
    assert "REDIS_URL" not in keys
    privacy_keys = {key for key in keys if key.startswith("PRIVACY_")}
    assert privacy_keys == set(MECHANISM_KEYS)
    allowed = set(MECHANISM_KEYS) | {"HANDOVER_URL", "ORCHESTRATOR_URL"}
    for var in variables:
        if "key" in var:
            assert var["key"] in allowed, var


def test_r10_orchestrator_requests_notice_values_from_panel():
    """R10: el orchestrator pide las cuatro variables del aviso con sync: false."""
    orchestrator = _service("orchestrator")
    for key in NOTICE_KEYS:
        var = _env_var(orchestrator, key)
        assert var.get("sync") is False, var
        assert "value" not in var, var


def test_r11_handover_requests_retention_values_from_panel():
    """R11: handover pide retención y antigüedad de casos activos con sync: false."""
    handover = _service("handover")
    for key in ("PRIVACY_RETENTION_DAYS", "PRIVACY_ACTIVE_CASE_MAX_DAYS"):
        var = _env_var(handover, key)
        assert var.get("sync") is False, var
        assert "value" not in var, var


def test_r12_orchestrator_references_handover_retention_days():
    """R12: el orchestrator hereda PRIVACY_RETENTION_DAYS de handover por envVarKey."""
    var = _env_var(_service("orchestrator"), "PRIVACY_RETENTION_DAYS")
    assert var["fromService"] == {
        "type": "pserv",
        "name": "handover",
        "envVarKey": "PRIVACY_RETENTION_DAYS",
    }
    assert "property" not in var["fromService"]
    assert "value" not in var
    assert "sync" not in var
    declared = _env_var(_service("handover"), "PRIVACY_RETENTION_DAYS")
    assert declared["key"] == var["fromService"]["envVarKey"]


def test_r13_retention_days_has_a_single_source():
    """R13: solo handover declara PRIVACY_RETENTION_DAYS; el resto lo referencia."""
    entries = [
        (owner, var)
        for owner, var in _all_env_vars()
        if var.get("key") == "PRIVACY_RETENTION_DAYS"
    ]
    sources = [owner for owner, var in entries if var.get("sync") is False]
    assert sources == ["handover"]
    references = [owner for owner, var in entries if "fromService" in var]
    assert references == ["orchestrator"]
    assert len(entries) == 2


def test_r14_owner_values_are_never_written_in_the_blueprint():
    """R14: las seis variables legales no llevan value ni generateValue."""
    for owner, var in _all_env_vars():
        if var.get("key") in OWNER_KEYS:
            assert "value" not in var, (owner, var)
            assert "generateValue" not in var, (owner, var)


def test_r15_unrelated_resources_do_not_declare_privacy_variables():
    """R15: gateway, rag, timeouts-worker y env groups no tienen PRIVACY_*."""
    data = _blueprint()
    for name in ("telegram-gateway", "rag", "timeouts-worker"):
        assert all(
            not var.get("key", "").startswith("PRIVACY_")
            for var in _service(name).get("envVars", [])
        ), name
    for group in data.get("envVarGroups", []):
        assert all(
            not var.get("key", "").startswith("PRIVACY_")
            for var in group.get("envVars", [])
        ), group["name"]


def test_r16_orchestrator_does_not_receive_active_case_max_days():
    """R16: el orchestrator no recibe PRIVACY_ACTIVE_CASE_MAX_DAYS."""
    keys = {
        var.get("key")
        for var in _service("orchestrator").get("envVars", [])
    }
    assert "PRIVACY_ACTIVE_CASE_MAX_DAYS" not in keys


def test_r17_docs_list_retention_worker():
    """R17: docs/despliegue.md describe el worker, su orden y que no expone puertos."""
    text = _docs_text()
    assert "retention-worker" in text
    assert "python purgar_datos.py --intervalo" in text
    assert "purga primero `handover` y después `orchestrator`" in text
    assert "No expone puertos" in text


def test_r18_docs_table_lists_every_sync_false_variable():
    """R18: la tabla de variables incluye las seis variables con su servicio."""
    text = _docs_text()
    expected = {
        "PRIVACY_NOTICE_TEXT": "orchestrator",
        "PRIVACY_NOTICE_VERSION": "orchestrator",
        "PRIVACY_ACCEPT_PHRASE": "orchestrator",
        "PRIVACY_ACCEPTED_REPLY": "orchestrator",
        "PRIVACY_RETENTION_DAYS": "handover",
        "PRIVACY_ACTIVE_CASE_MAX_DAYS": "handover",
    }
    for key, service in expected.items():
        assert f"| `{key}` | {service} |" in text, key


def test_r19_docs_explain_single_retention_source():
    """R19: un solo PRIVACY_RETENTION_DAYS y redespliegue de ambos servicios."""
    text = _docs_text()
    assert "solo en `handover`" in text
    assert "hereda por referencia" in text
    assert "redesplegar" in text
    assert "ambos" in text


def test_r20_docs_explain_active_case_limit():
    """R20: active < retention y cierre sin avisar a cliente ni asesor."""
    text = _docs_text()
    assert "estrictamente menor que" in text
    assert "`PRIVACY_RETENTION_DAYS`" in text
    assert "cierra" in text
    assert "borra" in text
    assert "sin avisar al cliente ni al asesor" in text


def test_r21_docs_states_owner_defined_values_and_startup_block():
    """R21: los valores los define el propietario con revisión legal."""
    text = _docs_text()
    assert "propietario" in text
    assert "revisión legal" in text
    assert "antes de desplegar" in text
    assert "no arrancan en producción" in text


def test_r22_docs_contain_no_retention_numeric_example():
    """R22: ningún plazo de retención aparece con valor numérico de ejemplo."""
    text = _docs_text()
    assert re.search(r"PRIVACY_(RETENTION|ACTIVE_CASE_MAX)_DAYS\s*[=:]\s*\d", text) is None


def test_r23_docs_list_uncovered_personal_data():
    """R23: la purga no cubre logs, copias, consentimientos ni supresiones."""
    text = _docs_text()
    assert "logs" in text
    assert "copias de seguridad" in text
    assert "privacy_consents" in text
    assert "supresión" in text
    assert "revocación" in text
