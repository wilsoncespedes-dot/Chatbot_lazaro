"""Importación de clientes desde CSV (#77)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

from orchestrator.accounts import hash_token, verify_password
from orchestrator.adapters.repository import FakeRepository
from migrations import section

_SCHEMA = section("orchestrator: tablas")
_INDEXES = section("orchestrator: índices")
_MIGRATIONS = section("orchestrator: migraciones aditivas previas")
from orchestrator.client_import import (
    ImportFileError,
    ImportPlan,
    ImportRow,
    ImportStaging,
    ImportSummary,
    build_plan,
    csv_safe,
    parse_csv,
    run_import,
    summary_to_csv,
)
from orchestrator.client_source import FuenteClientesLocal
from orchestrator.domain import Profile
from orchestrator.identity import credential_allows_access, credential_status

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
PUBLIC_ID = "ABCD-2345"
CSV_HEADER = "id,usuario,correo,telefono\n"
CSV_ROW = "ABCD-2345,ana,ana@example.com,+34600123456\n"


def _source(repo: FakeRepository) -> FuenteClientesLocal:
    return FuenteClientesLocal(repo)


def _create(
    repo: FakeRepository,
    username: str,
    public_id: str,
    *,
    email: str | None = None,
    phone: str | None = None,
) -> Profile:
    return repo.create_client_credential(
        username,
        "hash",
        NOW,
        NOW + timedelta(days=30),
        NOW,
        public_id=public_id,
        email=email,
        phone=phone,
    )


def _row(
    number: int,
    *,
    id_value: str | None = None,
    usuario: str = "ana",
    correo: str | None = None,
    telefono: str | None = None,
    status: str = "nueva",
    reason: str | None = None,
    existing: str | None = None,
    errors=(),
) -> ImportRow:
    return ImportRow(
        number=number,
        id=id_value,
        usuario=usuario,
        correo=correo,
        telefono=telefono,
        errors=tuple(errors),
        status=status,  # type: ignore[arg-type]
        reason=reason,
        existing_profile_id=existing,
    )


def _upload(env, content: bytes, csrf: str = "csrf-token"):
    return env.client.post(
        "/admin/clientes/importar/vista-previa",
        data={"csrf_token": csrf},
        files={"archivo": ("clientes.csv", content, "text/csv")},
    )


def _token(html: str) -> str:
    match = re.search(r'name="token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


# --- T13: parseo ---------------------------------------------------------------


def test_parse_comma_and_semicolon():
    """R4, R5: coma y punto y coma producen las mismas filas."""
    comma = parse_csv(
        (CSV_HEADER + CSV_ROW).encode(), max_bytes=10000, max_rows=10
    )
    semicolon = parse_csv(
        b"id;usuario;correo;telefono\n"
        b"ABCD-2345;ana;ana@example.com;+34600123456\n",
        max_bytes=10000,
        max_rows=10,
    )
    expected = [
        {
            "id": "ABCD-2345",
            "usuario": "ana",
            "correo": "ana@example.com",
            "telefono": "+34600123456",
        }
    ]
    assert comma == expected
    assert semicolon == expected


def test_bom_and_non_utf8():
    """R4, R6: el BOM es aceptado y un archivo no UTF-8 se rechaza."""
    with_bom = b"\xef\xbb\xbf" + (CSV_HEADER + CSV_ROW).encode()
    assert parse_csv(with_bom, max_bytes=10000, max_rows=10)[0]["usuario"] == "ana"

    with pytest.raises(ImportFileError) as error:
        parse_csv(b"\xff\xfe\x00bad", max_bytes=10000, max_rows=10)
    assert error.value.code == "archivo_no_utf8"


@pytest.mark.parametrize(
    "header",
    [
        "id,correo\n",
        "usuario,password\n",
        "usuario,contrasena\n",
        "usuario,extra\n",
        "usuario,usuario\n",
    ],
)
def test_header_rejects_unknown_and_password_columns(header):
    """R7, R11: columnas desconocidas, contraseñas y duplicadas se rechazan."""
    with pytest.raises(ImportFileError) as error:
        parse_csv((header + "valor\n").encode(), max_bytes=10000, max_rows=10)
    assert error.value.code == "encabezado_invalido"


def test_size_and_rows_limits():
    """R8, R9: tamaño máximo y filas máximas se comprueban sin vista previa."""
    with pytest.raises(ImportFileError) as size_error:
        parse_csv(b"x" * 101, max_bytes=100, max_rows=10)
    assert size_error.value.code == "archivo_demasiado_grande"

    three_rows = CSV_HEADER + "".join(
        f"ABCD-234{i},ana{i},ana{i}@example.com,\n" for i in range(1, 4)
    )
    with pytest.raises(ImportFileError) as rows_error:
        parse_csv(three_rows.encode(), max_bytes=10000, max_rows=2)
    assert rows_error.value.code == "demasiadas_filas"

    two_rows = CSV_HEADER + "".join(
        f"ABCD-234{i},ana{i},ana{i}@example.com,\n" for i in range(1, 3)
    )
    assert len(parse_csv(two_rows.encode(), max_bytes=10000, max_rows=2)) == 2


# --- T14: validación y normalización ------------------------------------------


def test_invalid_usuario_id_correo_telefono_per_field():
    """R13-R16: cada campo inválido se marca por separado."""
    plan = build_plan(
        [{"id": "XX", "usuario": "ab", "correo": "malo", "telefono": "12"}],
        _source(FakeRepository()),
    )
    row = plan.rows[0]
    assert row.status == "invalida"
    assert {(error.field, error.code) for error in row.errors} == {
        ("usuario", "usuario_invalido"),
        ("id", "id_invalido"),
        ("correo", "correo_invalido"),
        ("telefono", "telefono_invalido"),
    }


def test_normalization():
    """R18: ID, correo y teléfono se normalizan antes de comparar o guardar."""
    plan = build_plan(
        [
            {
                "id": "abcd efgh",
                "usuario": "  Ana  ",
                "correo": "  ANA@Example.COM ",
                "telefono": "+34 600-123-456",
            }
        ],
        _source(FakeRepository()),
    )
    row = plan.rows[0]
    assert row.id == "ABCD-EFGH"
    assert row.usuario == "ana"
    assert row.correo == "ana@example.com"
    assert row.telefono == "+34600123456"
    assert row.errors == ()


def test_preview_lists_all_errors_per_row(env, panel):
    """R12, R17: la vista previa muestra todos los errores de cada fila."""
    panel.login_admin(env)
    response = _upload(
        env,
        (CSV_HEADER + "XX,ab,malo,12\n").encode(),
    )
    assert response.status_code == 200
    for code in (
        "usuario_invalido",
        "id_invalido",
        "correo_invalido",
        "telefono_invalido",
    ):
        assert code in response.text


# --- T15: duplicados -----------------------------------------------------------


def test_duplicate_by_id_email_phone_in_base():
    """R19-R21: duplicados de base por ID, correo y teléfono."""
    repo = FakeRepository()
    _create(repo, "uno", "ABCD-2345", email="a@example.com", phone="+1111111")
    _create(repo, "dos", "EFGH-2345", email="b@example.com", phone="+2222222")
    _create(repo, "tres", "JKMN-2345", email="c@example.com", phone="+3333333")
    plan = build_plan(
        [
            {
                "id": "ABCD2345",
                "usuario": "nuevo1",
                "correo": "n1@example.com",
                "telefono": "+1111111",
            },
            {"id": "", "usuario": "nuevo2", "correo": "b@example.com", "telefono": ""},
            {"id": "", "usuario": "nuevo3", "correo": "", "telefono": "+3333333"},
        ],
        _source(repo),
    )
    assert [row.status for row in plan.rows] == ["duplicado_base"] * 3
    assert [row.reason for row in plan.rows] == ["id", "correo", "telefono"]


def test_duplicate_in_file():
    """R22: repetir id, correo, teléfono o usuario se marca con la fila de origen."""
    plan = build_plan(
        [
            {
                "id": "ABCD-2345",
                "usuario": "ana",
                "correo": "ana@example.com",
                "telefono": "+34600123456",
            },
            {
                "id": "ABCD2345",
                "usuario": "bea",
                "correo": "bea@example.com",
                "telefono": "+34600123457",
            },
        ],
        _source(FakeRepository()),
    )
    assert plan.rows[0].status == "nueva"
    assert plan.rows[1].status == "duplicado_archivo"
    assert "id" in (plan.rows[1].reason or "") and "fila 1" in (
        plan.rows[1].reason or ""
    )


def test_conflict_two_existing_clients():
    """R23: dos clientes distintos por claves diferentes es conflicto."""
    repo = FakeRepository()
    _create(repo, "uno", "ABCD-2345", email="one@example.com")
    _create(repo, "dos", "EFGH-2345", email="two@example.com")
    plan = build_plan(
        [
            {
                "id": "ABCD-2345",
                "usuario": "nuevo",
                "correo": "two@example.com",
                "telefono": "",
            }
        ],
        _source(repo),
    )
    assert plan.rows[0].status == "conflicto"
    assert plan.rows[0].reason == "conflicto_multiple"
    summary = run_import(plan, "actualizar", _source(repo), NOW)
    assert summary.failed == 1 and summary.updated == 0
    uno = next(p for p in repo.profiles.values() if p.username == "uno")
    assert uno.email == "one@example.com"


def test_policy_default_is_skip(env, panel):
    """R24: una única elección y «Saltar» preseleccionado."""
    panel.login_admin(env)
    response = _upload(env, (CSV_HEADER + CSV_ROW).encode())
    assert response.status_code == 200
    assert 'name="politica"' in response.text
    assert 'value="saltar" selected' in response.text
    assert 'value="actualizar"' in response.text
    preview_audit = next(
        row for row in env.repo.panel_audit
        if row.action == "client_import_preview" and row.result.startswith("filas=")
    )
    assert "nuevas=1" in preview_audit.result


# --- T16: ejecución y resumen --------------------------------------------------


def test_import_creates_clients():
    """R25: cada fila válida sin duplicados crea un cliente."""
    repo = FakeRepository()
    plan = ImportPlan(
        rows=(
            _row(1, id_value="ABCD-2345", correo="a@example.com", telefono="+1111111"),
            _row(2, id_value="EFGH-2345", usuario="bea", correo="b@example.com"),
        )
    )
    summary = run_import(plan, "saltar", _source(repo), NOW)
    assert summary.created == 2
    stored = {profile.username: profile for profile in repo.profiles.values()}
    assert set(stored) == {"ana", "bea"}
    assert stored["ana"].email == "a@example.com"
    assert stored["ana"].phone == "+1111111"


def test_update_policy_updates_only_contact():
    """R26: se actualizan solo correo y teléfono no vacíos, nunca el usuario."""
    repo = FakeRepository()
    profile = _create(
        repo, "ana", "ABCD-2345", email="old@example.com", phone="+1111111"
    )
    unchanged = _create(repo, "bea", "EFGH-2345", email="keep@example.com")
    before = repo.get_client_credential(profile.id)
    plan = build_plan(
        [
            {
                "id": "ABCD-2345",
                "usuario": "ana",
                "correo": "new@example.com",
                "telefono": "+2222222",
            },
            {
                "id": "EFGH-2345",
                "usuario": "bea",
                "correo": "",
                "telefono": "",
            },
        ],
        _source(repo),
    )
    summary = run_import(plan, "actualizar", _source(repo), NOW)
    assert summary.updated == 2
    stored = repo.profiles[profile.id]
    assert (stored.email, stored.phone) == ("new@example.com", "+2222222")
    assert stored.username == "ana"
    after = repo.get_client_credential(profile.id)
    assert after.valid_until == before.valid_until
    assert repo.profiles[unchanged.id].email == "keep@example.com"


def test_skip_policy_keeps_existing():
    """R27: con «Saltar» el cliente existente queda intacto y cuenta como saltado."""
    repo = FakeRepository()
    profile = _create(repo, "ana", "ABCD-2345", email="old@example.com")
    plan = build_plan(
        [
            {
                "id": "ABCD-2345",
                "usuario": "ana",
                "correo": "new@example.com",
                "telefono": "",
            }
        ],
        _source(repo),
    )
    summary = run_import(plan, "saltar", _source(repo), NOW)
    assert summary.skipped == 1 and summary.updated == 0
    assert repo.profiles[profile.id].email == "old@example.com"


def test_file_duplicate_always_skipped():
    """R28: un duplicado dentro del archivo se salta aunque la política actualice."""
    repo = FakeRepository()
    plan = build_plan(
        [
            {
                "id": "ABCD-2345",
                "usuario": "ana",
                "correo": "ana@example.com",
                "telefono": "",
            },
            {
                "id": "ABCD-2345",
                "usuario": "bea",
                "correo": "bea@example.com",
                "telefono": "",
            },
        ],
        _source(repo),
    )
    summary = run_import(plan, "actualizar", _source(repo), NOW)
    assert summary.created == 1 and summary.skipped == 1
    assert summary.details[1][1] == "saltado"


class FailingSource:
    """Fuente falsa: la primera escritura falla y la segunda continúa."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def listar(self):
        return []

    def buscar_por_id(self, public_id):
        return None

    def buscar_por_correo(self, correo):
        return None

    def buscar_por_telefono(self, telefono):
        return None

    def actualizar_contacto(self, profile_id, now, *, correo=None, telefono=None):
        return True

    def crear(self, username, password_hash, valid_from, valid_until, now, public_id,
              correo=None, telefono=None):
        self.calls.append(username)
        if username == "boom":
            raise RuntimeError("fallo de escritura")
        return Profile(id="p1", username=username, role="cliente", public_id=public_id)


