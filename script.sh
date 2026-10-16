#!/usr/bin/env bash
set -Eeuo pipefail

VERSION=1
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
REPO=$SCRIPT_DIR
PROFILE=portable
ACTION=dry-run
PACKAGES_ONLY=0
WITH_OPTIONAL=0
BACKUP_ID=
MANIFEST="$REPO/manifests/desktop.tsv"

usage() {
  cat <<'EOF'
Usage: ./script.sh [--dry-run|--apply] [--profile portable|desktop]
       ./script.sh --restore BACKUP_ID [--dry-run|--apply]
       ./script.sh --install-packages --apply [--with-optional]

Default mode is --dry-run; it performs no writes. File application is
separate from the explicit, privileged --install-packages operation.
EOF
}
fail() { printf 'Erro: %s\n' "$*" >&2; exit 1; }
log() { printf '%s\n' "$*"; }
valid_rel() { [[ -n $1 && $1 != /* && $1 != *$'\t'* && $1 != *$'\n'* && $1 != *$'\r'* && $1 != *//* && $1 != */ && $1 != . && $1 != ./* && $1 != */./* && $1 != */. && $1 != .. && $1 != ../* && $1 != */../* && $1 != */.. ]]; }
valid_path_text() { [[ $1 != *$'\t'* && $1 != *$'\n'* && $1 != *$'\r'* ]]; }

while (($#)); do
  case $1 in
    --help|-h) usage; exit 0 ;;
    --dry-run) ACTION=dry-run ;;
    --apply) ACTION=apply ;;
    --profile) (($# >= 2)) || fail '--profile requer valor'; PROFILE=$2; shift ;;
    --restore) (($# >= 2)) || fail '--restore requer BACKUP_ID'; BACKUP_ID=$2; shift ;;
    --install-packages) PACKAGES_ONLY=1 ;;
    --with-optional) WITH_OPTIONAL=1 ;;
    *) fail "opção desconhecida: $1" ;;
  esac
  shift
