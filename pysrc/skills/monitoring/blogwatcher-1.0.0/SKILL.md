---
name: blogwatcher
description: Monitor blogs, RSS/Atom feeds, and configured research venue pages using the blogwatcher CLI; use research_sources or seed_research for top-venue research monitoring.
homepage: https://github.com/Hyaxia/blogwatcher
metadata: {"clawdbot":{"requires":{"bins":["blogwatcher"]},"install":[{"id":"go","kind":"go","module":"github.com/Hyaxia/blogwatcher/cmd/blogwatcher@latest","bins":["blogwatcher"],"label":"Install blogwatcher (go)"}]}}
---

# blogwatcher

Track blog, RSS/Atom, and research venue page updates with the `blogwatcher` CLI.

Install
- Go: `go install github.com/Hyaxia/blogwatcher/cmd/blogwatcher@latest`

Common commands
- Add a blog: `blogwatcher add "My Blog" https://example.com`
- List blogs: `blogwatcher blogs`
- Scan for updates: `blogwatcher scan`
- List articles: `blogwatcher articles`
- Mark an article read: `blogwatcher read 1`
- Mark all articles read: `blogwatcher read-all`
- Remove a blog: `blogwatcher remove "My Blog"`

Research monitoring
- List configured research sources without requiring the CLI: run this skill with `{"action":"research_sources","top_venue_only":true}`.
- Seed configured top-venue research sources into blogwatcher: run with `{"action":"seed_research","top_venue_only":true}`.
- Research monitoring sources live in `pysrc/skills/research/config/watch_sources.toml`; preprint feeds are marked `top_venue = false`.

Notes
- Use `blogwatcher <command> --help` to discover flags and options.