def test_failed_rows_reported_and_import_continues():
    """R29, R31: una escritura fallida no detiene las filas restantes."""
    source = FailingSource()
    plan = ImportPlan(
        rows=(
            _row(1, usuario="boom", id_value="ABCD-2345"),
            _row(2, usuario="bien", id_value="EFGH-2345"),
        )
    )
    summary = run_import(plan, "saltar", source, NOW)
    assert summary.created == 1 and summary.failed == 1
    assert summary.details[0] == (1, "fallido", "error_escritura")
    assert source.calls == ["boom", "bien"]


def test_username_taken_by_other_client_fails():
    """R29: un usuario de otro cliente no coincidente cuenta como fallido."""
    repo = FakeRepository()
    _create(repo, "ana", "ABCD-2345")
    plan = build_plan(
        [
            {
                "id": "EFGH-2345",
                "usuario": "ana",
                "correo": "otra@example.com",
                "telefono": "",
            }
        ],
        _source(repo),
    )
    row = plan.rows[0]
    assert row.status == "invalida"
    assert {(error.field, error.code) for error in row.errors} == {
        ("usuario", "usuario_tomado")
    }
    summary = run_import(plan, "saltar", _source(repo), NOW)
    assert summary.failed == 1 and summary.created == 0


def test_summary_counts_and_reasons():
    """R30: totales y motivo de cada fila saltada o fallida."""
    source = FailingSource()
    plan = ImportPlan(
        rows=(
            _row(1, usuario="nueva", id_value="ABCD-2345"),
            _row(2, usuario="mal", status="invalida", reason="usuario_invalido"),
            _row(3, usuario="dup", status="duplicado_archivo", reason="id (fila 1)"),
            _row(4, usuario="conf", status="conflicto", reason="conflicto_multiple"),
            _row(
                5,
                usuario="base",
                status="duplicado_base",
                reason="correo",
                existing="p9",
            ),
        )
    )
    summary = run_import(plan, "saltar", source, NOW)
    assert (summary.created, summary.updated, summary.skipped, summary.failed) == (
        1,
        0,
        2,
        2,
    )
    assert summary.details[1] == (2, "fallido", "usuario_invalido")
    assert summary.details[2] == (3, "saltado", "id (fila 1)")
    assert summary.details[3] == (4, "fallido", "conflicto_multiple")


