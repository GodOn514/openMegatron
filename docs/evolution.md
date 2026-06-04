# Controlled Evolution / 受控自进化

openMegatron treats AI-generated improvements as proposals first.

openMegatron 会先把 AI 生成的改进记录为提案，而不是直接覆盖项目文件。

## Why / 为什么

The project goal is to let models distill reusable **SKILL** and project capabilities from real work. That is powerful, but it needs review, snapshots, and rollback.

项目目标是让模型从真实任务中蒸馏出可复用的 **SKILL** 和项目能力。这件事很有价值，但必须配套审核、快照和回滚。

## Flow / 流程

1. The agent or user creates an evolution proposal.
2. The proposal records title, summary, changed files, full replacement content, and review notes.
3. A user reviews it in the frontend Evolution Review panel or through the API.
4. Applying a proposal creates snapshots for every touched file.
5. Applied proposals can be rolled back from the same ledger.

1. 智能体或用户先创建进化提案。
2. 提案记录标题、摘要、目标文件、完整替换内容和审查备注。
3. 用户在前端“进化审查”面板或 API 中审核。
4. 应用提案前会自动为每个目标文件创建快照。
5. 已应用提案可以基于同一 ledger 回滚。

## API / 接口

```text
GET  /evolution/policy
GET  /evolution/proposals
POST /evolution/proposals
POST /evolution/apply
POST /evolution/reject
POST /evolution/rollback
```

Example proposal:

示例提案：

```json
{
  "title": "Add a research helper skill",
  "summary": "Create a reviewable skill draft for citation checking.",
  "kind": "skill",
  "files": [
    {
      "path": "pysrc/skills/research/citation-checker-1.0.0/SKILL.md",
      "action": "write",
      "content": "# Citation Checker\n\n..."
    }
  ]
}
```

## Storage / 存储

Runtime state is stored under:

运行状态存放在：

```text
.runtime/evolution/
```

This folder is ignored by Git. It contains the proposal ledger and file snapshots.

这个目录已被 Git 忽略，用于保存提案 ledger 和文件快照。

## Guardrails / 保护规则

The store blocks paths that commonly contain local state, secrets, or generated dependencies, including:

系统会阻止常见的本地状态、密钥和生成依赖路径，包括：

```text
.git
.runtime
node_modules
venv
dist
log
logs
pysrc/model.toml
model.toml
.env
```

All target paths must stay inside the repository.

所有目标路径都必须留在仓库目录内部。
