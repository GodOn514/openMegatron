## Summary / 摘要

- 

## Scope / 范围

- [ ] Frontend / 前端
- [ ] Backend / 后端
- [ ] Skills / 技能
- [ ] Docs / 文档
- [ ] Launcher / 启动器

## Verification / 验证

- [ ] `python -m py_compile pysrc/agent.py pysrc/evolution.py scripts/data_admin.py scripts/runtime_setup.py scripts/llm_setup.py`
- [ ] `pytest -q`
- [ ] `npm run lint`
- [ ] `npm run build`
- [ ] Manual `start.bat` smoke test / 手动启动冒烟测试

## Safety / 安全

- [ ] No API keys, tokens, or local `model.toml` values are included.
- [ ] Runtime/generated folders such as `venv`, `node_modules`, `.runtime`, `log`, and Docker data are not included.
- [ ] Skill or project self-evolution changes went through proposal review when applicable.

## Notes / 备注

- 
