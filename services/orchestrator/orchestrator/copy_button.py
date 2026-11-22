"""Botón «Copiar» de IDs de cliente y su JavaScript de mismo origen (#73)."""
from __future__ import annotations

import html

COPY_JS = """'use strict';
function fallbackCopy(value, button) {
  var field = document.createElement('textarea');
  field.value = value;
  field.setAttribute('readonly', '');
  field.style.position = 'fixed';
  field.style.opacity = '0';
  document.body.appendChild(field);
  field.select();
  try {
    if (document.execCommand && document.execCommand('copy')) {
      button.textContent = 'Copiado';
    }
  } catch (error) {
    /* sin selección manual no hay alternativa */
  }
  document.body.removeChild(field);
}
document.addEventListener('click', function (event) {
  var button = event.target.closest('button[data-copy]');
  if (!button) { return; }
  var value = button.getAttribute('data-copy') || '';
  var done = function () { button.textContent = 'Copiado'; };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(value).then(done, function () {
      fallbackCopy(value, button);
    });
    return;
  }
  fallbackCopy(value, button);
});
"""


def copy_button(public_id: str) -> str:
    """R18: botón sin `onclick` en línea; el valor viaja en `data-copy`."""
    if not public_id:
        return ""
    return (
        '<button type="button" class="copy-btn" '
        f'data-copy="{html.escape(public_id, quote=True)}" '
        'aria-label="Copiar ID">Copiar</button>'
    )