def test_imported_client_has_inactive_credential_and_cannot_login():
    """R37, R38: hash no verificable y credencial vencida."""
    repo = FakeRepository()
    plan = ImportPlan(rows=(_row(1, id_value="ABCD-2345"),))
    run_import(plan, "saltar", _source(repo), NOW)
    found = repo.get_client_credentials_by_username("ana")
    assert found is not None
    _profile, stored_hash, credential = found
    assert verify_password("ana", stored_hash) is False
    assert verify_password("importado$deshabilitado", stored_hash) is False
    assert credential is not None
    status = credential_status(
        credential.valid_from, credential.valid_until, credential.revoked_at, NOW, 0
    )
    assert status == "vencida"
    assert credential_allows_access(status) is False


# --- T17: fuente y esquema -----------------------------------------------------


class RecordingSource:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def listar(self):
        self.calls.append(("listar",))
        return []

    def buscar_por_id(self, public_id):
        return None

    def buscar_por_correo(self, correo):
        return None

    def buscar_por_telefono(self, telefono):
        return None

    def actualizar_contacto(self, profile_id, now, *, correo=None, telefono=None):
        self.calls.append(("actualizar_contacto", profile_id))
        return True

    def crear(self, username, password_hash, valid_from, valid_until, now, public_id,
              correo=None, telefono=None):
        self.calls.append(("crear", username, public_id, correo, telefono))
        return Profile(id="p1", username=username, role="cliente", public_id=public_id)


