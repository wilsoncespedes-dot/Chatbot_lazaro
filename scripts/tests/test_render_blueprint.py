"""Tests del Blueprint de Render y del procedimiento de despliegue (#24)."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT = ROOT / "render.yaml"

SERVICE_NAMES = (
    "telegram-gateway",
    "orchestrator",
    "rag",
    "handover",
    "timeouts-worker",
)
SECRET_KEYS = {
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_WEBHOOK_SECRET",
    "SERVICE_TOKEN",
    "LLM_API_KEY",
    "EMBEDDINGS_API_KEY",
    "DATABASE_URL",
    "REDIS_URL",
    "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_APP_SECRET",
    "WHATSAPP_VERIFY_TOKEN",
}
THIRD_PARTY_SECRETS = {
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_WEBHOOK_SECRET",
    "LLM_API_KEY",
    "EMBEDDINGS_API_KEY",
    "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_APP_SECRET",
    "WHATSAPP_VERIFY_TOKEN",
}


def _blueprint() -> dict:
    return yaml.safe_load(BLUEPRINT.read_text(encoding="utf-8"))


def _services() -> list[dict]:
    return _blueprint()["services"]


def _service(name: str) -> dict:
    return next(service for service in _services() if service["name"] == name)


def _env_var(service: dict, key: str) -> dict:
    return next(
        var for var in service.get("envVars", []) if var.get("key") == key
    )


def _text() -> str:
    return BLUEPRINT.read_text(encoding="utf-8")


def _walk_keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _walk_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_keys(item)


def test_r1_exactly_the_two_public_web_services():
    """R1: solo telegram-gateway y orchestrator son web con /health."""
    web = {service["name"]: service for service in _services() if service["type"] == "web"}
    assert set(web) == {"telegram-gateway", "orchestrator"}
    assert web["telegram-gateway"]["dockerfilePath"] == (
        "services/telegram_gateway/Dockerfile"
    )
    assert web["orchestrator"]["dockerfilePath"] == "services/orchestrator/Dockerfile"
    for service in web.values():
        assert service["healthCheckPath"] == "/health"


def test_r2_private_services_are_only_rag_and_handover():
    """R2: rag y handover son pserv; no hay otros servicios de red."""
    private = {
        service["name"]: service
        for service in _services()
        if service["type"] == "pserv"
    }
    assert set(private) == {"rag", "handover"}
    assert private["rag"]["dockerfilePath"] == "services/rag/Dockerfile"
    assert private["handover"]["dockerfilePath"] == "services/handover/Dockerfile"


def test_r3_worker_uses_handover_image_and_loop_command():
    """R3: timeouts-worker es worker, usa la imagen de handover y el bucle."""
    worker = _service("timeouts-worker")
    assert worker["type"] == "worker"
    assert worker["dockerfilePath"] == "services/handover/Dockerfile"
    assert worker["dockerCommand"] == "python vencer_casos.py --intervalo"


def test_r4_postgres_16_only_private_network():
    """R4: una base Postgres 16 con ipAllowList vacío (solo red privada)."""
    databases = _blueprint()["databases"]
    assert len(databases) == 1
    database = databases[0]
    assert str(database["postgresMajorVersion"]) == "16"
    assert database["ipAllowList"] == []


def test_r5_keyvalue_service_is_private():
    """R5: una instancia keyvalue con ipAllowList vacío."""
    keyvalue = [service for service in _services() if service["type"] == "keyvalue"]
    assert len(keyvalue) == 1
    assert keyvalue[0]["ipAllowList"] == []


def test_r6_every_resource_uses_the_same_region():
    """R6: servicios, base y keyvalue comparten región."""
    data = _blueprint()
    regions = {service["region"] for service in data["services"]}
    regions |= {database["region"] for database in data["databases"]}
    assert len(regions) == 1


def test_r7_no_plan_field_anywhere():
    """R7: el Blueprint no fija planes ni precios."""
    assert "plan" not in set(_walk_keys(_blueprint()))


def test_r8_secrets_have_no_literal_values():
    """R8: ningún secreto lleva `value` literal; los de terceros usan sync:false."""
    data = _blueprint()
    all_vars = [
        var for service in data["services"] for var in service.get("envVars", [])
    ]
    all_vars += [
        var
        for group in data.get("envVarGroups", [])
        for var in group.get("envVars", [])
    ]
    for var in all_vars:
        if var.get("key") in SECRET_KEYS:
            assert "value" not in var, var
    for var in all_vars:
        if var.get("key") in THIRD_PARTY_SECRETS:
            assert var.get("sync") is False, var


def test_r9_shared_env_group_provides_generated_service_token():
    """R9: SERVICE_TOKEN se genera en un env group enlazado por los cinco servicios."""
    group = next(
        group
        for group in _blueprint()["envVarGroups"]
        if any(var.get("key") == "SERVICE_TOKEN" for var in group["envVars"])
    )
    token = next(var for var in group["envVars"] if var["key"] == "SERVICE_TOKEN")
    assert token.get("generateValue") is True
    for name in SERVICE_NAMES:
        assert any(
            var.get("fromGroup") == group["name"]
            for var in _service(name).get("envVars", [])
        ), name


def test_r10_database_and_redis_use_resource_references():
    """R10: DATABASE_URL viene de la base y REDIS_URL del keyvalue."""
    database_url = _env_var(_service("orchestrator"), "DATABASE_URL")
    assert database_url["fromDatabase"]["property"] == "connectionString"
    redis_url = _env_var(_service("telegram-gateway"), "REDIS_URL")
    assert redis_url["fromService"]["type"] == "keyvalue"
    assert redis_url["fromService"]["property"] == "connectionString"


def test_r11_internal_urls_use_hostport_references():
    """R11: las URLs internas salen de fromService hostport, sin literales."""
    expected = {
        ("telegram-gateway", "ORCHESTRATOR_URL"): "web",
        ("orchestrator", "RAG_URL"): "pserv",
        ("orchestrator", "HANDOVER_URL"): "pserv",
        ("orchestrator", "TELEGRAM_GATEWAY_URL"): "web",
        ("handover", "TELEGRAM_GATEWAY_URL"): "web",
        ("timeouts-worker", "HANDOVER_URL"): "pserv",
    }
    for (service_name, key), source_type in expected.items():
        var = _env_var(_service(service_name), key)
        assert var["fromService"]["type"] == source_type
        assert var["fromService"]["property"] == "hostport"
        assert "value" not in var
    assert "http://" not in _text()
    assert "https://" not in _text()


def test_r32_orchestrator_trusts_proxy_headers_and_shared_group_does_not():
    """R32: solo el orchestrator define ADMIN_TRUST_PROXY_HEADERS=true."""
    variable = _env_var(_service("orchestrator"), "ADMIN_TRUST_PROXY_HEADERS")
    assert variable["value"] == "true"
    for group in _blueprint()["envVarGroups"]:
        assert all(
            var.get("key") != "ADMIN_TRUST_PROXY_HEADERS" for var in group["envVars"]
        )


def test_expiry_notice_worker_uses_handover_image_and_loop():
    """R60: el worker de avisos usa la imagen de handover y el bucle."""
    worker = _service("expiry-notice-worker")
    assert worker["type"] == "worker"
    assert worker["dockerfilePath"] == "services/handover/Dockerfile"
    assert worker["dockerCommand"] == "python avisar_vencimientos.py --intervalo"
    assert _env_var(worker, "ORCHESTRATOR_URL")["fromService"]["type"] == "web"
    assert _env_var(worker, "EXPIRY_NOTICE_INTERVAL_SECONDS")["value"] == "3600"
    assert _env_var(worker, "EXPIRY_NOTICE_HTTP_TIMEOUT_SECONDS")["value"] == "120"


def test_r28_deployment_procedure_documents_every_step():
    """R28: docs/despliegue.md describe Blueprint, secretos, vector, webhook y /health."""
    text = (ROOT / "docs" / "despliegue.md").read_text(encoding="utf-8").lower()
    for expected in ("blueprint", "sync: false", "vector", "webhook", "/health"):
        assert expected in text
