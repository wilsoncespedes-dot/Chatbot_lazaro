# Spec review — estados_y_consentimiento (#37)

**Veredicto:** SPEC_APPROVED

## Revisión enfocada

- Cobertura de acceptance: [x] R35 exige la transición lógica `nuevo → esperando_consentimiento` en memoria, sin contacto ni estado persistido.
- Cobertura de acceptance: [x] R36 exige la transición `esperando_consentimiento → cerrada` tras `privacy.reject`; solo se conserva la evidencia permitida por R5/R29.
- EARS y trazabilidad: [x] R35/R36 usan patrón EARS, cada requirement tiene una task y tests concretos quedan previstos en T2/T3/T10/T11.
- Decisiones/dependencias: [x] Preserva compuertas #35/#36, identidad por canal, evidencia de botón y deja login/credenciales a #38.
- Diseño/seguridad: [x] Reutiliza panel #21, falla cerrado sin textos legales, no persiste estado/contacto previo al consentimiento y el rechazo conserva solo evidencia mínima.

## Resultado de la corrección

R35 y R36 resuelven los dos huecos señalados en la primera revisión. Las transiciones iniciales son verificables y preservan la regla de no persistir contacto/estado antes del consentimiento. El resto del spec sigue alineado con #35/#36, la evidencia de botones, el panel #21 y el límite de login en #38. No quedan cambios bloqueantes.