def test_import_goes_through_client_source():
    """R36: crear y actualizar pasan exclusivamente por FuenteDeClientes."""
    repo = FakeRepository()
    source = RecordingSource()
    plan = ImportPlan(
        rows=(
            _row(1, id_value="ABCD-2345", correo="a@example.com", telefono="+1111111"),
        )
    )
    run_import(plan, "saltar", source, NOW)
    assert source.calls == [
        ("crear", "ana", "ABCD-2345", "a@example.com", "+1111111")
    ]
    assert repo.profiles == {} and repo.client_credentials == {}


def test_schema_statements_idempotent():
    """R39: columnas email/phone/contact_updated_at e índices idempotentes."""
    migrations = " ".join(_MIGRATIONS)
    indexes = " ".join(_INDEXES)
    for statement in (
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS email TEXT",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS phone TEXT",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS contact_updated_at TIMESTAMPTZ",
        "CREATE INDEX IF NOT EXISTS profiles_email ON profiles (email)",
        "CREATE INDEX IF NOT EXISTS profiles_phone ON profiles (phone)",
    ):
        assert statement in migrations
    assert "profiles_email" in migrations and "profiles_phone" in migrations
    assert "profiles_email" not in indexes and "profiles_phone" not in indexes


def test_suppression_clears_email_phone():
    """R40: la supresión deja email y teléfono del perfil en nulo."""
    repo = FakeRepository()
    profile = _create(repo, "ana", "ABCD-2345", email="a@example.com", phone="+1111111")
    repo.create_or_get_pending_suppression("r1", profile.id, "c1", "telegram", NOW)
    assert repo.execute_suppression("r1", "admin1", 60, NOW) is not None
    stored = repo.profiles[profile.id]
    assert stored.email is None and stored.phone is None


