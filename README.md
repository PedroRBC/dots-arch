# dots-arch

Configurações pessoais do desktop Arch/CachyOS, com instalação por arquivo, backup e symlinks. A infraestrutura do TrueNAS permanece somente local, ignorada pelo Git, e **não é executada pelo instalador do desktop**.

## Padrão do repositório

```text
home/                 arquivos declarativos reais, espelhando a home
profiles/portable/    monitores automáticos, sem ajustes específicos de hardware
profiles/desktop/     três monitores e integrações deste desktop
seeds/                temas e preferências iniciais graváveis, sem symlinks
assets/arc/           wallpapers ARC originais em SVG e PNG
scripts/              ativação/recovery do tema e geração dos wallpapers
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

A configuração declarativa inclui a paleta customizada ARC, acabamento da barra, relógio e indicadores de workspaces. Fonte Fira Code, plugins, avatar e opções específicas de monitor continuam locais. O helper ARC seleciona a paleta e os wallpapers por IPC, sem substituir o arquivo inteiro de overrides nem reorganizar a barra. O plugin TrueNAS referenciado fora deste repo não é incluído nem baixado automaticamente.

Mudanças feitas na UI podem ficar nos overrides, **sem aparecer no Git**. Para preservá-las, exporte/revise apenas as preferências desejadas, valide o esquema e atualize `home/.config/noctalia/config.toml`. Nunca copie toda a pasta de estado para o repo.

### Arquivos intencionalmente não gerenciados

Histórico e variáveis universais do Fish, clipboard, notificações antigas, caches, bancos, autenticação, perfis de navegadores, VS Code/User bruto, identidade Git, configurações de agentes, avatar, wallpapers pessoais, WayVNC/TLS, Sunshine, greeter e credenciais do NAS ficam fora. Arquivos desconhecidos dentro das pastas dos apps são preservados.

`examples/fish/homecare-android.fish.example` guarda um exemplo opcional do ambiente Android específico desta máquina. Ele não é ativado automaticamente. Ajuste SDK/JDK/AVD antes de copiá-lo para sua configuração local.

## ARC // Hyper Tech

Reinterpretação de interfaces de engenharia Stark/JARVIS com a clareza do HUD de Peter Parker: navy profundo, ciano para foco, azul secundário, âmbar para atenção e coral para erro. Os elementos HUD ficam na periferia dos wallpapers; o centro permanece livre para trabalhar. Não há telemetria fictícia, plugins novos ou sons. O tema estático não requer serviço adicional; o wallpaper Motion opcional usa uma unidade transitória por sessão.

- `home/.config/noctalia/palettes/Arc.json`: variantes dark/light e ANSI completas, no formato nativo v5.
- `assets/arc/`: fontes SVG e PNGs originais em 3840×2160 e 1536×2732. Não são artes copiadas dos filmes.
- Bordas ciano/azul, cantos de 6 px e terminais com opacidade 0.94. Gaps, espessura das bordas, blur, atalhos, fontes, padding e regras permanecem como antes. A extensão Motion refina somente os cinco nós de animação já configurados, sem novos overrides de filhos.
- Kitty, Alacritty, GTK, Qt, KDE e btop recebem as cores pelos templates já existentes. Alacritty não sobrepõe mais o import com uma paleta Nord fixa. Micro permanece Catppuccin.
- O template Hyprland do Noctalia fica desabilitado: seu post-hook poderia reescrever o Lua versionado.

### Aplicar e recuperar

**Antes de editar arquivos já linkados**, capture o baseline. O instalador não consegue desfazer uma edição posterior feita diretamente na fonte de um symlink:

```bash
python3 -I scripts/hyper-tech.py --backup
# Guarde o ID; só então edite as fontes desejadas.

