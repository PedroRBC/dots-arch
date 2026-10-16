#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_SCRIPT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/script.sh
TMP=$(mktemp -d)
trap 'rm -rf -- "$TMP"' EXIT
REPO="$TMP/repo with spaces"
HOME_FIX="$TMP/home with spaces"
mkdir -p "$REPO/manifests" "$REPO/packages" "$HOME_FIX"
cp -- "$SOURCE_SCRIPT" "$REPO/script.sh"
mkdir -p "$REPO/home/.config/fish" "$REPO/templates" "$REPO/seeds"
printf 'hello\n' > "$REPO/home/.config/fish/config.fish"
printf 'colors = "@CONFIG_HOME@/colors"\n' > "$REPO/templates/qt6ct.conf.in"
printf 'theme\n' > "$REPO/seeds/theme.conf"
CONFIG="$HOME_FIX/config files"
STATE="$HOME_FIX/state files"
mkdir -p "$CONFIG"
export HOME="$HOME_FIX" XDG_CONFIG_HOME="$CONFIG" XDG_STATE_HOME="$STATE"

pass=0
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
ok() { ((pass+=1)); printf 'ok %02d - %s\n' "$pass" "$*"; }
run() { bash "$REPO/script.sh" "$@"; }
manifest() { printf '%s\n' "$@" > "$REPO/manifests/desktop.tsv"; }

# Defaults and dry-run must be entirely read-only.
manifest $'all\tlink\thome/.config/fish/config.fish\tconfig\tfish/config.fish'
mkdir -p "$TMP/bin"
for cmd in pacman sudo; do printf '#!/usr/bin/env bash\nprintf "%s\\n" "$0 $*" >> "%s"\n' "$cmd" "$TMP/package-calls" > "$TMP/bin/$cmd"; chmod +x "$TMP/bin/$cmd"; done
export PATH="$TMP/bin:$PATH"
run --dry-run > "$TMP/dry.out"
[[ ! -e "$CONFIG/fish" && ! -e "$STATE" ]] || fail 'dry-run deixou arquivos'
ok 'dry-run sem escrita'
[[ ! -s "$TMP/package-calls" ]] || fail 'stub pacman/sudo foi chamado'
ok 'defaults não chamam pacman/sudo'

# Apply, idempotence, then restore exact original.
mkdir -p "$CONFIG/fish"
printf 'mine\n' > "$CONFIG/fish/config.fish"
run --apply > "$TMP/apply.out"
[[ -L "$CONFIG/fish/config.fish" && $(readlink "$CONFIG/fish/config.fish") == "$REPO/home/.config/fish/config.fish" ]] || fail 'link incorreto'
BACKUP=$(sed -n 's/^Aplicação concluída\. Backup: //p' "$TMP/apply.out")
[[ -n $BACKUP && -f "$STATE/dots-arch/backups/$BACKUP/original/0" ]] || fail 'backup original ausente'
ok 'apply cria link e guarda conflito'
run --apply > "$TMP/noop.out"
grep -q 'Nenhuma alteração' "$TMP/noop.out" || fail 'reaplicação não foi noop'
ok 'apply idempotente sem backup vazio'
run --restore "$BACKUP" --dry-run >/dev/null
run --restore "$BACKUP" --apply >/dev/null
[[ -f "$CONFIG/fish/config.fish" && ! -L "$CONFIG/fish/config.fish" ]] || fail 'restore não recuperou original'
[[ $(<"$CONFIG/fish/config.fish") == mine ]] || fail 'conteúdo original incorreto'
ok 'restore recupera original'

# A changed source behind an installed link invalidates restore.
rm -f "$CONFIG/fish/config.fish"
run --apply > "$TMP/apply2.out"
BACKUP2=$(sed -n 's/^Aplicação concluída\. Backup: //p' "$TMP/apply2.out")
printf 'changed source\n' > "$REPO/home/.config/fish/config.fish"
if run --restore "$BACKUP2" --apply > /dev/null 2>&1; then fail 'restore aceitou source modificada'; fi
[[ -L "$CONFIG/fish/config.fish" ]] || fail 'restore conflitante removeu link'
ok 'restore recusa source de link modificada'
# Reset fixture source to keep subsequent checks predictable.
printf 'hello\n' > "$REPO/home/.config/fish/config.fish"

# Broken symlink is a conflict and must be backed up/restorable.
rm -f "$CONFIG/fish/config.fish"
ln -s "$TMP/nonexistent" "$CONFIG/fish/config.fish"
run --apply > "$TMP/apply3.out"
BACKUP3=$(sed -n 's/^Aplicação concluída\. Backup: //p' "$TMP/apply3.out")
[[ -L "$CONFIG/fish/config.fish" && -L "$STATE/dots-arch/backups/$BACKUP3/original/0" ]] || fail 'broken symlink não foi preservado'
run --restore "$BACKUP3" --apply >/dev/null
[[ $(readlink "$CONFIG/fish/config.fish") == "$TMP/nonexistent" ]] || fail 'broken symlink não restaurado'
ok 'broken symlink é preservado'

