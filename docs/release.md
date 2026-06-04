# Release Notes / 发布说明

This project is intended to be easy to try from GitHub: clone, configure a model provider, and run `start.bat`.

本项目的 GitHub 交付目标是：clone 后配置模型厂商，然后运行 `start.bat` 即可体验。

## Release Checklist / 发布检查清单

- [ ] `start.bat` starts cleanly on a fresh Windows machine.
- [ ] 启动器能在新的 Windows 环境中正常启动。
- [ ] Port conflicts are handled or reported clearly.
- [ ] 端口冲突能自动处理或清楚提示。
- [ ] Model provider setup supports Chinese and English.
- [ ] 模型厂商配置支持中文和英文。
- [ ] No `venv`, `node_modules`, `.runtime`, logs, caches, API keys, or local TOML files are committed.
- [ ] 不提交 `venv`、`node_modules`、`.runtime`、日志、缓存、API Key 或本地 TOML。
- [ ] CI passes on GitHub Actions.
- [ ] GitHub Actions CI 通过。
- [ ] README quickstart has been tested manually.
- [ ] README 快速开始已经手动验证。

## Current Verification Commands / 当前验证命令

```bash
python -m py_compile pysrc/agent.py pysrc/evolution.py scripts/data_admin.py scripts/runtime_setup.py scripts/llm_setup.py
pytest -q
npm run lint
npm run build
```

## Versioning / 版本

Use small version steps while the project is still moving quickly:

项目还在快速迭代期，建议小步发版：

- Patch: bug fixes, docs, launcher repair.
- 补丁版：Bug 修复、文档、启动器修复。
- Minor: new skills, new UI panels, new workflow APIs.
- 小版本：新技能、新 UI 面板、新工作流 API。
- Major: incompatible data format or launcher behavior.
- 大版本：不兼容的数据格式或启动器行为。