def test_retention_purge_clears_email_phone():
    """R41: la purga por retención limpia los contactos anteriores al cutoff."""
    repo = FakeRepository()
    profile = _create(repo, "ana", "ABCD-2345", email="a@example.com", phone="+1111111")
    repo.profiles[profile.id].contact_updated_at = NOW - timedelta(days=10)
    repo.purge_personal_data(NOW - timedelta(days=5), NOW)
    stored = repo.profiles[profile.id]
    assert stored.email is None and stored.phone is None


# --- T18: seguridad y rutas ----------------------------------------------------


def test_non_admin_forbidden(env, panel):
    """R2: una sesión que no es admin no entra ni provoca la lectura del archivo."""
    panel.login_admin(env)
    profile = next(
        stored for stored in env.repo.profiles.values() if stored.role == "admin"
    )
    asesor = env.repo.create_profile("asesor1", "asesor", "hash", panel.NOW)
    env.repo.create_session(
        hash_token("asesor-admin"), asesor.id, panel.CSRF, panel.NOW + timedelta(hours=1)
    )
    env.client.cookies.set("admin_session", "asesor-admin")
    assert profile.role == "admin"

    get_response = env.client.get(
        "/admin/clientes/importar", follow_redirects=False
    )
    assert get_response.status_code == 303
    assert get_response.headers["location"] == "/admin/login"

    post_response = env.client.post(
        "/admin/clientes/importar/vista-previa",
        data={"csrf_token": panel.CSRF},
        files={"archivo": ("clientes.csv", (CSV_HEADER + CSV_ROW).encode(), "text/csv")},
        follow_redirects=False,
    )
    assert post_response.status_code == 303