# A failed later link creation rolls back only this run's changes.
mkdir -p "$CONFIG/partial"
printf 'original one\n' > "$CONFIG/partial/one"
printf 'original two\n' > "$CONFIG/partial/two"
manifest $'all\tlink\thome/.config/fish/config.fish\tconfig\tpartial/one' $'all\tlink\thome/.config/fish/config.fish\tconfig\tpartial/two'
mkdir -p "$TMP/failbin"
printf '#!/usr/bin/env bash\nn=0; [[ ! -f "%s" ]] || read -r n < "%s"; n=$((n+1)); printf "%%s\\n" "$n" > "%s"; (( n != 2 )) || exit 1; exec /usr/bin/ln "$@"\n' "$TMP/ln-count" "$TMP/ln-count" "$TMP/ln-count" > "$TMP/failbin/ln"
chmod +x "$TMP/failbin/ln"
OLD_PATH=$PATH; export PATH="$TMP/failbin:$PATH"
if run --apply >/dev/null 2>&1; then fail 'falha simulada do ln não ocorreu'; fi
export PATH=$OLD_PATH
[[ ! -L "$CONFIG/partial/one" && ! -L "$CONFIG/partial/two" ]] || fail 'rollback parcial deixou links'
[[ $(<"$CONFIG/partial/one") == 'original one' && $(<"$CONFIG/partial/two") == 'original two' ]] || fail 'rollback não recuperou originals'
ok 'falha parcial restaura somente operações da execução'

# Full preflight prevents partial mutation when a later entry is a directory.
rm -f "$CONFIG/fish/config.fish"
mkdir -p "$CONFIG/fish/other.conf"
manifest $'all\tlink\thome/.config/fish/config.fish\tconfig\tfish/config.fish' $'all\tlink\thome/.config/fish/config.fish\tconfig\tfish/other.conf'
if run --apply > /dev/null 2>&1; then fail 'directory conflict foi aceito'; fi
[[ ! -e "$CONFIG/fish/config.fish" ]] || fail 'preflight deixou alteração parcial'
ok 'directory conflict bloqueia antes de mutar'
rmdir "$CONFIG/fish/other.conf"

# Manifest traversal, missing source and symlinked ancestors are rejected.
manifest $'all\tlink\t../outside\tconfig\tbad'
if run --dry-run >/dev/null 2>&1; then fail 'source traversal aceita'; fi
manifest $'all\tlink\tmissing\tconfig\tbad'
if run --dry-run >/dev/null 2>&1; then fail 'source ausente aceita'; fi
mkdir -p "$TMP/outside" "$CONFIG/escape"
rm -rf "$CONFIG/escape"
ln -s "$TMP/outside" "$CONFIG/escape"
manifest $'all\tlink\thome/.config/fish/config.fish\tconfig\tescape/child'
if run --apply >/dev/null 2>&1; then fail 'ancestor symlink aceita'; fi
[[ ! -e "$TMP/outside/child" ]] || fail 'gravou através de symlink'
ok 'traversal, missing source e ancestor symlink recusados'

# Profiles, seeds preserve existing entries, and render materializes local absolute path.
manifest $'all\tlink\thome/.config/fish/config.fish\tconfig\tcommon' $'desktop\tseed\tseeds/theme.conf\tconfig\tdesktop-theme' $'portable\tseed\tseeds/theme.conf\tconfig\tportable-theme' $'all\trender\ttemplates/qt6ct.conf.in\tconfig\tqt6ct/qt6ct.conf'
run --apply --profile portable > "$TMP/profile.out"
[[ -e "$CONFIG/portable-theme" && ! -e "$CONFIG/desktop-theme" ]] || fail 'seleção portable incorreta'
[[ $(<"$CONFIG/qt6ct/qt6ct.conf") == "colors = \"$CONFIG/colors\"" ]] || fail 'render não substituiu token'
ok 'perfil portable e render corretos'
run --apply --profile desktop >/dev/null
[[ -e "$CONFIG/desktop-theme" ]] || fail 'perfil desktop não aplicou'
ok 'perfil desktop aplicado'
printf 'user data\n' > "$CONFIG/portable-theme"
run --apply --profile portable >/dev/null
[[ $(<"$CONFIG/portable-theme") == 'user data' ]] || fail 'seed sobrescreveu existente'
ok 'seed preserva destino existente'
rm -f "$CONFIG/portable-theme"
printf 'external target\n' > "$TMP/external-seed"
ln -s "$TMP/external-seed" "$CONFIG/portable-theme"
run --apply --profile portable >/dev/null
[[ -L "$CONFIG/portable-theme" && $(readlink "$CONFIG/portable-theme") == "$TMP/external-seed" ]] || fail 'seed tocou symlink existente'
[[ $(<"$TMP/external-seed") == 'external target' ]] || fail 'seed escreveu através de symlink'
ok 'seed preserva symlink externo sem escrever através dele'

