# Design — robustez del estado de traspaso automático (#34)

## Alcance y cambios

- `services/orchestrator/orchestrator/adapters/repository.py`: extender `purge_personal_data` para borrar outcomes anteriores al mismo `cutoff` de retención, y borrar outcomes/rachas asociadas a los `inactive_ids` ya calculados. Agregar las cantidades a `deleted`; mantener el insert de `privacy_purge_runs` dentro de la transacción existente.
- `services/orchestrator/orchestrator/domain.py`: garantizar que `_auto_handover` llame `finish_auto_handover(contact.id, False)` también si `_handover` lanza una excepción; después propagarla para conservar el manejo actual del error.
- Tests en `services/orchestrator/tests/test_privacy_purge.py` y `test_auto_handover.py`; actualizar trazabilidad en `progress/impl_robustez_estado_traspaso_automatico.md`.
- No hay rutas, contratos, variables, dependencias ni política de retención nuevas. El fake debe reflejar los mismos criterios y conteos del repositorio PostgreSQL.

## Estado conservado

Los outcomes de contactos activos se conservan hasta que alcanzan el corte de retención. Las rachas de contactos activos no vencen por sí solas: se eliminan cuando se purga el contacto asociado. Las filas de `privacy_purge_runs` conservan el resultado agregado, no los identificadores purgados.

## Alternativa descartada

Conservar outcomes indefinidamente para deduplicación mantiene innecesariamente identificadores de contacto y permite crecimiento sin límite. La deduplicación global existente por `processed_updates` no se modifica.
