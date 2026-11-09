# 开发接手与初始化记录

记录日期：2026-11-09。本轮完成开发配置、基线核对与版本讨论准备。用户确认“先形成可持续开发的项目配置和路线，然后对未来版本的草案进行分析，提出建议与想法，积极与我讨论”。

## 基线事实

- 产品目录 `/home/user1/pnginfo`；参考工作区 `/home/user1/projects/09-pngInfo`，为独立 Git 仓库。
- 产品分支 `main`，v1 提交 `ab6d87c824a9762edfe30e986509389d6c309ea3`；通过 HTTPS `git ls-remote` 核实远端 `main` 同提交。
- origin 为 `git@github.com:WangZhenYu-T/Lite-PngInfo.git`。本次 SSH 只读探测被远端连接关闭，HTTPS 可读；写入权限未验证，发布前应按用户指令再核实。
- 初始唯一未跟踪文件为产品 `opencode.json`；已有配置被增量更新。
- `normalize_metadata` 读取 Pillow 信息，仅解码 Comment/Description，再抽取 NAI 参数。四图原始字段均能读到，A1111、Forge 与 ComfyUI 分类字段为空。
- 收藏保存原图 BLOB、完整解析 JSON、提示词摘要和图片 SHA-256；读取历史收藏直接返回存档 JSON。
- 前端 `openFavorite` 覆盖当前读取状态；JSON 模式展示规范化响应，尚无逐字段原文入口。

## 样图索引

所有文件位于参考工作区 `pnginfo/`。本次用当前 Pillow 和 v1 parser 重新本地读取，未输出完整提示词。哈希用于识别参考文件，不是模型哈希。

| 样图 | 尺寸 | 已核实内容 | 后续用途 |
|---|---|---|---|
| `NAI_autosave_00305_.png` | 832×1216 | Software=NovelAI，Source=NovelAI Diffusion V4.5；Comment JSON、Description 等文本；v1 正向 1982 字、负向 643 字 | NAI 兼容与来源识别；不能据此证明 ComfyUI-NAI 来源 |
| `comfyui.png` | 1200×600 | prompt 10654 字，workflow 33984 字；3 个 KSampler、2 个 SaveImageSimple、7 个 LoRA loader；inputs 未见 hash 键 | 多输出、放大链、字符串连接、模型/LoRA 分支 |
| `webui A111.png` | 720×1280 | parameters 1243 字；Version=v1.9.3；有 Model hash 与 Lora hashes | A1111 文本 parser、模型字段 |
| `webui Forge.png` | 1200×1200 | parameters 4169 字；Version=f2.0.1v1.10.1-previous-659-gc055f2d4；有 Model hash 与 Lora hashes | Forge 提示证据、长负向文本 |
| `v3版本更新范例.png` | 2249×1408 | UI 参考，仅见色彩/分辨率附属信息 | 左大图、右信息的独立详情布局 |

| 样图 | SHA-256 |
|---|---|
| NAI | `c37b1454152a62b722ceabbcc41b1fbdf70c78bf87fcd83e371dbe29539bb9b6` |
| ComfyUI | `2a06d93305aaaaef106bab9ee2b3e9bad22b31569e3e8706b73d7c7a80641ea3` |
| A1111 | `63dcaab2038e8b047fb39da092fedc9b4f3997efd76ea269a9c53392e0b1ac3e` |
| Forge | `11b0f5ebc99c6973cb54b9cbe97c45265edaaac3c28be7c436bbe2e9553292fb` |
| UI 参考 | `012bc607b577e44979089c57c63cfd49cf06d7d722920685d4dc4fe73642b070` |

ComfyUI 的 3 个 sampler 为节点 19、124、125，CFG 分别为 5、7、7，denoise 分别为 1、0.15、1；它们不能合成一套确定参数。逆向报告进一步记录了保存输出与放大链的连接关系，开发时需重新从 prompt 图确认。

NAI 本图的 v4 正/负结构中角色列表为空，因此角色 UI 需合成多角色用例或另补样图。用户后续说明此图通过 NAI API 生成，分类名称确定为 NAI，无需再区分 API 调用宿主。ComfyUI 复杂样图改用于验证保守回退，不要求分类模式提取各分支参数或 LoRA。

## 开发环境与验证

