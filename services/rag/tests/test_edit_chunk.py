"""Tests de PATCH /chunks/{id} (edición de fragmentos)."""
from __future__ import annotations

from lazaro_contracts import ChunkUpdateResponse, ErrorResponse

from rag.adapters.embeddings import FakeEmbeddings
from rag.domain import Chunk

HEADERS = {"X-Service-Token": "svc-token"}


def _add(env, text: str = "texto original", name: str = "Manual A") -> Chunk:
    vector = env.embeddings.embed([text])[0]
    chunk = Chunk("m1-1", "m1", name, 1, text, vector)
    env.repo.add_manual("m1", name, [chunk])
    return chunk


def _patch(env, chunk_id: str, text: str, headers: dict | None = None):
    return env.client.patch(
        f"/chunks/{chunk_id}",
        json={"text": text},
        headers=HEADERS if headers is None else headers,
    )


def _err(response, status: int, code: str) -> dict:
    assert response.status_code == status
    body = response.json()
    ErrorResponse.model_validate(body)
    assert body["error"] == code
    return body


def test_patch_chunk_updates_text_and_returns_200(env):
    """R5, R6, R8: edición válida -> 200 con los datos actualizados del fragmento."""
    _add(env)
    response = _patch(env, "m1-1", "texto nuevo")
    assert response.status_code == 200
    body = ChunkUpdateResponse.model_validate(response.json())
    assert body.chunk_id == "m1-1"
    assert body.text == "texto nuevo"
    assert env.repo.chunks[0].text == "texto nuevo"


def test_patch_chunk_recalculates_embedding(env):
    """R5: el embedding se recalcula con el proveedor configurado antes de persistir."""
    _add(env)
    _patch(env, "m1-1", "nuevo contenido")
    assert env.embeddings.calls[-1] == ["nuevo contenido"]
    expected = FakeEmbeddings().embed(["nuevo contenido"])[0]
    assert env.repo.chunks[0].embedding == expected


def test_patch_chunk_preserves_metadata(env):
    """R7: conserva chunk_id, manual_id, manual, orden y estado activo."""
    chunk = _add(env, name="Manual Facturación")
    body = ChunkUpdateResponse.model_validate(_patch(env, "m1-1", "otro texto").json())
    assert body.chunk_id == chunk.chunk_id
    assert body.manual_id == chunk.manual_id
    assert body.manual == chunk.manual
    assert body.order == chunk.order
    assert body.active is chunk.active
    stored = env.repo.chunks[0]
    assert (stored.chunk_id, stored.manual_id, stored.manual, stored.order, stored.active) == (
        chunk.chunk_id,
        chunk.manual_id,
        chunk.manual,
        chunk.order,
        chunk.active,
    )


def test_patch_chunk_preserves_text_exactly(env):
    """R3: un texto no vacío se guarda exactamente como se recibe, sin normalizar."""
    _add(env)
    text = "  Texto con espacios  "
    body = ChunkUpdateResponse.model_validate(_patch(env, "m1-1", text).json())
    assert body.text == text
    assert env.repo.chunks[0].text == text
    assert env.embeddings.calls[-1] == [text]


def test_patch_chunk_rejects_blank_text(env):
    """R2: texto vacío o solo espacios -> 422 validation_error sin cambios."""
    original = _add(env)
    for text in ("", "   ", "\n\t "):
        _err(_patch(env, "m1-1", text), 422, "validation_error")
        assert env.repo.chunks[0] == original
    assert env.embeddings.calls == [["texto original"]]


def test_patch_chunk_not_found(env):
    """R9: un chunk_id inexistente -> 404 not_found sin crear datos ni llamar a embeddings."""
    _err(_patch(env, "no-existe", "texto"), 404, "not_found")
    assert env.repo.chunks == [] and env.repo.manuals == {}
    assert env.embeddings.calls == []


def test_patch_chunk_embeddings_failure_keeps_previous_values(env):
    """R10: si falla el embedding -> 500 internal_error y no se modifica el fragmento."""
    original = _add(env)
    env.embeddings.fail = True
    _err(_patch(env, "m1-1", "texto nuevo"), 500, "internal_error")
    assert env.repo.chunks[0] == original


def test_patch_chunk_without_token_returns_401(env):
    """R4: sin X-Service-Token no se modifica nada y se responde 401 unauthorized."""
    original = _add(env)
    _err(_patch(env, "m1-1", "texto nuevo", headers={}), 401, "unauthorized")
    assert env.repo.chunks[0] == original


def test_patch_chunk_with_wrong_token_returns_401(env):
    """R4: token incorrecto -> 401 unauthorized sin llamar a embeddings."""
    original = _add(env)
    _err(
        _patch(env, "m1-1", "texto nuevo", headers={"X-Service-Token": "mal"}),
        401,
        "unauthorized",
    )
    assert env.repo.chunks[0] == original
    assert env.embeddings.calls == [["texto original"]]
