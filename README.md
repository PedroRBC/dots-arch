# dots-arch

Configurações pessoais do desktop Arch/CachyOS, com instalação por arquivo, backup e symlinks. A infraestrutura do TrueNAS permanece somente local, ignorada pelo Git, e **não é executada pelo instalador do desktop**.

## Padrão do repositório

```text
home/                 arquivos declarativos reais, espelhando a home
profiles/portable/    monitores automáticos, sem ajustes específicos de hardware
profiles/desktop/     três monitores e integrações deste desktop
seeds/                temas e preferências iniciais graváveis, sem symlinks
manifests/desktop.tsv lista explícita do que instalar e onde
packages/             pacotes oficiais, CachyOS e opcionais
examples/             ajustes locais opcionais, não instalados automaticamente
infra/truenas/        opcional e local: infraestrutura do NAS, ignorada pelo Git
tests/                testes isolados do instalador e validação das configurações
script.sh             entrada única do bootstrap do desktop
```

**O sentido dos links é importante:** `~/.config/kitty/kitty.conf` aponta para `home/.config/kitty/kitty.conf` neste clone. Não coloque no Git um link para um arquivo que só existe na sua máquina: isso não salva seu conteúdo. Mantenha o clone em um caminho estável; se o mover, reaplique o instalador a partir da nova localização.

## Nova instalação

Requer Linux, Bash 4.3+ e ferramentas GNU usuais (`coreutils`, `sed`, `grep`). Execute como seu usuário, **não com sudo**. Python 3.11+, Fish e Lua/luac são necessários apenas para a validação completa das configurações.

```bash
git clone https://github.com/PedroRBC/dots-arch.git ~/Projects/dots-arch
cd ~/Projects/dots-arch

# Só mostra o plano: não escreve nada nem instala programas.
./script.sh
# Equivalente:
./script.sh --dry-run

# Aplica arquivos e links, preservando conflitos em backup.
./script.sh --apply
```

O perfil padrão é **portable**: modo preferido e escala automática para as saídas disponíveis, sem nomes de conectores, HDR, VRR, direct scanout ou atalhos direcionados a monitores inexistentes.

Para reproduzir **este desktop**, confira os arquivos em `profiles/desktop/hypr/` antes de usar:

```bash
./script.sh --profile desktop --dry-run
./script.sh --profile desktop --apply
```

Esse perfil preserva DP-2 (1080p/240 Hz), DP-3 (1080p/60 Hz), HDMI-A-1 rotacionado, distribuição de workspaces, VRR/direct scanout e captura global T3. Também preserva duas políticas **preexistentes**, não recomendadas como defaults de outro computador: autorização X11 de root local (`xhost +SI:localuser:root`) e `allow_token_by_default = true` no portal. Revise/desative essas opções se não precisar delas. O perfil portátil não as habilita.

### Pacotes: etapa separada e opcional

Aplicar configurações **não instala pacotes**. Para conferir os pacotes e, separadamente, instalar os disponíveis:

```bash
./script.sh --install-packages --dry-run
./script.sh --install-packages --apply
# Inclui Alacritty, Micro, GitHub CLI e xorg-xhost:
./script.sh --install-packages --with-optional --apply
```

A elevação via `sudo` fica restrita à operação explícita de pacotes. As listas são `packages/arch.txt`, `packages/cachyos.txt` e `packages/optional.txt`. Não são adicionados repositórios, não é usado AUR automaticamente e não é feita atualização parcial com `pacman -Sy`.

**Compatibilidade:** esta configuração usa **Hyprland 0.56.2 com API Lua `hl.*`** e **Noctalia nativo 5.3.0 com TOML**. Versões futuras precisam de revisão; versões antigas do compositor com apenas `.conf` não são compatíveis. Não substituir por `noctalia-shell`/Quickshell.