def test_missing_csrf_403_audited(env, panel):
    """R3: sin CSRF responde 403, audita forbidden y no procesa el archivo."""
    panel.login_admin(env)
    response = env.client.post(
        "/admin/clientes/importar/vista-previa",
        files={"archivo": ("clientes.csv", (CSV_HEADER + CSV_ROW).encode(), "text/csv")},
    )
    assert response.status_code == 403
    audits = [
        row for row in env.repo.panel_audit
        if row.action == "client_import_preview" and row.result == "forbidden"
    ]
    assert len(audits) == 1
    assert env.repo.client_credentials == {}


def test_expired_or_foreign_token_409(env, panel):
    """R32: un token ausente/ajeno responde 409 y no escribe clientes."""
    panel.login_admin(env)
    preview = _upload(env, (CSV_HEADER + CSV_ROW).encode())
    token = _token(preview.text)

    bogus = env.client.post(
        "/admin/clientes/importar/confirmar",
        data={"csrf_token": panel.CSRF, "token": "no-existe", "politica": "saltar"},
    )
    assert bogus.status_code == 409
    assert not any(p.username == "ana" for p in env.repo.profiles.values())

    other = env.repo.create_profile("admin2", "admin", "hash", panel.NOW)
    env.repo.create_session(
        hash_token("otra-sesion"), other.id, panel.CSRF, panel.NOW + timedelta(hours=1)
    )
    env.client.cookies.set("admin_session", "otra-sesion")
    foreign = env.client.post(
        "/admin/clientes/importar/confirmar",
        data={"csrf_token": panel.CSRF, "token": token, "politica": "saltar"},
    )
    assert foreign.status_code == 409
    assert not any(p.username == "ana" for p in env.repo.profiles.values())


def test_preview_expires_after_ttl():
    """R33: la vista previa caduca después del TTL."""
    clock = [NOW]
    staging = ImportStaging(10, lambda: clock[0])
    token = staging.put("sesion", ImportPlan(rows=()))
    clock[0] = NOW + timedelta(seconds=11)
    assert staging.pop("sesion", token) is None


def test_staging_single_use():
    """R33: la vista previa se consume en la confirmación."""
    staging = ImportStaging(600, lambda: NOW)
    plan = ImportPlan(rows=())
    token = staging.put("sesion", plan)
    assert staging.pop("sesion", token) is plan
    assert staging.pop("sesion", token) is None


def test_file_not_persisted(env, panel):
    """R10: la vista previa no crea clientes ni guarda el archivo en la base."""
    panel.login_admin(env)
    response = _upload(env, (CSV_HEADER + CSV_ROW).encode())
    assert response.status_code == 200
    assert not any(p.username == "ana" for p in env.repo.profiles.values())
    assert env.repo.client_credentials == {}
    assert env.repo.messages == []


