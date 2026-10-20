# ARC // VFX

Wallpaper animado produzido com VectorCraft (arte), EffectCraft (animação e Glow) e FilmCraft (montagem/exportação). Os originais em `../arc/` permanecem intactos. Clonar o repositório não ativa o wallpaper nem altera autostart, atalhos ou monitores.

## Vídeos prontos para usar

Os dois MP4s finais são versionados no Git normal: não exigem Git LFS, os aplicativos de autoria nem uma nova renderização. No GitHub, abra o arquivo e use **Download raw file**, ou clone o repositório/branch da PR.

| Download | Dimensões | Duração |
| --- | --- | --- |
| [Horizontal — arc-vfx-landscape.mp4](renders/arc-vfx-landscape.mp4) | 1920 × 1080 | 60 s / 1440 quadros |
| [Vertical — arc-vfx-portrait.mp4](renders/arc-vfx-portrait.mp4) | 768 × 1366 | 60 s / 1440 quadros |

Ambos são H.264, yuv420p, 24 fps e sem áudio. O movimento tem período de 12 segundos; cada vídeo contém cinco períodos, sem fade para preto ou transição entre ciclos. A versão vertical tem composição própria, sem recortar a horizontal.

### Direção visual

- Anéis ciano e azul em contrarrotação.
- Núcleo luminoso pulsante, com Glow localizado.
- Varredura de radar restrita ao reator.
- Partículas orbitais discretas e uma onda de energia expansiva.
- Grade, tipografia e área principal de trabalho imóveis.

## Usar em outro PC com este setup Hyprland/Noctalia

Pré-requisitos: este setup já configurado, sessão gráfica Hyprland/Noctalia ativa, `mpvpaper`, `ffprobe` (FFmpeg) e systemd de usuário disponíveis. No Arch/CachyOS, `mpvpaper` é uma dependência opcional separada: `sudo pacman -S --needed mpvpaper`.

Na raiz do clone, execute o bloco abaixo. Ele para o controlador existente, guarda os vídeos anteriores em um diretório de backup e instala os dois MP4s no cache esperado. Não execute junto com outro processo gerando ou trocando esses arquivos.

```bash
bash <<'SH'
set -eu
python3 -I scripts/arc-motion.py --stop --apply
cache="${XDG_CACHE_HOME:-$HOME/.cache}/dots-arch/arc-motion"
mkdir -p "$cache"
backup=$(mktemp -d "$cache/backup-before-vfx.XXXXXX")
for name in arc-motion-landscape.mp4 arc-motion-portrait.mp4; do
    if [ -f "$cache/$name" ]; then
        cp -p "$cache/$name" "$backup/$name"
    fi
done
printf 'Backup dos vídeos anteriores: %s\n' "$backup"
install -m 600 assets/arc-vfx/renders/arc-vfx-landscape.mp4 "$cache/arc-motion-landscape.mp4"
install -m 600 assets/arc-vfx/renders/arc-vfx-portrait.mp4 "$cache/arc-motion-portrait.mp4"
python3 -I scripts/arc-motion.py --wallpaper --apply
python3 -I scripts/arc-motion.py --status
SH
```

O controlador escolhe horizontal/vertical pela orientação das saídas e preserva o handoff com Noctalia. A ativação acima vale para a sessão atual; este guia não cria ou habilita autostart. Um autostart já configurado que usa `--wallpaper --apply` reutilizará o cache instalado.

**Não execute `scripts/render-arc-motion.py --apply` depois da cópia:** ele regenera o wallpaper Motion anterior e sobrescreve o cache VFX.

Para voltar ao fundo estático e ao seletor nativo do Noctalia:

```bash
python3 -I scripts/arc-motion.py --stop --apply
```

Para voltar ao vídeo anterior, pare o controlador, copie os MP4s do diretório de backup de volta para o cache e execute `--wallpaper --apply` novamente. Não inicie players paralelos por fora do controlador. Em outros ambientes, os MP4s podem ser usados com um aplicativo de wallpaper animado compatível; o controlador deste repositório é específico deste setup.

## Verificação e limites

Os arquivos finais foram verificados com `ffprobe` e decodificação completa com FFmpeg. Os diagnósticos das emendas a cada 12 s e final → início apoiam a continuidade de fase, mas não são garantia perceptual. O custo de reprodução varia por hardware, quantidade de saídas e transmissão VNC.

```bash
ffprobe -v error -show_streams -show_format assets/arc-vfx/renders/arc-vfx-landscape.mp4
ffmpeg -v error -xerror -i assets/arc-vfx/renders/arc-vfx-landscape.mp4 -f null -
```

## Arquivos de autoria locais

As fontes `.vectorcraft`, `.svg`, `.ecproj` e `.fcproj` usadas na produção são mantidas localmente e não fazem parte desta distribuição dos MP4s. Os projetos de edição podem depender de caminhos absolutos e mídia intermediária; não são necessários para reproduzir os vídeos finais em outro PC.

Os demais arquivos em `renders/` (bases PNG, ciclos de 12 s, prévias e relatórios), assim como `FilmCraft Previews/`, ficam ignorados pelo Git. Apenas os dois MP4s finais são distribuídos. Os ciclos de 12 s não atendem ao contrato de 60 s do controlador.