- WSL Ubuntu；Python 3.12.3、Pillow 12.3.0、SQLite 3.45.1、Node 22.23.2。
- OpenCode 1.18.30；保留本机支持的 `skills.paths`、`permission.skill` 与 `mcp.<name>.enabled`。在线 schema 已含新版结构，最终以本机解析和合并配置验证为准。
- 初始化基线执行 `python3 -m unittest discover -s tests -v`：3 项通过。测试使用临时数据库和随机端口。
- 两处项目的 `opencode debug config` 均成功解析；断言确认 bootstrap 放行、逆向技能拒绝、Runpod 关闭，参考工作区已加载产品约定且指令文件路径存在。provider 列表保持一致。`node --check static/app.js` 与两个仓库的 `git diff --check` 通过。
- 既有 CI 配置为 Ubuntu/Windows × Python 3.10/3.13；本轮未实际运行这些远程环境。
- 选用技能仅 `agent-bootstrap`。扫描了全局 skills/prompts 与 CLI 可发现项；Playwright MCP 已能承担 UI 验证，无需启用要求额外 CLI 的 Playwright skill。逆向工作已有报告，本项目关闭继承的 `craft-anything-anywhere` 权限。项目级关闭继承的 Runpod MCP，通用 MCP 与 provider 沿用。
- `opencode debug skill` 在当前安装中输出中途截断为 65536 字节，不能作为“所有技能都已完整列出”的依据；bootstrap 文件存在，本会话技能工具已成功加载，路径与合并权限也分别核实。
- Codebase Memory 的 `pnginfo` 索引记录时间为 2026-11-06，`static/`、`data/` 被排除。当前基线结论采用磁盘源文件；后续应继续检查索引覆盖与新鲜度。

## 资料关系与维护

本地原始需求和逆向报告保留在参考工作区，产品仓库只记录可共享的摘要与建议。路线见 [ROADMAP.md](ROADMAP.md)。版本讨论达成决定后更新路线的状态和理由；实际发版后再更新 CHANGELOG。

配置分别放在参考工作区与产品根目录，两者是独立 OpenCode 项目。参考工作区通过绝对路径加载产品 `AGENTS.md`，产品会话自动读取根目录约定。移动目录后需更新本机路径。重新打开 OpenCode 后，新项目配置与技能权限生效。

2026-11-09 讨论更新：用户确认第一类名称为 NAI；ComfyUI 分类仅显示容易提取且可靠绑定本图的少量信息，完整工作流交由 JSON/ComfyUI；接受 JSON 格式化与复制原文，以及未找到/缺少哈希/网络失败的查询状态区分；要求覆盖无元信息图片。完整范围与验收已整理进版本方案，功能尚未开始实现。

同日补充：用户明确以轻量为特色，要求避免防御性编程，同时以无缺陷和现有稳定行为为前提。已在开发约定和版本方案中落实为“边界集中校验、内部遵守约定、减少重复、避免假想兜底与提前抽象”。核对已发布代码后评估 v1 整体轻量，局部重复及对应整理建议见版本方案；本轮只更新文档。

## v2 本地实现与验证

用户随后明确授权“更新 v2”。解析代码移至 `metadata.py`，HTTP 与收藏保留在 `app.py`；无新增运行依赖。当前实现原始文本条目、JSON 格式化/复制原文、NAI/A1111/Forge 语义提取、ComfyUI 简单路径提示词、来源标签、无元信息状态，以及历史收藏按需升级。

历史数据不改表结构；升级前使用 SQLite backup 创建 `data/favorites.before-v2.sqlite3`。列表不加载图片 BLOB，不为刷新全量重解析；打开旧收藏才升级分类。无法重解析的历史原图回退到历史展示，不写回伪造的原文。备份本身包含图片与元信息，解除收藏只修改活动库，备份需用户自行管理。

- 自动回归：18 项解析/HTTP 测试通过，包括重复/压缩/后置文本、JSON 精度、角色、WebUI 设置、ComfyUI 简单/复杂图、空图收藏、无效读取失效旧会话、历史备份/升级/回退。
- 浏览器：合成样本完成 25 项主流程检查；另完成 5 项快速换图、上传中重置、服务端会话一致性和字段导出检查，并在新隔离上下文通过 6 项最终交互检查（含预览开关）。验证使用任务独立服务和临时 SQLite，未访问产品收藏库；无页面脚本异常。错误响应检查中的 400/409 是预期行为。
- 本地样图：NAI 正向/负向长度 1982/643；A1111 为 825/108、1 个模型及 3 个 LoRA 条目；Forge 为 544/3201、1 个模型及 5 个 LoRA 条目；复杂 ComfyUI 不提取推测参数，4 个原始字段可读；UI 参考图正确显示无生成元信息。
- 检查 `node --check static/app.js` 与 `git diff --check`。本次在 Linux/Python 3.12/Pillow 12.3 环境验证；尚未实际运行 Windows/Python CI 矩阵。

v3 独立收藏查看器和 v4 模型查询尚未实现。当前改动仅在本地，提交、push、发布依用户后续指令执行。