./script.sh --profile desktop --dry-run
./script.sh --profile desktop --apply
python3 -I scripts/hyper-tech.py                       # apenas prévia
python3 -I scripts/hyper-tech.py --from-backup <ID> --apply
```

Em uma instalação nova, `python3 -I scripts/hyper-tech.py --apply` captura os arquivos presentes e ativa o tema. Esse backup não representa fontes anteriores às edições já feitas no clone. O helper requer a sessão Hyprland/Noctalia ativa e assets instalados; não instala pacotes nem encerra a sessão. Recarrega somente `config.colors` e `config.decorations` por `hyprctl eval`, sem reaplicar regras de monitores, binds ou autostart. Escolhe landscape/portrait pela geometria e transformação de cada saída, incluindo saídas virtuais.

Backups do tema ficam em `${XDG_STATE_HOME:-$HOME/.local/state}/dots-arch/themes/<ID>/`, com diretório 0700 e cópias 0600. Incluem fontes afetadas, saídas auditadas dos templates e metadados visuais; **não os publique**. Depois da aplicação:

```bash
python3 -I scripts/hyper-tech.py --restore <ID>          # verifica conflitos, não escreve
python3 -I scripts/hyper-tech.py --restore <ID> --apply  # restaura aparência
```

A recuperação verifica todos os fingerprints antes de escrever e recusa alterações posteriores, inclusive no estado misto e nas preferências GTK. Restaura as fontes/saídas salvas e recupera paleta, modo e wallpapers por IPC; não substitui integralmente `settings.toml`. Se houver conflito, preserve as alterações novas e compare manualmente as cópias privadas. `--seal <ID> --apply` é uma operação de manutenção: atualiza o ponto final do journal, não deve ser usado para ignorar conflitos desconhecidos. Os assets ARC instalados continuam disponíveis após o rollback; sua instalação tem o backup separado do `script.sh`.

O helper permite apenas os templates builtin auditados e os templates comunitários de saída `claude-code`/`vscode` existentes, sem habilitá-los automaticamente. Outros IDs, hooks ou destinos exigem revisão; suas saídas permanecem arquivos locais graváveis, não links.

**Pacote atualizado com sessão antiga:** o helper usa `/proc/<pid>/exe` do Noctalia ativo para exportar/validar configurações. Usar o CLI recém-atualizado pode migrar o estado para uma versão que o daemon antigo recusa salvar. Nesta aplicação havia pacote 5.3.0 e processo 5.2.1; o único ajuste de compatibilidade foi o marcador de estado 15→14, após conferir ausência de overrides de dock da migração 15. O helper não faz downgrades automáticos. Em outra instalação, não reduza marcadores sem revisar as migrações; prefira entrar novamente na sessão quando for conveniente.

Regeneração determinística dos wallpapers (Python 3.11+ e `rsvg-convert`):

```bash
python3 -I scripts/render-arc.py
python3 -I scripts/render-arc.py --check
```

### ARC // Motion — extensão opcional

O Lua usa curvas sem rebote, `popin 97%` para janelas, slide-fade curto nos workspaces e console especial pelo topo, com saída mais rápida. Fades/foco herdam a árvore global; não há giro de borda nem pulsação. Os painéis continuam com suas animações nativas, preservando as regras `no_anim` do Noctalia. O parâmetro `speed` do Hyprland não é uma duração garantida em milissegundos.

O wallpaper Motion gira somente quatro segmentos periféricos, mantendo centro, textos e grade imóveis. `scripts/render-arc-motion.py` deriva layers das fábricas de `scripts/render-arc.py`, sem alterar os SVGs/PNGs estáticos. Os loops H.264 silenciosos têm 60 s/24 fps, horizontal 1920×1080 e vertical 768×1366; ficam em `${XDG_CACHE_HOME:-$HOME/.cache}/dots-arch/arc-motion/`, não no manifesto. O renderer valida metadados com ffprobe; a fase é contínua por construção e testada na geometria, mas `--check` não é uma análise automática do seam do vídeo codificado.

```bash
python3 -I scripts/render-arc-motion.py          # prévia sem escrita
python3 -I scripts/render-arc-motion.py --apply  # gerar localmente
python3 -I scripts/render-arc-motion.py --check

