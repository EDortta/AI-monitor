# AI Agent Activity Monitor

> [English](#english) · [Português BR](#português-br) · [Español](#español)

---

## English

A lightweight system-tray application that shows which AI coding agents (Claude Code, Codex, Cursor) are active across your projects, and keeps a browsable history of past sessions.

### How it works

Two files in `~/Sync/` drive everything:

| File | Purpose |
|------|---------|
| `~/Sync/agent-status.json` | Live sessions — each agent writes/removes its own entry |
| `~/Sync/agent-log.md` | Append-only session history |

The tray icon reflects the current state:
- **Colored dot(s)** — one or more agents are running (orange = Claude Code, green = Codex, blue = Cursor)
- **Gray dot** — no active session

Single-click opens a popup with live sessions. Double-click opens the full history window.

### Requirements

- Python 3.9+
- Linux (MATE/GNOME/X11), macOS, or Windows

### Installation

**Linux / macOS**

```bash
./install.sh
```

The script creates a `.venv`, installs dependencies, and registers an autostart entry (`.desktop` on Linux, `LaunchAgent` on macOS).

**Windows**

```bat
install.bat
```

**Manual**

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python monitor.py
```

### Patching project AGENTS.md files

`patch-agents.py` appends a standard *Activity Monitor* section to every `AGENTS.md` found under `~/Sync/Projects/` and `~/Sync/Y2/`, so each agent knows the protocol automatically.

```bash
python patch-agents.py           # apply
python patch-agents.py --dry-run # preview only
```

### Debug log

`~/.local/share/agent-monitor/debug.log`

---

## Português BR

Aplicativo leve de bandeja do sistema que exibe quais agentes de IA (Claude Code, Codex, Cursor) estão ativos nos seus projetos, com histórico navegável de sessões anteriores.

### Como funciona

Dois arquivos em `~/Sync/` controlam tudo:

| Arquivo | Finalidade |
|---------|-----------|
| `~/Sync/agent-status.json` | Sessões ativas — cada agente escreve e remove sua própria entrada |
| `~/Sync/agent-log.md` | Histórico de sessões (somente acréscimo) |

O ícone na bandeja reflete o estado atual:
- **Ponto colorido** — um ou mais agentes rodando (laranja = Claude Code, verde = Codex, azul = Cursor)
- **Ponto cinza** — nenhuma sessão ativa

Clique simples abre um popup com as sessões ao vivo. Clique duplo abre a janela de histórico completo.

### Requisitos

- Python 3.9+
- Linux (MATE/GNOME/X11), macOS ou Windows

### Instalação

**Linux / macOS**

```bash
./install.sh
```

O script cria o `.venv`, instala as dependências e registra a entrada de inicialização automática (`.desktop` no Linux, `LaunchAgent` no macOS).

**Windows**

```bat
install.bat
```

**Manual**

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python monitor.py
```

### Patchear os arquivos AGENTS.md dos projetos

`patch-agents.py` adiciona uma seção padrão *Activity Monitor* a cada `AGENTS.md` encontrado em `~/Sync/Projects/` e `~/Sync/Y2/`, para que cada agente conheça o protocolo automaticamente.

```bash
python patch-agents.py           # aplicar
python patch-agents.py --dry-run # apenas visualizar
```

### Log de depuração

`~/.local/share/agent-monitor/debug.log`

---

## Español

Aplicación liviana de bandeja del sistema que muestra qué agentes de IA (Claude Code, Codex, Cursor) están activos en tus proyectos, con un historial navegable de sesiones anteriores.

### Cómo funciona

Dos archivos en `~/Sync/` controlan todo:

| Archivo | Propósito |
|---------|----------|
| `~/Sync/agent-status.json` | Sesiones activas — cada agente escribe y elimina su propia entrada |
| `~/Sync/agent-log.md` | Historial de sesiones (solo se añade, nunca se edita) |

El ícono en la bandeja refleja el estado actual:
- **Punto de color** — uno o más agentes en ejecución (naranja = Claude Code, verde = Codex, azul = Cursor)
- **Punto gris** — ninguna sesión activa

Un clic abre un popup con las sesiones en vivo. Doble clic abre la ventana de historial completo.

### Requisitos

- Python 3.9+
- Linux (MATE/GNOME/X11), macOS o Windows

### Instalación

**Linux / macOS**

```bash
./install.sh
```

El script crea el `.venv`, instala las dependencias y registra la entrada de inicio automático (`.desktop` en Linux, `LaunchAgent` en macOS).

**Windows**

```bat
install.bat
```

**Manual**

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python monitor.py
```

### Parchear los archivos AGENTS.md de los proyectos

`patch-agents.py` añade una sección estándar *Activity Monitor* a cada `AGENTS.md` encontrado en `~/Sync/Projects/` y `~/Sync/Y2/`, para que cada agente conozca el protocolo automáticamente.

```bash
python patch-agents.py           # aplicar
python patch-agents.py --dry-run # solo vista previa
```

### Log de depuración

`~/.local/share/agent-monitor/debug.log`
