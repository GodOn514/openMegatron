# openMegatron / 源哥 AI

> **本地 AI 智能体工作台 — 双击就能跑**
>
> **Local AI Agent Workspace — Double-click to run**

---

## ✨ 这是什么？

`openMegatron` 是一个在**你自己电脑上**运行的 AI 智能体平台。装上就能用，不需要买服务器，不需要配云环境。

把它想象成一个「AI 工具箱」：

- 🧠 **科研助手** — 查论文、找期刊、生成综述、检查引用格式
- 💻 **代码助手** — AI 帮你写代码、改代码
- 🎬 **视频制作** — 从表格生成视频

所有数据都留在你的电脑里，安全可控。

---

## 🧭 为什么叫 openMegatron？

名字是为了致敬 **Transformer** 这个技术脉络。Megatron 是 Transformers 宇宙里的反派威震天，但本项目不是为了致敬反派，而是借这个名字表达一种“非主流方法”：不是只让传统技术蒸馏出文本，而是让 AI 在任务中蒸馏出可复用的 **SKILL** 和项目能力。

The name honors the **Transformer** lineage. Megatron is a villain in the Transformers universe, but this project is not about praising the villain. It uses the name to signal a non-mainstream approach: instead of only using technology to distill text, openMegatron asks AI to distill reusable **SKILL** and project capabilities from real work.

---

## 🚀 快速开始（Windows）

### 系统要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows 10/11 64位 |
| CPU | 4核以上，推荐 8核 |
| 内存 | 8GB 以上，推荐 16GB |
| 硬盘 | 10GB 可用空间 |
| 网络 | 需要联网（调用 AI 用） |

### 安装和启动

**方法一：一键启动（推荐）**

```bat
# 双击这个文件就行！
start.bat
```

启动器会自动帮你：
1. 检查并安装 Python（如果没装）
2. 检查并安装 Docker Desktop（如果没装）
3. 自动创建 Python 虚拟环境
4. 安装所有依赖
5. 自动补齐浏览器技能需要的 Playwright Chromium
6. 启动数据库、后端服务、前端页面

仓库不会上传 `venv/`、`node_modules/`、`.runtime/`、`.docker-cli/`、日志或本地缓存。缺什么，`start.bat` 会尽量自动安装和恢复。正常双击启动会自动安装 Playwright Chromium；如果你只想跳过浏览器技能运行时，可以先设置 `MEGATRON_INSTALL_PLAYWRIGHT=0`。

The repository does not include `venv/`, `node_modules/`, `.runtime/`, `.docker-cli/`, logs, or local caches. If something is missing, `start.bat` will try to install and restore it automatically. A normal double-click launch installs Playwright Chromium automatically; set `MEGATRON_INSTALL_PLAYWRIGHT=0` first if you want to skip browser-skill runtime support.

首次启动时会让你选择 AI 模型提供商（选一个就行）：
- **DeepSeek** — 国内可用，性价比高
- **OpenAI** — 需要海外网络
- **通义千问** — 阿里云
- 以及其他国产模型

> ⚠️ **注意**：AI 模型需要 API Key，首次启动时会引导你设置。

**方法二：一步步来**

如果你只想先看看，也可以手动运行：

```bash
# 1. 安装 Python 依赖
python -m venv venv
venv\Scripts\pip install -r pysrc\requirements.txt

# 2. 启动后端
venv\Scripts\python pysrc\agent.py --api

# 3. 另开一个终端启动前端
npm ci
npm run dev
```

---

## 🖥️ 使用界面

启动后，浏览器会自动打开 `http://localhost:3000`。

界面分三块：
- **左侧** — 项目和对话列表
- **中间** — 聊天主界面，和 AI 对话
- **右侧** — 导航栏，快速跳转到之前的回答

---

## 🧪 科研技能

项目内置了完整的科研工具链：

| 技能 | 说明 |
|------|------|
| 📄 论文阅读 | 上传 PDF，AI 自动总结 |
| 🔍 顶刊搜索 | 搜索 IEEE/Springer 等顶级期刊 |
| 📊 引用图谱 | 生成论文引用关系图 |
| ✅ 引用验证 | 检查引用格式是否正确 |
| 📋 证据矩阵 | 快速生成文献对比表 |
| 📝 综述生成 | 自动写文献综述 |
| 🏆 期刊推荐 | 根据论文内容推荐投稿期刊 |

---

## 🛡️ 受控自进化

openMegatron 支持“先提案、再审核、后应用”的自进化流程。AI 或用户可以创建技能/项目改动提案，前端“进化审查”面板会展示目标文件、摘要和内容预览。应用提案前会自动创建快照，应用后可以回滚。

openMegatron supports controlled self-evolution: proposal first, review second, apply last. The agent or user can create skill/project change proposals. The Evolution Review panel shows target files, summary, and preview content. Applying a proposal creates snapshots, and applied proposals can be rolled back.

更多说明见 `docs/evolution.md`。

See `docs/evolution.md` for details.

---

## 🐳 服务依赖

项目需要三个本地服务（启动器会自动用 Docker 启动）：

| 服务 | 用途 | 默认端口 |
|------|------|---------|
| PostgreSQL + pgvector | 数据存储 + 向量搜索 | 54320 |
| Redis | 缓存和消息队列 | 6379 |
| Neo4j | 知识图谱 | 7474 / 7781 |

---

## 📁 项目结构

```
openMegatron/
├── start.bat              # 一键启动器（双击我！）
├── docker-compose.yml     # 数据库服务配置
├── config.toml            # 前端配置（语言/端口）
├── pysrc/                 # Python 后端
│   ├── runtime_engine.py  # 主入口
│   ├── agent.py           # 智能体核心
│   ├── skill.py           # 技能路由系统
│   ├── model.example.toml # AI 模型配置模板
│   ├── model.toml         # 你的 AI 模型配置（已加入 .gitignore）
│   └── skills/            # 技能目录
│       ├── research/      # 科研技能
│       ├── code/          # 代码技能
│       └── media/         # 媒体技能
├── src/                   # React 前端
├── scripts/               # 启动脚本
├── tests/                 # 测试
└── docs/                  # 文档
```

---

## ⚙️ 设置

### 切换语言

启动器会自动根据系统语言显示中文或英文。
你也可以手动指定：

```bash
# 设置为中文
set MEGATRON_LANG=zh
# 或写入文件
echo zh > megatron.lang

# 设置为英文
set MEGATRON_LANG=en
echo en > megatron.lang
```

### 修改 AI 模型

编辑 `pysrc/model.toml`（参考 `pysrc/model.example.toml` 的格式），或通过 `scripts/llm_setup.py` 重新配置：

```bash
venv\Scripts\python scripts\llm_setup.py
```

### 修改端口

编辑 `config.toml`：

```toml
[frontend]
port = 3000  # 改成你想要的端口
```

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

提交前建议运行：

Before opening a PR, run:

```bash
python -m py_compile pysrc/agent.py pysrc/evolution.py scripts/data_admin.py scripts/runtime_setup.py scripts/llm_setup.py
pytest -q
npm run lint
npm run build
```

更多 GitHub 协作说明见 `CONTRIBUTING.md` 和 `docs/release.md`。

See `CONTRIBUTING.md` and `docs/release.md` for GitHub contribution and release notes.

---

## 📄 许可

本项目采用 MIT 许可协议。

---

## 🙏 致谢

项目名称来自 Transformers 宇宙里的 **Megatron（威震天）**。
我们的理念是：让 AI 把技术经验**蒸馏成活的能力**，而不仅仅是文本。
