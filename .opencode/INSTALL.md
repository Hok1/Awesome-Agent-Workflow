# Installing Awesome-Agent-Workflow for OpenCode

## Prerequisites

- [OpenCode.ai](https://opencode.ai) installed
- Python 3.8+ with `pip`
- This repo cloned locally

## Quick install

From the repo root, run:

```bash
./install.sh --target=opencode --user
```

Or interactively (the script will prompt for scope and method):

```bash
./install.sh --target=opencode
```

## What the installer does

1. Installs the 13 skills to `~/.config/opencode/skills/` (or `./.opencode/skills/` for project scope)
2. Installs the `fastmcp` Python dependency
3. Registers the `question-tracker` MCP server in `~/.config/opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "question-tracker": {
      "type": "local",
      "command": ["python3", "/abs/path/to/skills/sr-design/mcp_server.py"],
      "enabled": true
    }
  }
}
```

## Verify

Restart OpenCode, then ask it:

> 进入工作流

The `aaw-workflow` skill should trigger and start the SDD workflow.

## Manual install (if the script fails)

1. Symlink skills into OpenCode's discovery path:

   ```bash
   mkdir -p ~/.config/opencode/skills
   for d in skills/*/; do
     ln -s "$(pwd)/$d" "$HOME/.config/opencode/skills/$(basename "$d")"
   done
   ```

   > Note: OpenCode also auto-discovers skills from `~/.claude/skills/` and `.claude/skills/`, so if you already installed for Claude Code at user level, the skills are already visible to OpenCode — only the MCP step below is needed.

2. Install fastmcp:

   ```bash
   pip install fastmcp
   ```

3. Add the MCP server to `~/.config/opencode/opencode.json`:

   ```json
   {
     "$schema": "https://opencode.ai/config.json",
     "mcp": {
       "question-tracker": {
         "type": "local",
         "command": ["python3", "/abs/path/to/skills/sr-design/mcp_server.py"],
         "enabled": true
       }
     }
   }
   ```

## Uninstall

```bash
./install.sh --target=opencode --uninstall
```

## Other harnesses

If you also use Claude Code or Codex, install separately for each:

- Claude Code: `./install.sh --target=claude --user` (or via plugin marketplace)
- Codex: install via Codex `/plugins` marketplace, then `./install.sh --target=codex --user` to register the MCP server
