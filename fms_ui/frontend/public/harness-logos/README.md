# Harness logos

Static logos for the harness ids in `core/fms_lib/registry.py` (`READY`). Each
file is a square RGBA PNG on a transparent canvas: `<id>.png` is 128x128 and
`<id>-64.png` is 64x64, both resized with Lanczos from the largest available
source representation (macOS icons are opaque inside their squircle and
transparent outside it).

Vite copies this directory verbatim into `fms_ui/static/harness-logos/`, and
`fms_ui/server.py` serves it at:

- `/harness-logos/<id>.png`
- `/harness-logos/<id>-64.png`

No frontend source references these files yet; they are assets only.

## Sources

| Harness id | Display name | Source | Processing | Notes |
| --- | --- | --- | --- | --- |
| `qoder-cn` | Qoder CN | `/Applications/Qoder CN.app/Contents/Resources/icon.icns` | `iconutil` iconset, `icon_512x512@2x.png` (1024) -> resize | Official CN app icon, includes its CN badge |
| `qoder` | Qoder (international) | `/Applications/Qoder.app/Contents/Resources/icon.icns` | `icon_512x512@2x.png` (1024) -> resize | Official app icon |
| `kimi-code` | Kimi Code | `/Applications/Kimi Code.app/Contents/Resources/icon.icns` | `icon_512x512@2x.png` (1024) -> resize | Official app icon |
| `zcode` | ZCode | `/Applications/ZCode.app/Contents/Resources/icon.icns` | `icon_512x512@2x.png` (1024) -> resize | Official app icon |
| `codearts-agent` | CodeArts Agent | none | Generated placeholder | `com.huawei.codearts.agent` is not installed on this machine (the adapter was verified earlier when it was present); gray "CA" tile, not an official logo |
| `codex` | ChatGPT Codex | `/Applications/ChatGPT.app/Contents/Resources/icon-codex-dark-color.png` | 1024 RGBA source -> resize | Official Codex icon shipped inside ChatGPT.app |
| `deepseek` | DeepSeek Harness | `/Applications/DeepSeek Harness.app/Contents/Resources/icon.icns` | `icon_512x512@2x.png` (1024) -> resize | Official app icon (`com.deepseek.dsh`) |
| `claude-code` | Claude Code | `/Applications/Cursor.app/Contents/Resources/app/out/vs/glass/browser/media/claude-code-import-claude-mark.png` | 512 RGBA source -> resize | No Claude/Claude Code app bundle is installed; this is the official Claude mark bundled in Cursor, not a standalone app icon |
| `cline` | Cline | `/Applications/Cline.app/Contents/Resources/icon.icns` | `icon_512x512@2x.png` (1024) -> resize | Official app icon |
| `grok-build` | Grok Build | `/Applications/Grok Bot.app/Contents/Resources/icon.icns` | `icon_128x128@2x.png` (256) -> resize | The CLI at `~/.grok/bin/grok` has no app bundle; the only local Grok-branded app is Grok Bot (SpaceXAI, bundled as `com.anysphere.sand`). Treat as an approximate brand mark |
| `workbuddy` | WorkBuddy AI | `/Applications/WorkBuddy AI.app/Contents/Resources/icon.icns` | `icon_512x512@2x.png` (1024) -> resize | Official app icon |
| `workbuddy-cn` | WorkBuddy (domestic) | `/Applications/WorkBuddy.app/Contents/Resources/icon.icns` | `icon_512x512@2x.png` (1024) -> resize | Official app icon; visually identical to `workbuddy` in these apps |
| `antigravity` | Antigravity | `/Applications/Antigravity.app/Contents/Resources/icon.icns` | `icon_256x256@2x.png` (512) -> resize | Official app icon |
| `antigravity-cli` | Antigravity CLI | `/Applications/Antigravity.app/Contents/Resources/icon.icns` | `icon_256x256@2x.png` (512) -> resize | Same brand; no separate CLI app icon exists locally, so the desktop icon is reused |
| `minimax-code` | MiniMax Code | `/Applications/MiniMax Code.app/Contents/Resources/icon.icns` | `icon_512x512@2x.png` (1024) -> resize | Official app icon |
| `cursor` | Cursor | `/Applications/Cursor.app/Contents/Resources/Cursor.icns` | `icon_256x256@2x.png` (512) -> resize | Official app icon |
| `opencode` | OpenCode | `/Applications/OpenCode.app/Contents/Resources/icon.icns` | `icon_512x512@2x.png` (1024) -> resize | Official app icon |
| `gemini-cli` | Gemini CLI | `/Applications/Gemini.app/Contents/Resources/AppIcon.icns` | `icon_128x128@2x.png` (256) -> resize | Gemini CLI has no app bundle; the Gemini app icon (same brand) is used |
| `qwen` | Qwen Code | `/Applications/Qianwen.app/Contents/Resources/app.icns` | `icon_512x512@2x.png` (1024) -> resize | Qwen Code has no app bundle; the Qwen/Tongyi desktop app icon (same brand) is used |
| `pi` | Pi | `https://pi.dev/favicon.svg` | `sips` SVG rasterization (560) -> resize | Official Pi favicon mark (the pixelated π); transparent outside the mark, the mark itself is opaque |
| `omp` | Oh My Pi | `https://omp.sh/favicon.png` | 256 RGBA source -> resize | Official OMP favicon; transparent background |

## Missing and approximate entries

- `codearts-agent`: no local application bundle was found, so a neutral "CA"
  placeholder is used. It is deliberately not an imitation of the Huawei logo.
- `grok-build`: sourced from Grok Bot rather than a Grok Build app icon; verify
  against the official brand before treating it as authoritative.
- `claude-code`: official Claude mark extracted from Cursor's bundled import
  assets, because no Claude app is installed.
- `antigravity-cli`: intentionally shares the Antigravity icon.
- `pi`: no local Pi app bundle or icon exists (Pi ships only the npm CLI); the
  favicon from the official site is used.
- `omp`: no local app bundle exists (omp ships a single CLI binary); the
  favicon from the official site is used.

## Trademarks

These logos belong to their respective vendors. They are included only to
identify the source harness inside this local, read-only UI. Their presence does
not imply endorsement, partnership, or official affiliation.