done
[[ $PROFILE == portable || $PROFILE == desktop ]] || fail 'perfil inválido'
[[ -n ${HOME:-} && $HOME == /* ]] || fail 'HOME precisa ser absoluto'
XDG_CONFIG_HOME=${XDG_CONFIG_HOME:-$HOME/.config}
XDG_STATE_HOME=${XDG_STATE_HOME:-$HOME/.local/state}
[[ $XDG_CONFIG_HOME == /* && $XDG_STATE_HOME == /* ]] || fail 'XDG_CONFIG_HOME e XDG_STATE_HOME precisam ser absolutos'
for p in "$HOME" "$XDG_CONFIG_HOME" "$XDG_STATE_HOME"; do valid_path_text "$p" || fail 'paths não podem conter TAB/newline/CR'; done
((EUID != 0)) || fail 'não execute o instalador como root'
# Normalize lexical aliases without following symlinks; preflight checks those separately.
HOME=$(realpath -ms -- "$HOME")
XDG_CONFIG_HOME=$(realpath -ms -- "$XDG_CONFIG_HOME")
XDG_STATE_HOME=$(realpath -ms -- "$XDG_STATE_HOME")
[[ $HOME != / ]] || fail 'HOME não pode ser a raiz do sistema'
[[ $XDG_CONFIG_HOME != *'"'* && $XDG_CONFIG_HOME != *'\'* ]] || fail 'XDG_CONFIG_HOME não pode conter aspas duplas ou barras invertidas nos templates'
((PACKAGES_ONLY || ! WITH_OPTIONAL)) || fail '--with-optional requer --install-packages'

if ((PACKAGES_ONLY)); then
  [[ -z $BACKUP_ID ]] || fail 'restauração e pacotes são operações distintas'
  command -v pacman >/dev/null || fail 'pacman não está disponível'
  ((EUID != 0)) || fail 'não execute o instalador como root'
  pkg_files=("$REPO/packages/arch.txt")
  if command -v pacman-conf >/dev/null && pacman-conf --repo-list 2>/dev/null | grep -Fxq cachyos; then
    pkg_files+=("$REPO/packages/cachyos.txt")
  fi
  ((WITH_OPTIONAL)) && pkg_files+=("$REPO/packages/optional.txt")
  packages=()
  for f in "${pkg_files[@]}"; do
    [[ -f $f ]] || { [[ $f == */cachyos.txt ]] && continue; fail "lista ausente: $f"; }
    while IFS= read -r line || [[ -n $line ]]; do
      line=${line%%#*}; line=${line//[[:space:]]/}
      [[ -z $line ]] && continue
      [[ $line =~ ^[A-Za-z0-9@._+-]+$ ]] || fail "nome de pacote inválido em $f"
      pacman -Si -- "$line" >/dev/null 2>&1 || fail "pacote indisponível: $line"
      packages+=("$line")
    done < "$f"
  done
  ((${#packages[@]})) || { log 'Nenhum pacote selecionado.'; exit 0; }
  if [[ $ACTION == dry-run ]]; then
    printf 'Pacote selecionado: %s\n' "${packages[@]}"
    log "Prévia: ${#packages[@]} pacotes disponíveis; nenhum pacote foi instalado."
    exit 0
  fi
  log "Instalando ${#packages[@]} pacotes via sudo pacman -S --needed."
  sudo pacman -S --needed -- "${packages[@]}"
  exit
fi

# Canonical roots are computed without creating directories.
REPO_REAL=$(realpath -e -- "$REPO") || fail 'não foi possível resolver o repositório'
STATE_REAL=$(realpath -m -- "$XDG_STATE_HOME/dots-arch/backups") || fail 'estado inválido'
case "$STATE_REAL/" in "$REPO_REAL/"*) fail 'backup root precisa ficar fora do repositório' ;; esac
BACKUP_ROOT=$STATE_REAL

hash_file() { sha256sum -- "$1" | { read -r h _; printf '%s' "$h"; }; }
sed_replacement() { local s=$1; s=${s//\\/\\\\}; s=${s//&/\\&}; s=${s//|/\\|}; printf '%s' "$s"; }
link_is_correct() { [[ -L $1 ]] && [[ $(readlink -- "$1") == "$2" ]]; }
# Reject any symlink or non-directory in the path from root to the parent.
check_ancestors() {
  local root rel cur part
  local -a parts root_parts
  root=$1; rel=$2; cur=''
  IFS=/ read -ra root_parts <<< "$root"
  for part in "${root_parts[@]}"; do
    [[ -z $part ]] && continue
    cur="$cur/$part"
    [[ ! -L $cur ]] || fail "ancestral symlink recusado: $cur"
    [[ ! -e $cur || -d $cur ]] || fail "ancestral não é diretório: $cur"
  done
  cur=$root
  IFS=/ read -ra parts <<< "$(dirname -- "$rel")"
  for part in "${parts[@]}"; do
    [[ $part == . ]] && continue
    cur="$cur/$part"
    if [[ -L $cur ]]; then fail "ancestral symlink recusado: $cur"; fi
    if [[ -e $cur && ! -d $cur ]]; then fail "ancestral não é diretório: $cur"; fi
  done
}
resolve_source() {
  local rel=$1 candidate real
  valid_rel "$rel" || fail "source inválido: $rel"
  candidate="$REPO/$rel"
  [[ -f $candidate && ! -L $candidate ]] || fail "source ausente, simbólica ou não regular: $rel"
  real=$(realpath -e -- "$candidate") || fail "source inválido: $rel"
  case "$real" in "$REPO_REAL"/*) ;; *) fail "source escapa do repositório: $rel" ;; esac
  printf '%s' "$real"
}

check_ancestors "$XDG_STATE_HOME" 'dots-arch/backups/journal.tsv'

# Journal fields are plain TSV data; destinations containing separators are rejected.
if [[ -n $BACKUP_ID ]]; then
  [[ $BACKUP_ID =~ ^[A-Za-z0-9._-]+$ && $BACKUP_ID != . && $BACKUP_ID != .. ]] || fail 'BACKUP_ID inválido'
  JOURNAL="$BACKUP_ROOT/$BACKUP_ID/journal.tsv"
  [[ -f $JOURNAL && ! -L $JOURNAL ]] || fail "backup não encontrado: $BACKUP_ID"
  restore_rows=()
  [[ ! -L "$BACKUP_ROOT/$BACKUP_ID" && ! -L "$BACKUP_ROOT/$BACKUP_ID/original" ]] || fail 'diretório de backup simbólico recusado'
  while IFS=$'\t' read -r kind dest backup fingerprint source_hash extra || [[ -n ${kind:-} ]]; do
    [[ -z ${kind:-} || $kind == \#* ]] && continue
    [[ -z ${extra:-} && -n ${fingerprint:-} && ( $kind == link || $kind == file ) ]] || fail 'journal inválido'
    valid_path_text "$dest" && valid_path_text "$backup" || fail 'journal contém path inválido'
    [[ $dest == /* && $dest != *'/../'* && $dest != */.. ]] || fail 'destino inválido no journal'
    [[ $dest == "$HOME/"* || $dest == "$XDG_CONFIG_HOME/"* ]] || fail 'destino fora de HOME/XDG no journal'
    [[ $backup == - || $backup == "$BACKUP_ROOT/$BACKUP_ID/original/"* && $backup != *'/../'* ]] || fail 'backup fora do diretório permitido'
    if [[ $kind == link ]]; then [[ ${source_hash:-} =~ ^[a-f0-9]{64}$ ]] || fail 'hash da source ausente no journal'; fi
    if [[ $dest == "$XDG_CONFIG_HOME/"* ]]; then check_ancestors "$XDG_CONFIG_HOME" "${dest#"$XDG_CONFIG_HOME/"}"
    else check_ancestors "$HOME" "${dest#"$HOME/"}"; fi
    printf -v row '%s\t%s\t%s\t%s\t%s' "$kind" "$dest" "$backup" "$fingerprint" "${source_hash:--}"
    restore_rows+=("$row")
  done < "$JOURNAL"
  ((${#restore_rows[@]})) || { log 'Backup sem alterações para restaurar.'; exit 0; }
  # Validate every recorded original and installed object before any mutation.
  for row in "${restore_rows[@]}"; do
    IFS=$'\t' read -r kind dest backup fp source_hash <<< "$row"
    if [[ $backup != - && ! -e $backup && ! -L $backup ]]; then fail "original do backup ausente: $backup"; fi
    # An interruption may have moved the original before installing its replacement.
    if [[ ! -e $dest && ! -L $dest && $backup != - ]]; then continue; fi
    if [[ $kind == link ]]; then
      [[ -L $dest && $(readlink -- "$dest") == "$fp" && -f $fp && $(hash_file "$fp") == "$source_hash" ]] || fail "conflito na restauração; preservado: $dest"
    else
      [[ -f $dest && ! -L $dest && $(hash_file "$dest") == "$fp" ]] || fail "conflito na restauração; preservado: $dest"
    fi
  done
  if [[ $ACTION == dry-run ]]; then log "Prévia: restauraria ${#restore_rows[@]} item(ns) de $BACKUP_ID."; exit 0; fi
  for ((i=${#restore_rows[@]}-1; i>=0; i--)); do
    IFS=$'\t' read -r kind dest backup fp source_hash <<< "${restore_rows[i]}"
    if [[ -e $dest || -L $dest ]]; then rm -- "$dest"; fi
    if [[ $backup != - && -e $backup || $backup != - && -L $backup ]]; then
      mkdir -p -- "$(dirname -- "$dest")"
      mv -- "$backup" "$dest"
    fi
  done
  log "Backup $BACKUP_ID restaurado."
  exit 0
fi

[[ -f $MANIFEST ]] || fail "manifest ausente: $MANIFEST"
# Preflight every selected row before any mutation.
rows=(); seen=(); dests=(); sources=(); modes=(); roots=(); profiles=()
while IFS= read -r line || [[ -n $line ]]; do
  [[ -z $line || $line == \#* ]] && continue
  [[ $line != *$'\r'* ]] || fail 'manifest contém CR'
  IFS=$'\t' read -r prof mode src root dest extra <<< "$line"
  [[ -n ${prof:-} && -n ${mode:-} && -n ${src:-} && -n ${root:-} && -n ${dest:-} && -z ${extra:-} ]] || fail 'linha do manifest precisa de cinco campos TSV'
  [[ $prof == all || $prof == portable || $prof == desktop ]] || fail "profile inválido: $prof"
  [[ $mode == link || $mode == seed || $mode == render ]] || fail "mode inválido: $mode"
  [[ $root == config || $root == home ]] || fail "root inválido: $root"
  valid_rel "$src" && valid_rel "$dest" || fail 'source/dest precisam ser paths relativos sem traversal'
  valid_path_text "$src" && valid_path_text "$dest" || fail 'paths do manifest não podem conter TAB/newline/CR'
  dest_root=$HOME; [[ $root == config ]] && dest_root=$XDG_CONFIG_HOME
  dest_abs="$dest_root/$dest"
  case "$dest_abs/" in "$REPO_REAL/"*) fail 'destino gerenciado fica dentro do repositório' ;; esac
  case "$REPO_REAL/" in "$dest_abs/"*) fail 'destino gerenciado contém o repositório' ;; esac
  case "$dest_abs/" in "$BACKUP_ROOT/"*) fail 'backup root sobrepõe destino gerenciado' ;; esac
  case "$BACKUP_ROOT/" in "$dest_abs/"*) fail 'backup root fica dentro de destino gerenciado' ;; esac
  [[ $prof == all || $prof == "$PROFILE" ]] || continue
  source_abs=$(resolve_source "$src")
  check_ancestors "$dest_root" "$dest"
  if [[ -d $dest_abs && ! -L $dest_abs ]]; then fail "diretório conflita com destino de arquivo: $dest_abs"; fi
  for old in "${dests[@]}"; do
    [[ $dest_abs != "$old" && $dest_abs != "$old/"* && $old != "$dest_abs/"* ]] || fail "destinos duplicados/sobrepostos: $old e $dest_abs"
  done
  # A backup tree must not overlap any managed target.
  case "$dest_abs/" in "$BACKUP_ROOT/"*) fail 'backup root sobrepõe destino gerenciado' ;; esac
  case "$BACKUP_ROOT/" in "$dest_abs/"*) fail 'backup root fica dentro de destino gerenciado' ;; esac
  if [[ $mode == render ]]; then
    grep -Fq '@CONFIG_HOME@' "$source_abs" || fail "template render sem @CONFIG_HOME@: $src"
  fi
  dests+=("$dest_abs"); sources+=("$source_abs"); modes+=("$mode"); roots+=("$dest_root"); profiles+=("$prof")
done < "$MANIFEST"

# Plan, including which operations are no-ops. No directories are created here.
changes=(); expected=(); originals=()
for i in "${!dests[@]}"; do
  d=${dests[i]}; s=${sources[i]}; m=${modes[i]}; want=''
  if [[ $m == link ]]; then
    want=$s
    if link_is_correct "$d" "$want"; then changes+=(0); expected+=("$want"); originals+=(0); continue; fi
    [[ ! -e $d && ! -L $d ]] || { [[ -d $d && ! -L $d ]] && fail "diretório conflitante: $d"; }
  elif [[ $m == seed ]]; then
    if [[ -e $d || -L $d ]]; then changes+=(0); expected+=(preserve); originals+=(0); continue; fi
    want=$(hash_file "$s")
  else
    # Render only the literal token; all other bytes are preserved.
    want=$(sed "s|@CONFIG_HOME@|$(sed_replacement "$XDG_CONFIG_HOME")|g" "$s" | sha256sum | { read -r h _; printf '%s' "$h"; })
    if [[ -f $d && ! -L $d && $(hash_file "$d") == "$want" ]]; then changes+=(0); expected+=("$want"); originals+=(0); continue; fi
    [[ ! -e $d && ! -L $d ]] || { [[ -d $d && ! -L $d ]] && fail "diretório conflitante: $d"; }
  fi
  changes+=(1); expected+=("$want"); if [[ -e $d || -L $d ]]; then originals+=(1); else originals+=(0); fi
done

if [[ $ACTION == dry-run ]]; then
  count=0
  for i in "${!dests[@]}"; do if [[ ${changes[i]} == 1 ]]; then log "Aplicaria ${modes[i]}: ${dests[i]}"; ((count+=1)); else log "Sem alteração: ${dests[i]}"; fi; done
  log "Prévia concluída; $count alteração(ões), nenhum arquivo foi criado."
  exit 0
fi

changes_count=0; for c in "${changes[@]}"; do [[ $c == 1 ]] && ((changes_count+=1)); done
((changes_count)) || { log 'Nenhuma alteração necessária.'; exit 0; }
BACKUP_ID=$(date -u +%Y%m%dT%H%M%SZ)-$$
BACKUP_DIR="$BACKUP_ROOT/$BACKUP_ID"
(umask 077; mkdir -p -- "$BACKUP_ROOT"; mkdir -- "$BACKUP_DIR"; mkdir -- "$BACKUP_DIR/original"; : > "$BACKUP_DIR/journal.tsv") || fail 'não foi possível criar backup privado'
chmod 700 "$BACKUP_DIR" "$BACKUP_DIR/original"
TEMP_FILE=
rollback() {
  local rc=${1:-$?} i kind dest backup fp source_hash
  trap - ERR INT TERM
  [[ -z $TEMP_FILE ]] || rm -f -- "$TEMP_FILE"
  for ((i=${journal_count:-0}-1; i>=0; i--)); do
    IFS=$'\t' read -r kind dest backup fp source_hash <<< "${journal_rows[i]}"
    if [[ $kind == link ]]; then
      [[ -L $dest && $(readlink -- "$dest") == "$fp" && -f $fp && $(hash_file "$fp") == "$source_hash" ]] && rm -- "$dest" || true
    else
      [[ -f $dest && ! -L $dest && $(hash_file "$dest") == "$fp" ]] && rm -- "$dest" || true
    fi
    if [[ $backup != - && ( -e $backup || -L $backup ) && ! -e $dest && ! -L $dest ]]; then mv -- "$backup" "$dest" || true; fi
  done
  printf 'Falha; rollback conservador executado. Backup de recuperação: %s\n' "$BACKUP_ID" >&2
  exit "$rc"
}
trap rollback ERR
trap 'rollback 130' INT
trap 'rollback 143' TERM
journal_rows=(); journal_count=0
for i in "${!dests[@]}"; do
  [[ ${changes[i]} == 1 ]] || continue
  d=${dests[i]}; s=${sources[i]}; m=${modes[i]}; fp=${expected[i]}; b=-
  if [[ ${originals[i]} == 1 ]]; then b="$BACKUP_DIR/original/$i"; fi
  if [[ $m == link ]]; then kind=link; fp=$s; else kind=file; fi
  # Persist intent first so interruption/failure can be recovered conservatively.
  source_hash=-; [[ $kind == link ]] && source_hash=$(hash_file "$s")
  printf '%s\t%s\t%s\t%s\t%s\n' "$kind" "$d" "$b" "$fp" "$source_hash" >> "$BACKUP_DIR/journal.tsv"
  printf -v row '%s\t%s\t%s\t%s\t%s' "$kind" "$d" "$b" "$fp" "$source_hash"
  journal_rows+=("$row"); ((journal_count+=1))
  if [[ $d == "$XDG_CONFIG_HOME/"* ]]; then check_ancestors "$XDG_CONFIG_HOME" "${d#"$XDG_CONFIG_HOME/"}"
  else check_ancestors "$HOME" "${d#"$HOME/"}"; fi
  mkdir -p -- "$(dirname -- "$d")"
  if [[ $b != - ]]; then mv -- "$d" "$b"; fi
  if [[ $m == link ]]; then ln -s -- "$s" "$d"
  else
    tmp=$(mktemp -- "$d.dots-arch-tmp.XXXXXXXX")
    TEMP_FILE=$tmp
    if [[ $m == seed ]]; then cp --preserve=mode -- "$s" "$tmp"
    else sed "s|@CONFIG_HOME@|$(sed_replacement "$XDG_CONFIG_HOME")|g" "$s" > "$tmp"; chmod --reference="$s" "$tmp" 2>/dev/null || true
    fi
    mv -- "$tmp" "$d"; TEMP_FILE=
  fi
done
trap - ERR INT TERM
log "Aplicação concluída. Backup: $BACKUP_ID"
