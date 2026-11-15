# Spec review — #54 segundo_factor_panel

**Veredicto:** APPROVED

Revisión final tras la corrección. Los dos hallazgos anteriores están resueltos y requirements, design y tasks cuadran.

## Hallazgos resueltos

1. **Recuperación del administrador único y pérdida de clave.**
   - `design.md` declara una vía SQL documentada: sección «Recuperación operativa». Exige acceso a la BD y apunta a un `profiles.id`. Es una sola transacción con auditoría `ops:<operador>` / `two_factor_reset_ops`. Borra `staff_recovery_codes`, `staff_two_factor` y `admin_sessions`. Incluye la variante para `PANEL_2FA_ENCRYPTION_KEY`.
   - S4 ahora cita el bootstrap #23 (antes #34) y aclara que no sirve porque se niega si ya existe un administrador. S9 remite al procedimiento.
   - `requirements.md` añade R46 (procedimiento y auditoría), R47 (administrador único y variante de clave) y R48 (sin secretos ni hashes, y sin 2FA tras ejecutarlo).
   - T17 redacta la sección en `docs/despliegue.md`. T18 la verifica con un test documental que cubre `BEGIN`/`COMMIT`, `ops:`, los tres `DELETE`, la variante de clave y la mención a #23, y que comprueba que no hay `SELECT` de secretos. T16 pasa a cubrir R1–R48.

2. **Sesiones al activar el 2FA desde una sesión normal.**
   - R25 ahora borra las demás sesiones del perfil, tanto si la sesión era restringida como si era normal. `design.md` (confirm) coincide. T11 prueba ambos casos, incluidas las sesiones de otros perfiles, que sobreviven.

## T0 sigue siendo prerequisito humano

T0 sigue en `[ ]`: es una task humana previa que añade `cryptography>=43,<48` a `requirements.txt` e instala la dependencia en `.venv` y en la imagen. El agente no la instala. El leader debe asegurarse de que el humano complete T0 antes de pasar la feature a `in_progress`/implementer.

## Coherencia

- Las tasks T0–T18 están todas en `[ ]` y en orden. Entre todas cubren R1–R48, y R46–R48 quedan cubiertos por T17 y T18.
- Sin bloqueos pendientes.
