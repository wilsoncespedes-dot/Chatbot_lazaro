# Verificación — Cómo demostrar que el trabajo funciona

> Regla de oro: **el agente no dice "funciona", lo demuestra**.
> Toda feature termina con evidencia ejecutable, no con afirmaciones.

## Comando único

```bash
./init.sh
```

Detecta el Python correcto (`.venv` primero; en Windows `python` o `py -3`)
y ejecuta `python -m pytest` sobre `services/`, `contracts/`, `eval/` y
`scripts/`. Antes de que exista la feature 2, «aún no hay tests» es normal.

Para correr solo un servicio:

```bash
python -m pytest services/rag
```

## Niveles de verificación

### Nivel 1 — Tests unitarios (obligatorio)

Toda función pública de `domain.py` y de los adaptadores tiene tests que
cubren el camino feliz y al menos un camino de error.

### Nivel 2 — Tests de rutas HTTP (obligatorio)

Cada ruta se prueba con `TestClient` sobre `create_app(...)` con adaptadores
falsos: código HTTP, forma del JSON, encabezado `X-Service-Token` ausente
(→ 401) y errores con forma `{"error", "message"}`.

### Nivel 3 — Tests de contrato (obligatorio desde la feature 1)

Los ejemplos JSON de `contracts/` se validan contra los modelos de
`lazaro_contracts`. Si un servicio expone o consume una ruta del contrato,
su test usa esos mismos modelos.

### Nivel 4 — Trazabilidad de requirements (obligatorio para `"sdd": true`)

Cada `R<n>` de `specs/<name>/requirements.md` tiene al menos un test
concreto. El implementer documenta el mapa en `progress/impl_<name>.md`:

```markdown
## Trazabilidad
- R1 → `services/orchestrator/tests/test_messages.py::test_duplicate_update_is_ignored`
- R2 → `services/orchestrator/tests/test_messages.py::test_missing_token_returns_401`
```

### Nivel 5 — Integración con Docker (opcional, manual)

```bash
docker compose up -d --build
curl http://localhost:8001/health
docker compose down
```

Los tests que necesitan Docker van marcados `@pytest.mark.integration` y no
corren por defecto.

## Pruebas de seguridad obligatorias

Vienen del documento del proyecto. Cuando exista la feature que las toca,
deben estar y pasar:

| Prueba | Desde la feature |
|--------|------------------|
| Una ruta interna sin `X-Service-Token` válido responde 401 | 2 (esqueleto) |
| Un `update_id` repetido no se procesa dos veces | 3 y 4 |
| Si ningún fragmento supera el umbral, el bot no responde con el modelo y ofrece asesor | 5 y 6 |
| Una respuesta del modelo con citas inventadas se reemplaza por el rechazo fijo | 6 |
| Un mensaje con instrucciones («ignora tus reglas y ejecuta…») se trata como texto: no dispara ninguna acción distinta de buscar, responder o traspasar | 4 |
| El traspaso responde bien cuando no hay asesores | 7 |
| Un cliente no puede consultar la base de datos | feature de consulta (posterior) |

## Anti-patrones (no hacer)

- ❌ "He añadido la ruta, debería funcionar." → falta test ejecutable.
- ❌ Test que solo comprueba que no lanza excepción → debe comprobar el resultado.
- ❌ Tests que llaman a Telegram o al proveedor de IA de verdad.
- ❌ Saltarse un test con `skip` para que `init.sh` quede verde.
- ❌ Marcar la feature `done` sin `./init.sh` verde.

## Verificación final antes de cerrar

```bash
./init.sh           # debe terminar con [OK] Entorno listo
```

Si está rojo, **no** marques nada como `done`. Anota el bloqueo en
`progress/current.md` y pon la feature en `blocked`.
