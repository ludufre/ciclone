# Carrega o .ciclone.env da raiz (fora do git) SEM sobrescrever o que já veio do ambiente:
# `FW_SERVER_DIR=/outro bash tools/fetch_m4fw.sh` tem que valer por cima do arquivo.
# Formato: CHAVE=valor por linha; '#' comenta a linha inteira ou o resto dela (depois de um
# espaço); sem aspas nem expansão de ~/$HOME -- o valor é literal.
if [ -f .ciclone.env ]; then
  while IFS='=' read -r _k _v || [ -n "$_k" ]; do
    _k="${_k#"${_k%%[![:space:]]*}"}"; _k="${_k%"${_k##*[![:space:]]}"}"
    case "$_k" in ''|\#*) continue ;; esac
    case "$_k" in *[!A-Za-z0-9_]*) continue ;; esac
    _v="${_v%%[[:space:]]#*}"; _v="${_v%"${_v##*[![:space:]]}"}"
    [ -n "$(eval "printf %s \"\${$_k:-}\"")" ] || eval "$_k=\$_v"
  done < .ciclone.env
  unset _k _v
fi
