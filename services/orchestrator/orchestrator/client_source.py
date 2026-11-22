"""Puerto de acceso a clientes y su implementación local (#76)."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .adapters.repository import ClientCredentialRow, Repository
    from .domain import ClientCredential, ClientSearchResult, Profile


class FuenteDeClientes(Protocol):
    """Operaciones de clientes que el dominio necesita, sin acoplarse al repositorio."""

    def buscar_por_id(self, public_id: str) -> ClientSearchResult | None: ...

    def listar(self) -> list[ClientCredentialRow]: ...

    def crear(
        self,
        username: str,
        password_hash: str,
        valid_from: datetime,
        valid_until: datetime,
        now: datetime,
        public_id: str,
        correo: str | None = None,
        telefono: str | None = None,
    ) -> Profile: ...

    def buscar_por_correo(self, correo: str) -> str | None: ...

    def buscar_por_telefono(self, telefono: str) -> str | None: ...

    def actualizar_contacto(
        self,
        profile_id: str,
        now: datetime,
        *,
        correo: str | None = None,
        telefono: str | None = None,
    ) -> bool: ...

    def actualizar(
        self,
        profile_id: str,
        now: datetime,
        *,
        valid_until: datetime | None = None,
        revocar: bool = False,
    ) -> bool: ...

    def obtener_credencial(self, profile_id: str) -> ClientCredential | None: ...


class FuenteClientesLocal:
    """Fuente sobre el repositorio actual; no cambia el esquema de datos."""

    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    def buscar_por_id(self, public_id: str) -> ClientSearchResult | None:
        return self._repository.find_client_by_public_id(public_id)

    def listar(self) -> list[ClientCredentialRow]:
        return self._repository.list_client_credentials()

    def crear(
        self,
        username: str,
        password_hash: str,
        valid_from: datetime,
        valid_until: datetime,
        now: datetime,
        public_id: str,
        correo: str | None = None,
        telefono: str | None = None,
    ) -> Profile:
        return self._repository.create_client_credential(
            username,
            password_hash,
            valid_from,
            valid_until,
            now,
            public_id=public_id,
            email=correo,
            phone=telefono,
        )

    def buscar_por_correo(self, correo: str) -> str | None:
        return self._repository.find_client_id_by_email(correo)

    def buscar_por_telefono(self, telefono: str) -> str | None:
        return self._repository.find_client_id_by_phone(telefono)

    def actualizar_contacto(
        self,
        profile_id: str,
        now: datetime,
        *,
        correo: str | None = None,
        telefono: str | None = None,
    ) -> bool:
        return self._repository.update_client_contact(
            profile_id, now, email=correo, phone=telefono
        )

    def actualizar(
        self,
        profile_id: str,
        now: datetime,
        *,
        valid_until: datetime | None = None,
        revocar: bool = False,
    ) -> bool:
        if revocar and valid_until is not None:
            raise ValueError("No se puede renovar y revocar en la misma operación.")
        if revocar:
            return self._repository.revoke_client_credential(profile_id, now)
        if valid_until is not None:
            return self._repository.renew_client_credential(profile_id, valid_until, now)
        return False

    def obtener_credencial(self, profile_id: str) -> ClientCredential | None:
        return self._repository.get_client_credential(profile_id)
