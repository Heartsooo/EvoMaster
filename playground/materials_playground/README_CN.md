# Materials Playground

一个面向材料计算任务的轻量 EvoMaster playground。

它适合作为你自己的材料计算 agent 起点，适用于：

- 晶体 / 分子结构分析
- VASP / ASE / pymatgen 工作流规划
- 输入文件与作业脚本生成
- 计算结果总结
- 结合文献检索的材料研究任务

## 目录结构

```text
playground/materials_playground/
├── core/
│   ├── __init__.py
│   └── playground.py
├── prompts/
│   ├── system_prompt.txt
│   └── user_prompt.txt
└── workspace/
```

## 运行方式

```bash
python run.py --agent materials_playground --config configs/materials_playground/config.yaml --task "Analyze a CIF structure and propose a DFT relaxation workflow"
```

## 典型任务

- 读取 `POSCAR`、`CIF`、`XYZ` 并总结结构信息
- 生成 `INCAR`、`KPOINTS`、`submit.sh` 等输入模板
- 设计高通量材料筛选流程
- 总结吸附、能带、缺陷、形成能等计算任务

## 说明

- 当前版本刻意保持为单智能体、低耦合模板。
- 如果后续你需要 MCP 工具、多智能体协作或特定软件适配，可以在此基础上继续扩展。

## 已迁移能力

- 已迁入软件/计算引擎类 skills：`abacus`、`abinit`、`cp2k`、`gromacs`、`lammps`、`mlips`、`orca`、`pyatb`、`pyscf`、`quantum_espresso`
- 已迁入写作类 skills：`proposal-review`、`manuscript-scribe`
- 已接入 EvoMaster 原生 Bohrium 工具：`bohrium_job`（支持 `submit`、`poll`、`download`、`list_images`、`list_machines`、`kill`）以及 `bohrium_upload`（文件上传）
- 当前无需迁移 MatMaster 的 `SkillTool`，因为 EvoMaster 已内置 `use_skill` 工具

## 使用 skill

在 agent 配置中已启用上述 skills。运行时模型可以通过 `use_skill` 读取 skill 文档、引用参考资料或执行 skill 附带脚本。

## Bohrium 说明

当前已接入两类 Bohrium 工具：

- `bohrium_job`：支持 `submit`、`poll`、`download`、`list_images`、`list_machines`、`kill`
- `bohrium_upload`：支持把本地文件上传到 Bohrium OSS

典型任务示例：

```bash
python run.py --agent materials_playground --config configs/materials_playground/config.yaml --task "Use bohrium_job to list available CP2K images"
```

```bash
python run.py --agent materials_playground --config configs/materials_playground/config.yaml --task "Submit the directory /workspace/cp2k_case to Bohrium with image registry.dp.tech/dptech/cp2k:2024.1 and command cp2k.popt -i input.inp"
```

所需环境变量：

- `BOHRIUM_ACCESS_KEY`
- `BOHRIUM_PROJECT_ID`
- `BOHRIUM_BASE_URL`（可选）
- `BOHRIUM_USE_SANDBOX`（默认 `1`）
- `SERVICE_ENV`（默认 `test`）

额外依赖：

- `bohrium-sdk`：用于 `submit` 时上传输入压缩包
- `bohr-agent` CLI：用于 `bohrium_upload`

说明：

- `kill` 当前仅在 `BOHRIUM_USE_SANDBOX=1` 时可用
- `download` 依赖 Bohrium 返回作业产物列表；若目标作业尚未产出文件，会返回空结果

## 前端界面

已新增一个轻量前端控制台：

- 前端页面：`playground/materials_playground/web/index.html:1`
- 后端服务：`playground/materials_playground/web/server.py:1`

启动方式：

```bash
cd /home/heartsooo/evomaster/EvoMaster
python playground/materials_playground/web/server.py
```

然后打开：

```text
http://127.0.0.1:8787
```

这个前端当前支持：

- 输入自然语言任务
- 调用 `materials_playground` 运行
- 查看任务列表
- 实时轮询日志输出
- 使用材料计算任务模板快速发起任务

## 会话模式

前端现已升级为会话模式，具备：

- 一个 `session_id`
- 一个固定 `workspace`
- 每次发送消息都追加到同一会话
- 后端持久化 `message history` 到 `playground/materials_playground/web/.sessions/`
- agent 在后续运行中恢复结构化消息历史继续执行

前端页面会直接显示：

- `session_id`
- `workspace`
- `run_dir`
- 当前消息历史
- 最新运行日志

会话运行方式已参考 MatMaster 简化为结构化消息恢复：后端直接恢复 user/assistant messages，不再把历史拼成一个长 task 字符串。

已将 `materials_playground` 的 system prompt 改为 MatMaster 风格，并结合当前 EvoMaster 工具集做了适配。
