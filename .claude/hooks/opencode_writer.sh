# Configuración y preflight compartidos por el implementer y nocturno.sh.

readonly OPENCODE_WRITER_MODEL="opencode-go/deepseek-v4.1-flash"

opencode_writer_authenticated() {
  local auth_output
  auth_output="$(opencode auth list 2>&1)" || return 1
  printf '%s\n' "$auth_output" | grep -Eqi 'OpenCode Go|opencode-go'
}