`swash`, `helium-browser-bin` e `cachyos-fish-config` foram encontrados nos repositórios CachyOS desta instalação. Em Arch sem esses repositórios, obtenha alternativas compatíveis por conta própria ou ajuste as configurações. O navegador dos atalhos é Helium; UWSM mantém Firefox, como na configuração original. Capturas e imagens do clipboard usam Swash. A ausência desses programas não é resolvida apenas criando os links.

O cursor **Bibata-Modern-Ice** existe localmente neste sistema e na base `/etc/skel` de `cachyos-hypr-noctalia`; seus binários não foram copiados ao Git. Em outro sistema, instale o cursor de uma fonte confiável ou altere as referências em UWSM, GTK e `.icons/default/index.theme`. Não instale um metapacote amplo apenas para obter o cursor sem revisar suas alterações.

## O que é gerenciado

- Hyprland Lua modular, atalhos físicos da fileira numérica, regras e aparência.
- Noctalia: barra, widgets nativos, aparência e comandos de captura.
- Fish: PATH idempotente, integração opcional CachyOS/uv e preferências selecionadas do Pure.
- UWSM, Kitty, Alacritty, btop, GTK3/4, Qt6ct e Micro com colorscheme Catppuccin.
- Swash: somente preferências iniciais, sem estado de ferramentas.

O manifesto usa cinco campos separados por **TAB**:

```text
perfil    operação    fonte-relativa-ao-repo    raiz    destino-relativo
```

Perfis: `all`, `portable` ou `desktop`. Raízes: `config` (`${XDG_CONFIG_HOME:-$HOME/.config}`) e `home` (`$HOME`). Operações:

- **link:** arquivo estático no repo; arquivo ou link conflitante é preservado em backup antes da substituição.
- **seed:** copia somente se o destino estiver ausente. Não sobrescreve preferências ou temas já existentes; o aplicativo pode gravar sua cópia local.
- **render:** gera um arquivo local a partir de template, substituindo `@CONFIG_HOME@` pelo caminho real. Qt6ct usa isso porque não expande `/home/$USER` nesse campo. Alacritty também usa uma cópia local: o post-hook do Noctalia reescreve imports relativos e poderia inserir um caminho específico da máquina no repo. Mudanças são protegidas por backup.

Os temas `noctalia.*` são seeds, não links para o repo. Assim, a geração dinâmica do Noctalia não modifica esses arquivos no Git. Os imports/includes necessários já estão configurados para que os hooks instalados de Kitty, GTK e btop não precisem reescrever suas fontes estáticas.

### Noctalia: preferências não são todo o estado

O Noctalia também grava overrides em `~/.local/state/noctalia/settings.toml`. Esse arquivo **não é versionado, substituído nem linkado**: mistura aparência, integrações e configurações locais. Os overrides atuais continuam tendo precedência neste sistema.

Foram promovidas à configuração declarativa apenas preferências visuais confirmadas na referência instalada (barra, relógio e indicadores de workspaces). Fonte Fira Code, paleta comunitária Oxocarbon, plugins, wallpaper, avatar e opções específicas de monitor precisam ser revisados/configurados pela UI em uma instalação nova. O plugin TrueNAS referenciado fora deste repo não é incluído nem baixado automaticamente.

Mudanças feitas na UI podem ficar nos overrides, **sem aparecer no Git**. Para preservá-las, exporte/revise apenas as preferências desejadas, valide o esquema e atualize `home/.config/noctalia/config.toml`. Nunca copie toda a pasta de estado para o repo.

### Arquivos intencionalmente não gerenciados

Histórico e variáveis universais do Fish, clipboard, notificações antigas, caches, bancos, autenticação, perfis de navegadores, VS Code/User bruto, identidade Git, configurações de agentes, avatar, wallpapers pessoais, WayVNC/TLS, Sunshine, greeter e credenciais do NAS ficam fora. Arquivos desconhecidos dentro das pastas dos apps são preservados.

