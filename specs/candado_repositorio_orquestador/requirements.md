# Requirements — candado_repositorio_orquestador

Feature #18. Servicio: solo `orchestrator`. Previa a la #16. *Decidido por el humano
(2026-10-31), D2 de la #12 / decisión 6 de la #14:* `PostgresRepository` del orquestador protege
su conexión pg8000 compartida con un `threading.Lock`, con el mismo patrón que R44-R45 de
`specs/autorizacion_asesores/` en `PostgresCaseRepository` de handover.

Terminología: la **sección protegida** es todo lo que `_run` hace sobre la conexión: abrirla y
crear el esquema si es el primer uso, pedir el cursor, `execute`, `fetchall`, y `commit` o
`rollback`.

## Exclusión mutua (`services/orchestrator/orchestrator/adapters/repository.py`)

## R1
El sistema (orchestrator) DEBE ejecutar la sección protegida de cada operación de
`PostgresRepository` en exclusión mutua mediante un `threading.Lock` propio de la instancia
(atributo `_lock`), de modo que dos hilos nunca usen la conexión a la vez.

## R2
MIENTRAS un hilo ejecuta `execute` sobre un cursor de la conexión de `PostgresRepository`, el
sistema DEBE mantener tomado el `_lock` de esa instancia.

## R3
CUANDO varios hilos hacen a la vez el primer uso de un `PostgresRepository`, el sistema DEBE
abrir una sola conexión y ejecutar las sentencias de `_SCHEMA` una sola vez.

## R4
SI una sentencia lanza una excepción dentro de la sección protegida ENTONCES el sistema DEBE
hacer `rollback`, propagar la misma excepción al llamador y liberar el `_lock`, de modo que la
siguiente operación de cualquier hilo se ejecute sin bloquearse.

## Sin cambios de comportamiento observable

## R5
El sistema DEBE seguir ejecutando el SQL de `PostgresRepository` parametrizado con `%s`, con las
mismas sentencias y los mismos parámetros que antes de esta feature (el test existente
`test_postgres_repository_uses_parameters_only` pasa sin cambios).

## R6
CUANDO se construye un `PostgresRepository`, el sistema NO DEBE abrir la conexión; DEBE abrirla en
la primera operación (el test existente `test_postgres_repository_connects_lazily` pasa sin
cambios).

## R7
El sistema DEBE conservar sin cambios las firmas del `Protocol` `Repository`, de `FakeRepository`
y de los métodos públicos y el constructor de `PostgresRepository`, y los valores que devuelven
(todos los tests existentes de `services/orchestrator/tests/` pasan sin eliminarse ni
debilitarse).

## Fuera de alcance

Cambios en `contracts/`, en otros servicios, en `main.py` del orquestador o en dependencias.
Pool de conexiones o conexión por petición (descartados por el humano, D2 de la #12). Atomicidad
entre las dos sentencias de `get_or_create_contact` (cada `_run` es su propia transacción, como
hoy; ver design.md).

## Trazabilidad con el `acceptance` de feature_list.json

| Criterio (orden) | Requirements |
|------------------|--------------|
| 1. `threading.Lock` sobre la conexión compartida; dos llamadas concurrentes no la usan a la vez | R1, R2, R3, R4 |
| 2. Sin cambios de contrato ni de comportamiento observable; SQL parametrizado como hoy | R5, R6, R7 |
| 3. Tests: dos hilos con conexión falsa no se solapan; ningún test existente se elimina ni se debilita | R1, R2 (T3), R3 (T4), R4 (T5), R7 (T6) |