# Dependência separada, não instalada pelo bootstrap:
sudo pacman -S --needed mpvpaper
python3 -I scripts/arc-motion.py --wallpaper --apply
python3 -I scripts/arc-motion.py --status
python3 -I scripts/arc-motion.py --stop --apply
```

**Troca explícita de renderizador:** o Noctalia nativo 5.2/5.3 não reproduz vídeos continuamente. Enquanto o mpvpaper assume o fundo de todos os outputs, a barra e os painéis continuam no Noctalia. Antes de usar o seletor nativo de wallpapers, execute `--stop --apply`: selecionar uma imagem não reabilita o renderizador nativo automaticamente. O retorno restaura somente o campo `wallpaper.enabled`, preservando os caminhos de imagens posteriormente escolhidas e todo o restante do estado local. Não use os dois renderizadores como donos concorrentes do fundo.

O helper cria `arc-motion.service` **transitório**, sem `enable`, autostart ou unidade permanente. Agrupa saídas horizontais em um player e verticais em outro, usa input region vazia e desabilita áudio/controles do player. O cleanup `ExecStopPost` é armado antes de desativar o fundo nativo; morte de player ou mudança de outputs encerra o modo animado, sem restart loop. Só encerra os processos da unidade que corresponde ao token privado. O VNC também recebe animação e pode aumentar o custo de transmissão. Auto-pause não é habilitado sem validar a semântica de oclusão do grupo.

**Limite da verificação nesta aplicação:** as interações foram aplicadas, restauradas e reaplicadas na sessão real, com geometria e estado não visual preservados. Os loops foram gerados e validados. `mpvpaper` não pôde ser instalado sem autenticação administrativa: o `sudo` exigiu senha e a tentativa gráfica expirou, sem instalar pacotes. Portanto a reprodução como wallpaper, a supervisão/cleanup reais e os custos de CPU/GPU/memória/VNC **ainda não foram medidos/testados ao vivo**. Os testes isolados não substituem essa validação. Até instalar e ativar explicitamente, o fundo continua estático.

#### Recuperação de Motion separada do tema estático

Backups Motion ficam em `${XDG_STATE_HOME:-$HOME/.local/state}/dots-arch/motion/backups/<ID>/`, privados e independentes dos backups ARC v1. A recuperação recusa mudanças posteriores no arquivo/link e nos nós de animação runtime. Não altere o journal para ignorar conflitos.

```bash
# Antes de uma futura edição do módulo já linkado:
python3 -I scripts/arc-motion.py --backup
hyprctl eval 'hl.config({misc={disable_autoreload=true}})'
# Edite somente animations.lua; então aplique sem um reload geral:
python3 -I scripts/arc-motion.py --interactions --from-backup <ID> --apply
# Restaure o valor ANTERIOR da opção (false é o padrão desta sessão):
hyprctl eval 'hl.config({misc={disable_autoreload=false}})'

python3 -I scripts/arc-motion.py --restore <ID>          # verifica conflitos
python3 -I scripts/arc-motion.py --restore <ID> --apply  # restaura animações e para o fundo
```

Desabilitar temporariamente o autoreload é necessário: editar uma fonte Lua linkada pode provocar reload completo automaticamente, recalculando escala/posição de monitores. A restauração e o rollback interno do helper protegem suas próprias escritas com essa opção e devolvem seu valor original. Para edições manuais, use a proteção antes de escrever e restaure a opção mesmo se a edição falhar. Capturar `--backup` sozinho não desativa o watcher. Para ativar interações e wallpaper juntos, use `--from-backup <ID> --apply`, com dependências e vídeos já disponíveis.

O baseline de recuperação desta aplicação é `20261016T235525Z-4033304-motion`. Para voltar ao tema anterior ao ARC, **desfaça Motion primeiro**, depois use `scripts/hyper-tech.py --restore <ID-ARC> --apply`. O contrato v1 do helper estático permanece intacto.

### Referências visuais

- [Territory — Avengers: Age of Ultron](https://territorystudio.com/project/marvels-avengers-age-of-ultron/): engenharia, robótica e aviônica como base visual.
- [Cantina Creative — Spider-Man: Homecoming](https://www.cantinacreative.com/film/spiderman-homecoming): Stark-tech com personalidade de Peter Parker.
- [Territory — Spider-Man: Far From Home](https://territorystudio.com/project/spider-man-far-from-home/): evolução de F.R.I.D.A.Y./E.D.I.T.H., subordinada à clareza.
- [Noctalia — paletas](https://docs.noctalia.dev/noctalia/theming/palette/): formato customizado nativo.

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
python3 -I tests/test-hyper-tech.py
python3 -I tests/test-arc-motion.py
python3 -I tests/test-arc-motion-render.py
python3 -I scripts/render-arc.py --check
# Após gerar os vídeos opcionais:
python3 -I scripts/render-arc-motion.py --check
./script.sh --profile desktop --dry-run
```

Os testes usam repositório-fixture e `HOME`/XDG temporários: não instalam pacotes, não alteram o desktop real e não acessam o NAS. A validação de sintaxe não garante que uma versão diferente dos apps aceite todas as opções. ShellCheck pode ser usado quando instalado; ele não é requisito do bootstrap.

## TrueNAS

`infra/truenas/` foi preservada no disco, mas a pasta inteira está no `.gitignore`: não é versionada, publicada nem baixada ao clonar este repositório. Sua documentação contém domínios e topologia operacional. Mantenha essa infraestrutura em armazenamento ou repositório privado separado; não use `git add -f` para incluí-la aqui.

Quando essa pasta existir localmente, consulte `infra/truenas/README.md` e `infra/truenas/client/README.md`. Nenhuma implantação, montagem, instalação de app ou comunicação com o NAS faz parte deste bootstrap. A assinatura histórica do instalador de mounts foi mantida para reconhecer unidades existentes; `infra/truenas/nas/prepare.py` é histórico e não deve ser reaplicado como se fosse o estado atual.
