# Contribuir

Cómo instalar, correr y probar el proyecto está en el [README](README.md) y en
[`CLAUDE.md`](CLAUDE.md), que también fija las convenciones: código y commits en inglés,
Conventional Commits, una rama y un PR por cambio, y `make lint` + `make test` (en Windows,
`.\make.ps1 lint` y `.\make.ps1 test`) antes de abrir el PR. Si tocaste `frontend/`, corre
además `npm run lint` y `npx tsc --noEmit` allí.

## Desarrollo con Claude Code

El repositorio declara sus plugins en [`.claude/settings.json`](.claude/settings.json)
(`enabledPlugins`). Todos vienen del marketplace oficial, `claude-plugins-official`, que
Claude Code ya conoce, así que no hace falta registrarlo. Si al abrir el proyecto Claude Code
no te ofrece instalarlos, hazlo a mano desde una sesión:

```text
/plugin install frontend-design@claude-plugins-official
/plugin install playwright@claude-plugins-official
/plugin install typescript-lsp@claude-plugins-official
/plugin install pyright-lsp@claude-plugins-official
/plugin install pr-review-toolkit@claude-plugins-official
/plugin install commit-commands@claude-plugins-official
/plugin install claude-md-management@claude-plugins-official
/plugin install security-guidance@claude-plugins-official
/plugin install context7@claude-plugins-official
```

Los dos plugins de LSP necesitan sus servidores en el `PATH` (`pyright-langserver` y
`typescript-language-server`):

```bash
npm install -g pyright typescript-language-server typescript
```

El servidor MCP de Chrome DevTools sirve para revisar el sitio en un navegador real (consola,
red, rendimiento). No va en el repositorio sino en tu configuración de usuario:

```bash
claude mcp add chrome-devtools --scope user npx chrome-devtools-mcp@latest
```

La skill `frontend-design` llega con su plugin; ya no hay una copia en `.claude/skills/`.