def test_csv_export_escapes_formulas():
    """R34: las celdas que empiezan por fórmula se prefijan con apóstrofo."""
    for dangerous in ("=SUM(A1)", "+1", "-1", "@cmd", "\tvalor", "\rvalor"):
        assert csv_safe(dangerous) == f"'{dangerous}"
    assert csv_safe("normal") == "normal"
    summary = ImportSummary(
        created=0,
        updated=0,
        skipped=0,
        failed=1,
        details=((1, "fallido", "=motivo"),),
    )
    assert "'=motivo" in summary_to_csv(summary)


def test_summary_and_audit_have_no_pii(env, panel):
    """R35: ni el resumen ni la auditoría contienen correo ni teléfono."""
    panel.login_admin(env)
    preview = _upload(env, (CSV_HEADER + CSV_ROW).encode())
    token = _token(preview.text)
    response = env.client.post(
        "/admin/clientes/importar/confirmar",
        data={"csrf_token": panel.CSRF, "token": token, "politica": "saltar"},
    )
    assert response.status_code == 200
    assert "ana@example.com" not in response.text
    assert "+34600123456" not in response.text
    audit = next(
        row for row in env.repo.panel_audit if row.action == "client_import"
    )
    assert "ana@example.com" not in audit.result
    assert "+34600123456" not in audit.result

    match = re.search(r'href="(/admin/clientes/importar/resumen/[^"]+)"', response.text)
    assert match is not None
    csv_response = env.client.get(match.group(1))
    assert csv_response.status_code == 200
    assert csv_response.headers["content-disposition"].startswith("attachment")
    assert "ana@example.com" not in csv_response.text
    assert "+34600123456" not in csv_response.text


def test_import_link_visible_for_admin(env, panel):
    """R1: el enlace «Importar clientes» aparece para el admin."""
    panel.login_admin(env)
    response = env.client.get("/admin/clientes")
    assert response.status_code == 200
    assert "Importar clientes" in response.text
    assert 'href="/admin/clientes/importar"' in response.text


def _xlsx_bytes(rows):
    import io

    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_parse_upload_lee_xlsx_con_numeros_y_celdas_vacias():
    from orchestrator.client_import import parse_upload

    data = _xlsx_bytes(
        [["usuario", "correo", "telefono"], ["ana", "a@x.co", 573001234567], ["", None, None], ["bob", None, None]]
    )
    rows = parse_upload(data, max_bytes=1_000_000, max_rows=10)
    assert rows == [
        {"usuario": "ana", "correo": "a@x.co", "telefono": "573001234567"},
        {"usuario": "bob", "correo": "", "telefono": ""},
    ]


def test_parse_upload_xlsx_rechaza_encabezado_limites_y_basura():
    from orchestrator.client_import import ImportFileError, parse_upload

    with pytest.raises(ImportFileError) as bad_header:
        parse_upload(_xlsx_bytes([["clave"], ["x"]]), max_bytes=1_000_000, max_rows=10)
    assert bad_header.value.code == "encabezado_invalido"
    many = _xlsx_bytes([["usuario"]] + [[f"u{i}"] for i in range(5)])
    with pytest.raises(ImportFileError) as rows:
        parse_upload(many, max_bytes=1_000_000, max_rows=3)
    assert rows.value.code == "demasiadas_filas"
    with pytest.raises(ImportFileError) as big:
        parse_upload(many, max_bytes=10, max_rows=3)
    assert big.value.code == "archivo_demasiado_grande"
    with pytest.raises(ImportFileError) as junk:
        parse_upload(b"PK\x03\x04no es un xlsx", max_bytes=1_000_000, max_rows=3)
    assert junk.value.code == "xlsx_invalido"


def test_parse_upload_csv_sigue_funcionando():
    from orchestrator.client_import import parse_upload

    assert parse_upload(b"usuario\nana\n", max_bytes=1000, max_rows=5) == [{"usuario": "ana"}]
