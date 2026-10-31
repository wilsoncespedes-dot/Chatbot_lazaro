"""Tests de POST /manuals (ingesta)."""
from __future__ import annotations

from lazaro_contracts import ErrorResponse, ManualUploadResponse
from rag_tests_fakes import make_blank_pdf, make_docx, make_pdf

HEADERS = {"X-Service-Token": "svc-token"}
LONG = " ".join(f"palabra{i}" for i in range(60))


def _err(response, status, code):
    assert response.status_code == status
    body = response.json()
    ErrorResponse.model_validate(body)
    assert body["error"] == code


def test_upload_pdf_returns_201_with_chunks(env):
    """R1: PDF con texto -> 201 {manual_id, chunks}."""
    response = env.upload(make_pdf(LONG))
    assert response.status_code == 201
    body = ManualUploadResponse.model_validate(response.json())
    assert body.chunks == len(env.repo.chunks) >= 1


def test_upload_docx_returns_201_with_chunks(env):
    """R2: DOCX con texto -> 201 con chunks >= 1."""
    response = env.upload(make_docx(LONG), filename="m.docx", ctype="application/octet-stream")
    assert response.status_code == 201
    assert response.json()["chunks"] >= 1


def test_upload_stores_chunk_fields_and_active_true(env):
    """R4: cada fragmento tiene chunk_id único, manual_id, orden desde 1, texto, vector y active."""
    body = env.upload(make_docx(LONG)).json()
    chunks = env.repo.chunks
    assert len(chunks) > 1
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    assert [c.order for c in chunks] == list(range(1, len(chunks) + 1))
    for c in chunks:
        assert c.manual_id == body["manual_id"]
        assert c.chunk_id == f"{c.manual_id}-{c.order}"
        assert c.text and c.embedding and c.active is True


def test_upload_uses_name_in_search_manual(env):
    """R5: el nombre del manual se devuelve en /search y los vectores vienen del adaptador."""
    env.upload(make_docx("instalar el modulo de facturacion"), name="Manual Facturación")
    assert env.embeddings.calls
    results = env.search("instalar el modulo de facturacion").json()
    assert results and results[0]["manual"] == "Manual Facturación"


def test_upload_text_file_returns_415(env):
    """R6: un archivo de texto -> 415 unsupported_format y nada guardado."""
    _err(env.upload(b"hola mundo", filename="a.txt", ctype="text/plain"), 415, "unsupported_format")
    assert env.repo.chunks == [] and env.repo.manuals == {}


def test_upload_fake_pdf_extension_returns_415(env):
    """R6: se decide por contenido, no por extensión."""
    _err(env.upload(b"no soy pdf", filename="a.pdf"), 415, "unsupported_format")
    assert env.repo.chunks == []


def test_upload_empty_file_returns_422_empty_document(env):
    """R7: archivo de 0 bytes -> 422 empty_document."""
    _err(env.upload(b""), 422, "empty_document")
    assert env.repo.chunks == []


def test_upload_pdf_without_text_returns_422(env):
    """R8: PDF sin texto, PDF corrupto y DOCX sin texto -> 422 empty_document."""
    _err(env.upload(make_blank_pdf()), 422, "empty_document")
    _err(env.upload(b"%PDF-1.4 basura"), 422, "empty_document")
    _err(env.upload(make_docx("")), 422, "empty_document")
    assert env.repo.chunks == []


def test_upload_missing_name_returns_422_validation_error(env):
    """R9: falta `name` o `file`, o name vacío -> 422 validation_error."""
    r = env.client.post("/manuals", files={"file": ("a.pdf", make_pdf(LONG))}, headers=HEADERS)
    _err(r, 422, "validation_error")
    r = env.client.post("/manuals", data={"name": "x"}, headers=HEADERS)
    _err(r, 422, "validation_error")
    _err(env.upload(make_pdf(LONG), name=""), 422, "validation_error")


def test_upload_name_too_long_returns_422(env):
    """R9: name de más de 200 caracteres -> 422 validation_error."""
    _err(env.upload(make_pdf(LONG), name="a" * 201), 422, "validation_error")
    assert env.repo.chunks == []


def test_upload_embeddings_failure_returns_500_and_stores_nothing(env):
    """R10: fallo de embeddings -> 500 internal_error y nada guardado."""
    env.embeddings.fail = True
    _err(env.upload(make_pdf(LONG)), 500, "internal_error")
    assert env.repo.chunks == [] and env.repo.manuals == {}
