# CLI Layout

A multi-panel terminal UI that wraps AI CLI tools like [Claude Code](https://docs.anthropic.com/en/docs/claude-code), giving you a split-view interface with separate panels for prompts, responses, and raw output.

Built with [Textual](https://textual.textualize.io/).

## Features

- **Multi-panel layouts** — Four layout modes (columns, left-heavy, right-heavy, stacked) plus a full-screen raw output view. Switch with `Ctrl+L` or the `/layout` command.
- **Markdown-rendered responses** — AI responses are rendered with Rich Markdown (bold, headers, lists, code blocks, etc.) instead of raw text.
- **Turn-based history** — Navigate through your conversation history with `Ctrl+P` / `Ctrl+N`. Each prompt + response is a "turn."
- **Loading animation** — Animated spinner in the response panel while waiting for the AI to respond.
- **Raw output view** — Toggle `Ctrl+T` to see the unfiltered subprocess stdout for debugging.
- **Clipboard support** — Copy the current response with `Ctrl+Y`.
- **Claude CLI commands** — Run `/usage`, `/config`, `/model`, `/status`, and `/version` directly from the input panel.
- **Extensible backends** — Plug in any AI CLI tool by adding a backend config and parser.

## Requirements

- Python 3.10+
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI installed and authenticated (for the default `claude` backend)

## Installation

```bash
# Clone the repository
git clone https://github.com/andylu-98/cli-layout.git
cd cli-layout

# Install in development mode
pip install -e .
```

This installs the `cli-layout` command and the two dependencies (`textual` and `pyyaml`).

## Quick Start

```bash
# Run with default settings (columns layout, claude backend)
cli-layout

# Choose a layout
cli-layout --layout left-heavy

# Use a custom config file
cli-layout --config /path/to/config.yaml

# Override the backend
cli-layout --backend claude
```

## Keybindings

| Key              | Action                                    |
| ---------------- | ----------------------------------------- |
| `Enter`          | Send prompt                               |
| `Shift+Enter`    | Insert newline in input                   |
| `Ctrl+L`         | Cycle through layouts                     |
| `Ctrl+T`         | Toggle between split view and raw output  |
| `Ctrl+P`         | Previous turn in history                  |
| `Ctrl+N`         | Next turn in history                      |
| `Ctrl+Y`         | Copy current response to clipboard        |
| `Ctrl+K`         | Clear panel content                       |
| `Ctrl+Q`         | Quit                                      |

## Slash Commands

Type these in the input panel:

| Command              | Description                          |
| -------------------- | ------------------------------------ |
| `/usage`             | Show Claude API usage                |
| `/config`            | List Claude configuration            |
| `/model`             | Show current model                   |
| `/status`            | Show Claude status                   |
| `/version`           | Show Claude CLI version              |
| `/layout <name>`     | Switch layout (columns, left-heavy, right-heavy, stacked) |

## Layouts

- **columns** — Three equal vertical columns: Prompt | Response | Input
- **left-heavy** — Left side (2/3): Prompt + Input stacked. Right side (1/3): Response
- **right-heavy** — Left side (1/3): Prompt. Right side (2/3): Response + Input stacked
- **stacked** — Everything stacked vertically: Prompt | Response | Input

## Configuration

The app looks for `config.yaml` in this order:

1. Path passed via `--config` flag
2. `CLI_LAYOUT_CONFIG` environment variable
3. `./config.yaml` (current directory)
4. `~/.config/cli-layout/config.yaml`

### Default config

```yaml
backend: claude

backends:
  claude:
    command: claude
    args:
      - --print
      - --output-format
      - stream-json
      - --verbose
      - --include-partial-messages
      - --input-format
      - stream-json
    output_format: stream-json
    input_format: stream-json
    resume_args:
      - --continue
    parser: claude
```

### Adding a custom backend

Add a new entry under `backends` and set `backend` to its name:

```yaml
backend: my-tool

backends:
  my-tool:
    command: my-ai-cli
    args:
      - --non-interactive
    output_format: text
    input_format: stdin
    resume_args: []
    parser: plain_text
```

Available parsers: `claude` (stream-json format), `plain_text` (line-by-line text).

## Project Structure

```
src/cli_layout/
├── app.py                 # Main Textual app, layouts, keybindings
├── config.py              # Config loading (YAML)
├── widgets.py             # ScrollPanel, InputPanel, SubmitTextArea
├── events.py              # Normalized event types
├── subprocess_manager.py  # Backend process I/O
└── backends/
    ├── base.py            # Abstract parser base class
    ├── registry.py        # Parser name → class mapping
    ├── claude_parser.py   # Claude stream-json parser
    └── plain_text_parser.py  # Fallback text parser
```

## License

MIT
