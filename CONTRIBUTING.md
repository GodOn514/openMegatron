# Contributing / 贡献指南

Thank you for helping improve openMegatron.

感谢你帮助改进 openMegatron。

## Development Rules / 开发规则

- Keep secrets out of Git: do not commit `pysrc/model.toml`, `.env`, API keys, cookies, logs, or runtime caches.
- 不要把密钥提交到 Git：包括 `pysrc/model.toml`、`.env`、API Key、cookie、日志和运行缓存。
- Prefer small, reviewable changes. Keep skill changes, frontend changes, launcher changes, and docs changes separated when possible.
- 优先提交小而清楚的改动。技能、前端、启动器和文档改动尽量分开。
- Use the controlled evolution flow for AI-generated skill/project changes that should be reviewed before landing.
- AI 生成的技能或项目改动建议走“受控自进化”流程，先提案、再审核、后应用。

## Local Verification / 本地验证

```bash
python -m py_compile pysrc/agent.py pysrc/evolution.py scripts/data_admin.py scripts/runtime_setup.py scripts/llm_setup.py
pytest -q
npm run lint
npm run build
```

For a full manual smoke test on Windows, run:

Windows 完整冒烟测试：

```bat
start.bat
```

## Pull Requests / Pull Request

Before opening a PR:

提交 PR 前请确认：

- The app starts without requiring committed local state.
- 应用不依赖已提交的本地运行状态。
- Frontend text follows the selected language and avoids unnecessary Chinese/English mixing.
- 前端文案跟随当前语言，避免不必要的中英混杂。
- New skills include a clear `SKILL.md`, inputs, outputs, and verification notes.
- 新技能应包含清楚的 `SKILL.md`、输入、输出和验证说明。
- Self-evolution proposals include a rollback path or snapshot.
- 自进化提案应包含回滚路径或快照。