# A later user edit is never deleted by restore.
rm -f "$CONFIG/common"
run --apply > "$TMP/apply4.out"
BACKUP4=$(sed -n 's/^Aplicação concluída\. Backup: //p' "$TMP/apply4.out")
rm "$CONFIG/common"
printf 'later edit\n' > "$CONFIG/common"
if run --restore "$BACKUP4" --apply >/dev/null 2>&1; then fail 'restore removeu edição posterior'; fi
[[ $(<"$CONFIG/common") == 'later edit' ]] || fail 'edição posterior perdida'
ok 'restore protege alterações posteriores'

# Tampered restore journal cannot redirect a write outside managed roots.
mkdir -p "$STATE/dots-arch/backups/attack/original"
printf 'file\t%s\t-\tdeadbeef\t-\n' "$TMP/important" > "$STATE/dots-arch/backups/attack/journal.tsv"
if run --restore attack --apply >/dev/null 2>&1; then fail 'journal traversal/tampering aceito'; fi
[[ ! -e "$TMP/important" ]] || fail 'journal tocou path externo'
ok 'restore valida paths do journal'

# Recovery also works if an interruption moved the original but installed nothing.
mkdir -p "$STATE/dots-arch/backups/interrupted/original"
printf 'saved original\n' > "$STATE/dots-arch/backups/interrupted/original/0"
hash=$(sha256sum "$REPO/home/.config/fish/config.fish"); hash=${hash%% *}
printf 'link\t%s\t%s\t%s\t%s\n' "$CONFIG/interrupted" "$STATE/dots-arch/backups/interrupted/original/0" "$REPO/home/.config/fish/config.fish" "$hash" > "$STATE/dots-arch/backups/interrupted/journal.tsv"
run --restore interrupted --apply >/dev/null
[[ $(<"$CONFIG/interrupted") == 'saved original' ]] || fail 'original interrompido não recuperado'
ok 'restore recupera original quando replacement ficou ausente'

manifest $'all\tlink\thome/.config/fish/config.fish\tconfig\tsignal-test'
printf 'before signal\n' > "$CONFIG/signal-test"
printf '#!/usr/bin/env bash\nkill -TERM "$PPID"\nexit 1\n' > "$TMP/failbin/ln"
OLD_PATH=$PATH; export PATH="$TMP/failbin:$PATH"
if run --apply >/dev/null 2>&1; then fail 'signal não interrompeu apply'; fi
export PATH=$OLD_PATH
[[ ! -L "$CONFIG/signal-test" && $(<"$CONFIG/signal-test") == 'before signal' ]] || fail 'signal não restaurou original'
ok 'SIGTERM executa rollback'

# Lexically aliased destinations must not evade overlap checks.
manifest $'all\tlink\thome/.config/fish/config.fish\tconfig\talias/file' $'all\tlink\thome/.config/fish/config.fish\tconfig\talias/./file'
if run --apply >/dev/null 2>&1; then fail 'dot path aceito'; fi
[[ ! -e "$CONFIG/alias" ]] || fail 'alias deixou alteração parcial'
manifest $'all\tlink\thome/.config/fish/config.fish\tconfig\t..'
if run --apply >/dev/null 2>&1; then fail 'bare traversal aceito'; fi
ok 'aliases e traversal de destino recusados'

manifest $'all\tlink\thome/.config/fish/config.fish\tconfig\tsame'
if XDG_CONFIG_HOME="$REPO" run --apply >/dev/null 2>&1; then fail 'destino dentro do repo aceito'; fi
ok 'destinos dentro do repositório recusados'

mkdir -p "$TMP/external-state"
ln -s "$TMP/external-state" "$HOME_FIX/state-link"
if XDG_STATE_HOME="$HOME_FIX/state-link" run --apply >/dev/null 2>&1; then fail 'state symlink aceito'; fi
[[ ! -e "$TMP/external-state/dots-arch" ]] || fail 'backup escreveu através de symlink'
ok 'ancestral simbólico dos backups recusado'

ln -s "$REPO/home/.config/fish/config.fish" "$REPO/source-link"
manifest $'all\tlink\tsource-link\tconfig\tbad-source'
if run --apply >/dev/null 2>&1; then fail 'source symlink aceita'; fi
ok 'fontes precisam ser arquivos reais'

# Package previews query availability, but only explicit apply may invoke sudo.
printf 'fixture-package\n' > "$REPO/packages/arch.txt"
printf 'optional-package\n' > "$REPO/packages/optional.txt"
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$*" >> "%s"\n[[ $1 == -Si ]]\n' "$TMP/pacman-args" > "$TMP/bin/pacman"
printf '#!/usr/bin/env bash\nprintf "called\\n" >> "%s"\n' "$TMP/sudo-calls" > "$TMP/bin/sudo"
run --install-packages --dry-run > "$TMP/packages.out"
grep -q 'fixture-package' "$TMP/packages.out" || fail 'prévia não listou pacote'
[[ ! -e "$TMP/sudo-calls" ]] || fail 'prévia chamou sudo'
run --install-packages --with-optional --apply >/dev/null
[[ -s "$TMP/sudo-calls" ]] || fail 'apply explícito não chamou stub sudo'
ok 'pacotes têm prévia sem sudo e apply separado'

printf '\n%d testes passaram.\n' "$pass"