`examples/fish/homecare-android.fish.example` guarda um exemplo opcional do ambiente Android específico desta máquina. Ele não é ativado automaticamente. Ajuste SDK/JDK/AVD antes de copiá-lo para sua configuração local.

## Backups e restauração

Cada aplicação com mudanças cria um backup privado fora do repo em:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/dots-arch/backups/<ID>/
```

Guarde o ID informado ao final. Para desfazer aquela aplicação:

```bash
./script.sh --restore <ID> --dry-run
./script.sh --restore <ID> --apply
```

A restauração é conservadora: se um destino ou o conteúdo instalado tiver sido alterado posteriormente, ele é preservado e o conflito é informado. Não apague o backup até verificar a recuperação. Uma segunda aplicação sem alterações é no-op; seeds existentes nunca são atualizados à força.

O instalador faz preflight completo, recusa diretórios conflitantes no lugar de arquivos, fontes ausentes/externas, caminhos inválidos e ancestrais simbólicos inesperados. Isso evita seguir um link para outro lugar e sobrescrever dados indiretamente. `HOME` e as variáveis XDG devem apontar para caminhos absolutos. Os templates atuais não aceitam aspas duplas ou barras invertidas em `XDG_CONFIG_HOME`; espaços são suportados. Execuções simultâneas devem ser evitadas.

O instalador não reinicia Hyprland/Noctalia, não habilita serviços, não muda o login e não contata o NAS. Aplicativos podem observar as mudanças e recarregar configurações por conta própria. Se um aplicativo salvar um arquivo substituindo o symlink, confira a diferença, incorpore apenas a configuração desejada ao repo e reaplique com backup; não há sincronização automática de arquivos de volta para o Git.

A reorganização inicial também preservou a estrutura anterior (incluindo os links antigos e `--help/`) em `~/.local/state/dots-arch/migrations/`. Esse arquivo de migração é separado dos backups transacionais do instalador.

## Adicionar uma configuração

1. Identifique o arquivo declarativo real e revise seu conteúdo. Não importe uma pasta inteira de aplicativo.
2. Copie-o para `home/`, preservando o caminho relativo. Para saída gerada/estado misto, use uma seed sanitizada em `seeds/` ou deixe local.
3. Remova caminhos pessoais rígidos, tokens e identidade; ajustes da máquina devem ser opcionais ou ficar em um perfil.
4. Adicione uma linha explícita em `manifests/desktop.tsv`.
5. Atualize os pacotes/documentação e rode os testes e a prévia.
6. Revise `git status --short --untracked-files=all` antes de qualquer commit. `.gitignore` é uma barreira adicional, **não uma garantia de ausência de segredos**.

## Verificação

```bash
bash -n script.sh tests/test-install.sh
bash tests/test-install.sh
python3 -I tests/validate-configs.py
python3 -I tests/test-manifest.py
./script.sh --profile desktop --dry-run
```

Os testes usam repositório-fixture e `HOME`/XDG temporários: não instalam pacotes, não alteram o desktop real e não acessam o NAS. A validação de sintaxe não garante que uma versão diferente dos apps aceite todas as opções. ShellCheck pode ser usado quando instalado; ele não é requisito do bootstrap.

## TrueNAS

`infra/truenas/` foi preservada no disco, mas a pasta inteira está no `.gitignore`: não é versionada, publicada nem baixada ao clonar este repositório. Sua documentação contém domínios e topologia operacional. Mantenha essa infraestrutura em armazenamento ou repositório privado separado; não use `git add -f` para incluí-la aqui.

Quando essa pasta existir localmente, consulte `infra/truenas/README.md` e `infra/truenas/client/README.md`. Nenhuma implantação, montagem, instalação de app ou comunicação com o NAS faz parte deste bootstrap. A assinatura histórica do instalador de mounts foi mantida para reconhecer unidades existentes; `infra/truenas/nas/prepare.py` é histórico e não deve ser reaplicado como se fosse o estado atual.
