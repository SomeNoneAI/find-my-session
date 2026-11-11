# find-my-session 全面代码审查报告

- 审查日期：2026-11-06
- 审查对象：`/Volumes/SomeNone/git/mine/find-my-session`（HEAD `da4d108`，工作区含未提交改动）
- 审查方式：六路并行静态审查（架构/代码质量、安全、性能、测试、文档、依赖发布）+ 关键结论的源码与运行时实证核验
- 审查性质：**只读**。未修改任何源码、文档或配置；仅运行了 `unittest` 与只读 git 查询

---

## 0. 执行摘要

项目整体成熟度明显高于同规模个人项目：零运行时 pip 依赖、只读威胁模型、21+ 个 harness 适配器、641 个测试、CI 覆盖 Python 3.9–3.14 与前端 typecheck/test/build、静态产物漂移检查、SHA256 + provenance + Trusted Publishing、合成 fixtures、head/tail 限界读取与性能回归预算。**主要问题不是"缺功能"，而是"规模扩张后缺少收敛"**：复制粘贴式适配器扩展、共享层被 harness 知识侵蚀、默认值与输出契约没有单一事实来源、每次查询全量重扫、以及发布链路上的两个可越权漏洞。

### 0.1 必须先处理的实证发现（已运行验证，非推测）

运行 `python3 -m unittest discover -s tests`：

| 运行 | 结果 |
| --- | --- |
| 第 1 次 | `Ran 641 tests`，**13 failures**，1 skipped |
| 第 2 次 | `Ran 641 tests`，**11 failures**，1 skipped |

- 稳定失败的 11 个全部是 `tests/test_pi.py::PiTests`。典型断言：`pi:a1b2c3d4` 期望，实际 `pi:01a1a44f`。
- 波动的 2 个是 `test_cli.py::HarnessListingTests::test_planned_harness_errors` 与 `test_session_cache.py::test_harness_selection_matches_cli_parsing`；前者单独运行时通过，说明存在**测试间状态污染 / 顺序依赖**。
- **根因已定位**：工作区未提交的 `tests/cli_support.py` diff 中，删除了 `"FMS_PI_HOME": str(pi_home or self.pi_home)` 且未替换。该变量是 `core/fms_lib/harnesses/pi.py:233` 的 home 覆盖入口，删除后 Pi 适配器回退到 `Path.home()/.pi`；本机确实存在 `/Users/calvinchen/.pi`，于是测试**读取了真实用户会话**而非合成 fixture。
- 这同时是一个**隐私风险**：测试会扫描真实 transcript、把真实会话 ID/内容带进断言输出与 CI 日志，直接违反 `AGENTS.md` 的「fixtures 必须合成、绝不提交真实会话数据」不变式。
- 另两个波动失败与新增 `codebuddy-cn` 适配器后 baseline 断言未同步有关（WIP 未完成），印证「每加一个 harness 需同步改多处测试」的维护成本。

> 结论：**当前工作区不能作为发版基线**。这是 P0，且修复成本很低（恢复一行环境变量映射 + 补一条"禁止回退真实 home"的隔离测试）。

### 0.2 健康度评分（10 分制，主观但可比较）

| 维度 | 评分 | 一句话 |
| --- | --- | --- |
| 架构设计 | 6.5 | 无循环依赖，但 service 泄漏 adapter 实例、抽象基类未成契约 |
| 代码质量 | 6.0 | 类型标注与 3.9 兼容性扎实，但复制粘贴严重、静默吞错多 |
| 可维护性 | 5.5 | 22 个适配器复制式扩展，默认值/常量/契约无单一来源 |
| 性能 | 6.0 | 读内容层有界设计优秀，但枚举层每次全量重扫、无索引 |
| 安全性 | 6.5 | 本机只读威胁模型落地扎实，但 HTTP 面板无鉴权、发布链可越权 |
| 测试覆盖 | 7.0 | 量大面广，但当前红灯、弱断言、核心模块无单测、flaky |
| 文档完整性 | 6.5 | 覆盖广且中英同步，但 CLI 能力文档与 CHANGELOG 明显滞后 |
| 依赖与发布 | 6.0 | 零运行时依赖与 SHA pin 到位，但 lockfile 混入镜像、发布校验可绕过 |

---

## 1. 重要上下文：工作区处于 WIP 状态

`git status --short` 显示 9 个已跟踪文件被修改、4 个新文件未跟踪，内容是**新增 `codebuddy-cn` 适配器**及其文档/测试：

```
 M CHANGELOG.md, README.md, README.zh-CN.md, core/fms_lib/registry.py,
   docs/compatibility.md, skills/find-my-session/SKILL.md,
   tests/cli_support.py, tests/test_cli.py, tests/test_ui.py
?? core/fms_lib/harnesses/codebuddy_cn.py
?? skills/find-my-session/references/codebuddy-cn.md
?? tests/codebuddy_cn_fixture.py, tests/test_codebuddy_cn.py
```

因此下列"文档不一致"属于**进行中的同步工作，不应误判为长期缺陷**：

- `registry.py:42-65` 现为 **22 个 READY**（含 `CodeBuddyCNAdapter()`）+ `PLANNED` 仅 1 个（`cline-vscode`）；两个 README 的 WIP diff 已改为 "Twenty-two / one more"，`docs/compatibility.md:49` 也已补 `CodeBuddy CN` 行，`SKILL.md` 已补 references 条目。静态审查中「矩阵 21 行、文档写 21 ready / 2 planned、codebuddy-cn 全仓 0 匹配」的结论**已被 WIP 修复**。
- 但 WIP 引入了上述测试红灯与 flaky；且 `test_cli.py` 把 planned 用例从 `codebuddy` 改成 `cline-vscode`，符合实际。

已核实的仓库卫生正面结论：`git ls-files '*.pyc' | wc -l` = **0**，`.pyc` 未被跟踪（静态审查中"可能被跟踪"的担心不成立）。

---

## 2. 分维度审查

### 2.1 架构设计

**总体**：依赖方向基本单向 `cli/mcp/ui → service/registry → harnesses → models/util`，无 import 环；但存在多处"绕过 service 直达 adapter"与"共享层吸收 harness 私有知识"的破口。

| 编号 | 严重度 | 证据 | 风险 | 建议 |
| --- | --- | --- | --- | --- |
| A1 | 高 | `core/fms_lib/service.py:294` `resolve_session` 返回 `Tuple[HarnessAdapter, SessionSummary]` | 适配器实例泄漏给所有上层；`cli.py:177-179` 与 `fms_ui/server.py:169-175` 各自直接调 `adapter.load()` / `resume_argv()`，形成两份重复调用路径，并导致 CLI/MCP/UI 三种不同的 detail JSON 形状（`server.py:174` 额外塞 `resume_argv`） | service 返回不透明 `SessionDetail`/`ResumePlan`，提供 `load_detail(ref)`、`resume_argv(ref)`；禁止 UI/CLI 直接 `import registry` |
| A2 | 高 | `core/fms_lib/harnesses/base.py:11-34` 仅 `home()` 是 `@abstractmethod`，其余 4 个核心方法都是普通方法 `raise NotImplementedError`；`service.py:424-425` 靠捕获 `NotImplementedError` 判断"不支持 prompts" | 静态检查无法约束契约；"用异常做能力探测"与 `AGENTS.md:25`「每个 adapter 都实现 `iter_prompts`」相矛盾 | 全部改 `@abstractmethod`，删除能力探测分支，用契约测试强制 |
| A3 | 中 | `base.py:21-22` `session_roots()` 默认 `[home()/"projects"]`；`service.py:177-178,304-309` 共享层解析 `<db>#<id>` 虚拟路径；`diagnostics.py:32,43-53` 硬编码 zstd 提示并按异常文本分类；`service.py:318-320` 错误示例写死 `qoder-cn:...`；`render.py:192` 硬编码待办状态集合 | 违反 `AGENTS.md:23`「共享层保持格式中立」，新增 harness 时需改共享层 | 基类改抽象或抛明确错误；虚拟路径封装为 `resolve_virtual_path()`；用 `DecoderMissingError` 结构化异常替代字符串匹配；中性文案 |
| A4 | 中 | `registry.py:41-65` 模块加载时构造 22 个**单例**且部分带可变缓存；`service.py:53-56` 用 8 线程并发调用同一批单例；`codex.py:487-492`、`qoder_family.py:195`、`kimi_code.py:283` 等无锁缓存（仅 `antigravity_family.py:177` 加锁） | 数据竞争与脏读；也是 2.5 节 flaky 的可疑来源 | adapter 无状态化，缓存集中到 service 层 `ScanContext`；或全部加锁 |
| A5 | 中 | `registry.py:9-30` 手工 import + 手工插入 + `service.py:13` / `server.py:18` 直接依赖装配层；新增一个 harness 需同步 SKILL.md、references、两个 README、compatibility.md、CHANGELOG、能力清单及多处测试基线 | 扩展成本高、易漏（本次 WIP 就漏了测试基线） | `pkgutil.iter_modules` 自动发现 + 声明式 `HARNESS_META`，由元数据生成文档与契约清单 |
| A6 | 低 | `scripts/fms:7-10` 与 `server.py:30-33` 各自实现路径嗅探 + `sys.path.insert` | `session_cache` 可能被以两个模块名加载两次、分裂单例 | 统一为包入口/importlib 解析 |
| A7 | 低 | `registry.py:93-94` `has_harness()` 对 PLANNED 返回 True，而 `lookup_harness():109-114` 抛"planned"错误 | 语义不一致 | 引入 `HarnessStatus` 枚举统一 |

### 2.2 代码质量与可维护性

**总体**：36/37 个库文件都有 `from __future__ import annotations`，未发现 `match`/`slots=True`/PEP 604 运行时联合等 3.9 不兼容用法，未发现可变默认参数、TODO/FIXME、明显死代码；`mypy`/`ruff` 已在 pyproject 配置。主要债务是重复代码与静默失败。

| 编号 | 严重度 | 证据 | 风险 | 建议 |
| --- | --- | --- | --- | --- |
| Q1 | 高 | `harnesses/common.py:39-110` 已有公共 helper，却仍有 **17 份 `_clean_prompt`、9 份 `_normalize_todos`、4~6 份 `_display_id`、`_table_columns`、14 份 `_file_path`**；`cursor.py:283-342` 完整重写 `is_generic/choose_title/tool_detail` | 修一处 bug 要改 17 个文件；行为逐步漂移（如 `minimax_code.py:247` 的 `_normalize_todos` 返回 `Optional[List]`，其余返回 `List`） | 抽 `sqlite_adapter.py` 基类 + `prompt_utils.py`，用参数化字段映射替代复制 |
| Q2 | 高 | `minimax_code.py:274-1180` 单类约 900 行（`summarize` 134 行、`_load_from_db` 132 行）；`codex.py:478-996` 类 518 行、`load` 148 行；`kimi_code.py` 类 698 行；`cursor.py` 类 487 行；`cli.py:254-543` `build_parser` 290 行；`render.py:143-253` 111 行/12 个条件块 | 认知负荷高、难做单测 | 按"扫描/摘要/详情/prompts"四阶段拆分，函数控制在 60 行内；parser 拆 `add_*_parser()` |
| Q3 | 高 | 18 个 adapter 重复同一组限额常量（`MAX_PROMPT_CHARS=4000` 等），`HEAD_BYTES` 存在 4 种值、`HEAD_RECORDS` 5 种值；默认值互相矛盾：`render.py:145` vs `:258` 同名渲染函数 `messages` 默认 **2 vs 10**、`chars` **600 vs 0**；`mcp.py:113` 描述 "default 2" 但 `:220` 传 10；CLI/UI/cache 各有自己的 limit 常量 | 同一操作在不同入口产出不同结果，用户无法预期 | 建立单一 `Limits` / `Defaults` 常量对象，各入口引用；JSON 输出做版本化 schema |
| Q4 | 高 | `service.py:24-27` 与 `base.py:48-49` 只捕 `(OSError, ValueError)`；`util.py:158-159,170-171,188-189,197-198,204-205,239` 损坏行/编码错误一律静默丢弃；`fms_ui/session_cache.py:180,218` `except Exception: pass` | `sqlite3.Error`/`KeyError`/`TypeError` 会在 `ThreadPoolExecutor`（`service.py:54-56`）中冒泡并终止整批扫描；默认无 `--verbose` 时用户完全不知道有多少会话被跳过 | 边界统一捕获并转 `ScanReport` 条目；始终收集并在结果元数据里返回跳过计数 |
| Q5 | 中 | `mcp.py:214-216` 用 `arguments["ref"]` 下标取值，缺 `ref` 抛 `KeyError`，而 `:252` 只捕 3 类异常，会让 `serve()` 主循环（`:325-340`）整体崩溃；`cli.py:552-561`、`server.py:233-243` 顶层也只处理 4 类异常 | 单个畸形请求打挂 MCP / 返回 traceback | `_required_str()` 校验 + 顶层 `except Exception` 兜底映射为脱敏错误 |
| Q6 | 中 | `util.py:48-50` naive 时间假定 UTC，而 `:62-63` `datetime.strptime(...).astimezone(UTC)` 按**本机时区**解释；两者策略互斥 | `--since 2026-10-01` 结果随机机器时区漂移 | 统一显式 `datetime(..., tz=UTC)`；补 UTC/+08/-05 时区矩阵测试 |
| Q7 | 中 | `models.py` 全部 dataclass 非 frozen 且含可变 `List/Dict`；`:156,159,160` `to_dict()` 直接把 `todos`/`edited_files`/`tool_counts` 的**内部引用**交给调用方，而 `session_cache.py:160` 浅拷贝后长期缓存 | 外部修改污染缓存快照 | 核心值对象 `frozen=True`；`to_dict()` 返回 `list(...)`/`dict(...)` 副本 |
| Q8 | 中 | `search.py:14-49` 与 `:51-92` 两份几乎相同的评分逻辑（魔法分数重复）；`service.py:109-123` 与 `:126-160` 重复"过滤→评分→排序→limit"流水线 | 修改评分规则易只改一处 | `score_summary` 返回 breakdown，`explain_score` 派生；抽 `SearchPipeline` |
| Q9 | 中 | `iter_prompts` 契约未统一：部分 adapter 去重（用 `seen`），部分不去重；时间解析有 `util.parse_timestamp` 但仍各自实现（`cursor.py:239-280`、`cline.py:242` 等）；16 处各自按文件 mtime 排序后 `service.py:122,159` 再按 `updated` 排一次；9 处硬编码 `archived=False` | `service.py:352-394` 的分页正确性隐含依赖"迭代顺序 = 时间升序且已去重"这一未写入文档的假设 | 在基类契约中明确升序/去重/归档判定，由 service 统一排序与校验 |
| Q10 | 低 | `pyproject.toml:40` `dependencies = []`（零第三方 import 属实），但 `fingerprint.py:99-118`、`codex.py:142-155`、`deepseek.py:87-121` 依赖外部 `zstd` CLI；`compression.zstd` 仅 3.14+ | 对 `AGENTS.md`「Standard library only」的实质性放宽，3.9–3.13 用户缺 CLI 时压缩会话被跳过 | 明确标注为可选系统能力；`doctor` 输出最低版本；补"无解码器"降级测试 |
| Q11 | 低 | `fingerprint.py:111` 生产代码用 `assert process.stdout is not None`（`-O` 下被移除）；`:111` `finally` 无条件 `kill()`；`stderr=DEVNULL` 吞掉解压错误 | 优化模式下潜在 None 解引用、诊断信息丢失 | 显式分支 + `terminate()/wait(timeout)`，错误计入 `unreadable` |

### 2.3 安全性与隐私

**总体**：本机只读威胁模型落地扎实——绑定 `127.0.0.1:8765`、`Host` 白名单防 DNS rebinding、静态资源白名单、CSP/`nosniff`/`X-Frame-Options`、`sqlite mode=ro`、全部 subprocess 用 argv 列表、Vue 端无 `v-html`/`innerHTML`、无 `eval`/`pickle`/`shell=True`、fixtures 抽检全合成、发布 ZIP 用显式白名单。但存在 3 个高危项。

#### 可直接利用的高危项

| 编号 | 严重度 | 证据 | 攻击场景 | 修复 |
| --- | --- | --- | --- | --- |
| S1 | **高** | `fms_ui/server.py:225-244` `do_GET` 只校验 Host；`:275-276` 绑定 loopback；全文件无 `Authorization`/token/`Origin` 校验（已 grep 确认 0 命中） | 本机任意进程/同机其他用户 `curl http://127.0.0.1:8765/api/prompts?ref=...` 即可读取全部 prompt 全文、`cwd` 与绝对路径 | 启动时生成 128-bit 随机 token，仅经启动 URL/自定义 header 传递并逐请求校验；校验 `Origin` 与 `Sec-Fetch-Site`；拒绝 `Access-Control-Request-Private-Network`；token 不写日志 |
| S2 | **高** | `.github/workflows/release.yml:3-7` `push: tags v*` 与 `workflow_dispatch` 并存；`:28-33` 只校验 `${GITHUB_REF_NAME#v} == __version__`，**未校验 `github.ref_type == 'tag'`**；`:16` 持 `contents: write`、`:117` 用 `--clobber`、`:129-148` Trusted Publishing | 建一个名为 `v0.1.3` 的分支并手动 dispatch，即可绕过 tag 校验，从分支构建、覆盖 release 并把任意 wheel 发布到 PyPI | 所有发布 job 加 `if: github.ref_type == 'tag' && startsWith(github.ref, 'refs/tags/v')`；校验 tag 指向 HEAD；去掉 `--clobber`；或删除 `workflow_dispatch` |
| S3 | **高**（需上游配合） | `release.yml:167-172`：`curl -L .../releases/**latest**/download/mcp-publisher_*.tar.gz \| tar xz` 后立即 `./mcp-publisher login github-oidc`；无版本/SHA/checksum/`--fail`，且该 job 有 `id-token: write`（`:153-155`） | 上游 `latest` 资产被替换或传输被劫持 → 在持 OIDC 凭据的 runner 上执行任意代码 | 固定到具体 release tag + 已知 SHA256（`sha256sum -c`）或换 SHA-pinned action；`curl --fail --proto '=https'`；隔离 OIDC 权限到最终发布步骤；checkout 加 `persist-credentials: false` |

#### 中低危纵深防御缺口

| 编号 | 严重度 | 证据 | 建议 |
| --- | --- | --- | --- |
| S4 | 中 | `server.py:168-175` + `service.py:295-309`：`ref` 直接 `Path(ref).expanduser()` → `is_file()` → `adapter_for_path()`；`ref=/Users/victim/.ssh/id_rsa` 会回显 `"file is not inside a known harness session store: <绝对路径>"` | HTTP/MCP 禁用路径形式 ref，只接受 `harness:id`；规范化后拒绝绝对路径/`..`/NUL/控制字符；统一错误文案不回显路径 |
| S5 | 中 | `server.py:233-243` 只捕 4 类异常；`sqlite3.Error`/`TypeError` 等未捕获会由 `socketserver` 打印完整 traceback 到 stderr 并断连 | 补 `except Exception` 脱敏 500；`parse_qs(strict_parsing=True)` 并限制参数个数与键值长度 |
| S6 | 中 | `server.py:131,133-142,173,182-185` + `session_cache.py:24,123-134`：`ThreadingHTTPServer` 线程无上限、`wait=true` 每请求最多 10s、`deep=true` 服务端不传 timeout（CLI 才有 `--timeout`）、`offset` 传 `maximum=0` 实为无上限 | 有界线程池 + 限速 + 强制 deep deadline + `offset/limit` 上限 + 请求体长度限制 |
| S7 | 中 | `util.py:90-110` `one_line()`/`block_text()`、`render.py:64-253` 未剥离 ANSI/C0/bidi 控制字符；transcript 原文直出终端/Markdown/日志 | 统一 `sanitize_output()`，所有面向终端/文档/JSON 的字段过一遍 |
| S8 | 中 | `server.py:240-241`、`cli.py:559`、`service.py:299-301`、`mcp.py:252-253` 等把含真实 home 的绝对路径回显；项目已有 `diagnostics.sanitize_detail()` 却未用于这些路径 | 统一走分类脱敏文案；默认输出用 `abbreviate_path()` 把 home 变 `~` |
| S9 | 中 | `harnesses/cursor.py:421-422` `uri = "file:%s?mode=ro" % path` 未做 URI 编码（其余 adapter 用 `path.as_uri()`）；Unix 文件名可含 `?`/`#` | 统一 `path.resolve().as_uri() + "?mode=ro"`，并断言 `mode=ro` 以保证只读不变式 |
| S10 | 中 | `codex.py:158-226`、`deepseek.py:124-160`、`util.py:214-246` 流式读**整个解压结果**，无解压后字节/行数/单行长度上限；`fingerprint.py:87-118` 的 `read(cap=2MB)+kill` 是正确样板 | 把该模板推广到所有解压路径（32–64MB 上限 + 行数上限 + 单行 1MB），给 zstd 子进程加超时 |
| S11 | 中 | `models.py:66-85,105-134`、`render.py:159,172,175-223`、`cli.py:515-525`、`server.py:173,182-186`：`show` 默认打印绝对路径与 Task/Recent turns；`prompts` 默认 `--chars 0`/`--limit 0`（全部）；`/api/sessions` 含 prompt 全文、`/api/session` 100 轮无截断 | 默认截断 + `--full` opt-in；提供 `--redact`（邮箱/`sk-`/`ghp_`/`AKIA`/Bearer/home 路径）；UI 加"隐藏敏感信息"开关 |
| S12 | 中 | `mcp.py:186-254` 未按 `TOOL_DEFINITIONS` 的 inputSchema 校验（`order` enum、`limit/offset/chars` 上限、`ref` 必填）；`serve():320-340` 逐行读 stdin 无行长上限 | 按 schema 做 `enum`/`maximum` 校验 + 行长上限 |
| S13 | 中 | `tools/build_artifacts.py:12` `COPY_IGNORE_PATTERNS` 仅 `("__pycache__","*.pyc",".DS_Store")`；`shutil.copytree` 默认 `symlinks=False` 会跟随链接；`.gitignore` 未忽略 `*.db`/`*.sqlite`/`*.jsonl`/`.screenshots/` | 扩充 deny-list（`.env*`/`*.db`/`*.jsonl`/`.git*`/`node_modules`/日志/截图）；`symlinks=True` 并拒绝链接；打包后断言 ZIP 条目全在白名单；CI 加 secret 扫描 |
| S14 | 中 | `.github/workflows/pages.yml:39,42,55` 是唯一使用浮动 tag（`@v5/@v3/@v4`）的 workflow；顶层 `pages: write`/`id-token: write` 对 build job 也生效 | 三个 action 改 SHA pin；权限下移到 deploy job |
| S15 | 低 | `cli.py:177-205` `resume --exec` 用 argv 列表无 shell，但 `session_id` 来自文件名/DB 行，以 `-` 开头可能造成目标 CLI 参数注入；MCP 把 transcript 原文交给宿主 LLM，存在间接提示注入面 | 校验 ID 字符集、`--` 之后传参、`--exec` 二次确认；MCP 输出把内容包进明确标记的非指令数据块 |
| S16 | 低 | `server.py:218-223` `_valid_host()` 只取 `hostname`，`Host: evil.com@127.0.0.1` 可通过；未实现 `do_POST/do_HEAD/do_OPTIONS`，基类 501 错误页不带安全头 | 精确匹配完整 Host（含端口）；显式实现这些方法返回带安全头的 JSON 405/501 |

**SQL 注入核查结论（正面）**：动态 SQL 的列名来自硬编码白名单与 `PRAGMA table_info` 交集、值全部 `?` 绑定、表名正确转义，未发现拼接用户输入。fixtures 抽检（30 个 `.json/.jsonl`）无真实路径/邮箱/token，`tests/` 下真实 `/Users/`、密钥样式字符串 0 命中。

### 2.4 性能与可伸缩性

**总体**：读内容层做得不错——`util.py:163-211` 的 head/tail 限界读取、`test_performance.py:143-152` 的「6MB transcript 读取量 < 尾部上限」回归、`session_cache.py` 的 single-flight + stale-while-revalidate、`fingerprint.py` 的 `read(cap)+kill`、模块级正则预编译、前端仅提交触发搜索 + `AbortController`。实测 1000 session 0.21s / 10000 session 2.39s，均远低于预算。**瓶颈集中在枚举层与压缩解码层**。

| 编号 | 严重度 | 证据 | 影响 | 建议 / 收益 |
| --- | --- | --- | --- | --- |
| P1 | 高 | `service.py:33-56` `_gather_summaries` 无条件 `list(adapter.iter_session_paths())` 并对每个路径 `summarize()`，无缓存/索引；`search_sessions():141-143`、`query_summaries`、`stats():234-235`、`doctor():201`、`list_project_paths():287`、`resolve_session():323-325` 同构 | CLI/MCP 每条命令全量重扫 22 个 store | 以 `(path, st_mtime_ns, st_size)` 为 key 持久化摘要索引到 `~/.cache/fms/index.sqlite`，只重扫变更文件；抽 `SnapshotProvider` 让单命令复用一次扫描。预期冷查询 **10–100×** |
| P2 | 高 | `service.py:141-143` 先全量 `_gather_summaries()` 再 `_filter_summaries()`（`:67-75`）；`_limit()`（`:78-81`）在 `search.py:128` 全量打分+排序之后才切片 | `fms latest --since 24h --limit 1` 仍读几年历史；`--include-archived` 过滤也在读盘之后 | 把 `since/cwd/limit/archived` 下推到 `iter_session_paths()`（多数 adapter 已按 mtime 降序），无 query 时用 `islice` 提前终止；`heapq.nlargest(limit, ...)`。这是**最直观的用户痛点** |
| P3 | 高 | `codex.py:51-54,142-155` 与 `deepseek.py:52-55,108-121`：`compression.zstd` 仅 3.14+，3.9–3.13 每次 `_open_zstd()` 都 `shutil.which` + 启动新进程；`deepseek.py:465/520/570/533` 对同一文件 **4 次各自完整解压**；`codex.py:706-720` 多次 `_scan_session` + `_iter_head_records` | 一次「搜索→选中→看详情→切 prompts」触发 3–4 个 zstd 进程与数倍全量解压 | 缓存 `which` 结果；按 `(path, mtime_ns, size)` 做 LRU 缓存解码后的 head/tail；加 `max_bytes` 上限。压缩 store 搜索数十× |
| P4 | 高 | `server.py:159-167` `/api/stats` 每次请求 `stats_service()` → `service.py:256-260` 对每个 session 调 `usage_summary()`（"需要完整遍历 transcript"）且**完全不走缓存**；`useWorkspace.ts:87-101` 每次搜索成功后自动 `loadSession(nextRef)` 再触发一次 `/api/session` 全量解析 | 打开统计面板/每次搜索都要全量逐行解析所有 transcript | `/api/stats` 接入快照或 sidecar 缓存；详情改为用户显式选择才加载。预期秒级 → <100ms |
| P5 | 高 | `gemini_cli.py:128-164` `_replay()` 逐行 `json.loads` 后把**全部 message** 追加进 `List`（Python 对象约 3–10× 原始大小），且 `summarize/iter_prompts/load` 各调一次 = 同一文件 3 次全量解析；`cursor.py:573-577,613-636` 同类，`_iter_json_transcript` 直接 `read_text()` 整个 JSON | 几十 MB transcript 内存放大甚至 OOM | 复用 `iter_head_records`/`iter_tail_records` 或 `deque(maxlen=200)`；`util.py:214-223` `iter_file_records` 加 `max_bytes` |
| P6 | 高 | `service.py:352-394` `_collect_prompt_page` 无论 `limit` 多小都完整迭代 `iter_prompts()` 才算 `total`；`cli.py:513-519` `prompts --limit` **默认 0（全部）**、`--chars 0`（全文） | `--limit 1` 仍解析整个 transcript；默认输出整本会话 | prompt 总数按文件 mtime 建 sidecar 索引 / 快速计数路径；默认 `--limit 20`、`--chars 600`；把 `deque` 窗口策略推广到所有分支 |
| P7 | 中 | `server.py:143,154-158` 仅 `/api/projects` 与非 deep `/api/sessions` 走缓存；`session_cache.py:30-39` fingerprint 只比较 store 路径字符串（不含 mtime），失效完全依赖 60s TTL；`:215-226` 后台 Timer 每 60s **无条件**全量刷新 | 面板空闲也持续读盘；UI 重端点每请求全量 | fingerprint 加入各 store 根的 `st_mtime_ns`；Timer 改「近 5min 有请求才刷新」；`/api/stats`、`/api/session`、`/api/prompts`、deep 接入缓存 |
| P8 | 中 | `models.py:66-85` 列表 DTO 含 `first_prompt`/`last_prompt` 全文；`server.py:131` `/api/sessions` 上限 500 条可达 4–8MB；`service.py:273-279` `/api/projects` 返回全部 cwd 无上限；`server.py:199` 除 favicon 外全部 `no-store`、无 gzip/ETag（尽管 `_revision` 可直接做 ETag） | 静态资源每次重传 ~129KB（`app.js` 106KB + `styles.css` 23KB），大 JSON 传输浪费 | 列表 DTO 裁剪到 200 字符；`/api/projects` 加 limit；静态资源 hash + `immutable`；API 用 revision 做 ETag/304；启用 gzip。响应体 -90%+ |
| P9 | 中 | `registry.py:118-120` 默认返回全部 22 个 adapter，无 store 存在性预筛；`service.py:322-325` 单 ref 查询对 22 个 adapter 各跑一次 `find()`（`gemini_cli.py:218-233` 还对每个不匹配路径逐行解析找 sessionId）；`_gather_summaries` 产生 4 份全量列表副本 | 未安装的 harness 也枚举；单 ref 查询 22 次目录遍历 | 先 `is_dir()` 快速预筛；`find()` 命中短路；用生成器链减少副本 |
| P10 | 中 | `search.py:14-49` 对每个 summary 做 6 次 `normalize_text()`（NFKC+casefold），`explain_score():51-92` 原样重算；`:119-125` deep 匹配串行且 deadline 只在 session 边界检查；`service.py:158-159` `latest=True` 在全量排序后再全量排一次 | 万级 session 时评分/排序数倍开销；deep 可能长时间挂起 | 缓存 `_search_blob`；deep 并发 + deadline 下推到 chunk 循环；排序策略一次完成；UI deep 默认 5s |
| P11 | 中 | `cursor.py:415` 索引缓存用 `int(st_mtime)` 秒级粒度；`server.py:263-276` `ThreadingHTTPServer` 无并发/背压，多个 deep/stats 请求可同时触发多份全量扫描 | 同秒内修改漏检（正确性）；并发下 CPU/磁盘 N 倍放大 | 统一 `st_mtime_ns`；重扫描端点全局 `Semaphore(1)` 串行化 |
| P12 | 中 | 前端 `ProjectAutocomplete.vue:227-245` 渲染全部匹配项目路径无 slice/虚拟化；`utils.ts:47,70` 每次调用新建 `Intl.DateTimeFormat`/`RelativeTimeFormat`（50 行约 100–150 次）；`useWorkspace.ts:22,103-125` `POLL_ATTEMPTS=12` × `WAIT_TIMEOUT=10s` 理论最长 120s 长轮询 | 项目多时输入卡顿、大列表渲染 CPU 高 | `filtered.slice(0,100)`/虚拟滚动；Intl 实例模块级单例；autocomplete 加 200ms debounce；POLL_ATTEMPTS 降到 3–4 |

**真实痛点 vs 理论问题**：P1/P2/P3/P4/P6/P8 是日常可感知的等待与流量；P5 的 OOM、P10 的 NFKC 开销、无虚拟滚动等属规模到位后才显现。改进应复用项目已有的 head/tail 限界、single-flight、`read(cap)+kill` 范式，不要另起炉灶。

### 2.5 测试覆盖与 CI 门禁

**总体**：33 个 `test_*.py`、约 641 个测试、15 个合成 fixture 生成器 + 5 个静态 fixture home；22 个 READY adapter 与 9 个 CLI 子命令都有对应测试文件；CI 覆盖 `compileall`/`unittest`/ruff/mypy/npm typecheck+test+build/static 漂移/`python -m build`/coverage。但**当前红灯**，且覆盖形态高度集中在「`cli.main()` 端到端 + 合成 happy path」。

| 编号 | 严重度 | 证据 | 建议 |
| --- | --- | --- | --- |
| T1 | **最高** | 见 §0.1：641 测试中 11–13 个失败，根因是 `tests/cli_support.py` WIP diff 误删 `FMS_PI_HOME`，测试回退读取真实 `~/.pi` | 恢复该环境变量映射；`mock.patch.dict(os.environ, env, clear=True)`（当前 `:510` 未用 `clear=True`，真实 `HOME`/`APPDATA`/`XDG_*` 仍可泄漏）；加一条「patch `Path.home` 为哨兵路径并断言任何 adapter 都不读取它」的隔离测试；把隐私扫描抽成公共 helper 覆盖全部 fixture home 并加入 `sk-`/`ghp_`/Bearer 正则 |
| T2 | 高 | `tests/test_cli.py:958-985` `test_commands_do_not_modify_store` 连调 13 条命令却**完全忽略返回码**，只断言快照未变——即使全部崩溃测试仍通过；`test_cli.py:46-49` 时间断言只查 `year >= 2020`（差 1000 倍也能过）；`test_mcp.py:32` 用裸 `assert`（`-O` 下被剥离）；`test_json_contract.py:85-138` 只断言「键存在」不查类型/值域/多余键 | 逐条断言 `code == 0` 且输出非空；精确 `assertEqual`；统一 unittest 断言方法并加 CI 检查禁止裸 assert；契约测试加类型与"无未声明字段"断言 |
| T3 | 高 | `tests/cli_support.py:288-307` + 15 个 `*_fixture.py`：fixture 由「了解 adapter 解析规则」的生成器写出（时间、字段形状精确对齐实现），**不存在独立于实现的 golden 语料**；实现理解错字段时 fixture 与断言会一起错 | 引入按公开格式规范手写的 golden 语料 + 随机字段删除的 property/fuzz 测试，打破同源 |
| T4 | 高 | 核心库缺独立单测：`models.py`、`errors.py`、`harnesses/base.py` 完全无测试；`search.py`（`score_summary`/`search_summaries`/`DeepTimeout`）、`service.py`、`render.py`（11 个函数中仅 1 个被直接调用）、`util.py`（15 个公开函数仅 2 个有直接测试）、`registry.py`（4/5 函数）全部靠 CLI 间接覆盖 | 新增 `test_util.py`/`test_models.py`/`test_registry.py`/`test_render.py`/`test_search.py`/`test_malformed_records.py` |
| T5 | 中 | 负输入覆盖稀薄：唯一「损坏 transcript」是 `test_diagnostics.py:105-110` 的伪 zstd 帧且只针对 DeepSeek；无普通非法 JSONL/缺字段、非法 UTF-8/BOM/UTF-16、损坏 SQLite、真实 `chmod 000` 权限错误；`test_codex.py:545` 与 `test_diagnostics.py:642-654` 在**无解码器环境直接 skip**，恰好跳过了最需要验证的降级路径 | 补负输入矩阵；用 `mock.patch.multiple` 强制 `_zstd=None` + `which→None` 做不依赖真实解码器的强制负路径测试 |
| T6 | 中 | 时区与平台：`util.py:53-67` 的 `7d/24h` 与本地午夜分支无测试、无 TZ 矩阵；`test_cli.py:917` 只有 Windows 隐私反向断言，无 `APPDATA`/`USERPROFILE`/非 ASCII home 正向用例；`ci.yml:189` Windows job `continue-on-error: true`（唯一 Windows 门禁形同虚设） | 固定 now + UTC/+08/-05 三种 TZ；参数化 Windows 路径注入；修好 Windows 后移除 `continue-on-error` |
| T7 | 中 | 前端仅 6 个 `.test.ts` / 23 个 `it()`，`App.vue`/`SearchFilters.vue`/`SessionDetail.vue`/`SessionList.vue`/`utils.ts`/`api.ts` 零测试；`testing/fixtures.ts:43-55` `stubFetch` 永远返回 `{ok:true}`，`api.ts:7-29` 的 4 条错误路径零覆盖；`package.json:6-11` 无 lint/coverage/E2E | 新增 `api.test.ts`（4 类错误 + AbortError）、`utils.test.ts`；补组件 loading/empty/error 三态；加 ESLint、`@vitest/coverage-v8` 阈值、Playwright 冒烟 E2E |
| T8 | 中 | `ci.yml:220-224` coverage 仅 `report --fail-under=80`，无 `--branch`、无按模块/新增行阈值、无 XML artifact、无 PR diff-coverage，且不阻断其他 job；`ci.yml:3-17` 无 `concurrency`、无 `schedule`；`release.yml:35-78` 只跑 3.14，缺 ruff/mypy/coverage/3.9 + zstd CLI 降级验证，`SdistBuildTests` 因缺 `build` 被 skip | `coverage run --branch` + 按模块阈值 + XML artifact + PR diff-coverage；`build`/`packaging` `needs: [coverage]`；加 concurrency 与 nightly；release `needs` CI 全绿或补齐门禁 |
| T9 | 中 | `CHANGELOG.md:69-75,154-159` 记录了 4+2 个 Fixed bug，但仓库无具名回归测试；`test_performance.py:246` 用墙钟 `elapsed < 5.0/30.0` 断言，跨平台易偶发失败；`test_explain.py:44-50` 用 `--timeout 0.000001` 依赖真实调度 | 每条 Fixed 建 `test_regression_<slug>.py`；改用已有 `_ReadTracker.bytes_read` 做确定性断言；注入 fake clock / `threading.Event` 门控 |
| T10 | 低 | `cli_support.py:300-307` `os.utime` 只固定 `.jsonl`，`.json`/`.sqlite`/zstd 沿用当前时间；`test_common.py:72-74` 自比 `expanduser` 属同义反复；`test_artifacts.py:105-128` 解压产物只跑 `--version` 冒烟；`test_release.py:76-78` 只 `assertTrue(callable(...))` | 全文件统一 `os.utime`；patch `Path.home()`；让解压产物实际执行 `fms harnesses`/`fms search` 并断言输出 |
| T11 | 低 | `AGENTS.md:34-48` 的「Run before finishing」未提及 ruff/mypy/coverage，而 `pyproject.toml:43-48` 已声明 dev 依赖且 CI 已执行；`pyproject.toml:90-97` mypy 不检查 `tests/` | 把 `ruff check .`、`mypy`、`coverage run --branch` 写入 AGENTS.md，保持文档与门禁一致 |

### 2.6 文档完整性与一致性

**总体**：48 份 `.md`；安装/入口点/隐私/Python 版本/卸载/故障排查/MCP 配置覆盖完整，中英 README 基本同步，未发现真正的相对链接死链，版本单一来源（`__version__ = 0.1.3` → `pyproject.toml:69` dynamic → `server.json:10,15`）设计正确。问题是**能力文档滞后于代码**。

| 编号 | 严重度 | 证据 | 建议 |
| --- | --- | --- | --- |
| D1 | **高** | `skills/find-my-session/SKILL.md` 全文 `mcp` **0 次匹配**（已 grep 确认），但 `cli.py:385` 有 `fms mcp`、`README.md:124`、`docs/mcp.md`、`server.json` 均已文档化；`.agents/skills/add-harness/SKILL.md:26-39` 的 12 项 capability checklist 也完全没有 MCP 与 `--version`/`--explain`/`--timeout`/`--format`/`--no-todos`/`--no-tools` | 违反 `AGENTS.md:31-32` 的不变式：在 SKILL.md 增加 `fms mcp` 小节并链接 `docs/mcp.md`；checklist 增加「MCP tool surface」行与全局选项覆盖表；最好加一条自动对照 `build_parser()` 的测试 |
| D2 | 高 | `CHANGELOG.md:7` 的 `0.1.3` 发布段只有 1 条 README 变更，而 `mcp`/`stats`/`resume`/`pi`/`omp`/`--explain`/`--timeout` 等**代码已实现且 README 已文档化**的能力仍全列在 `:17-67` 的 `[Unreleased]`，且 `[Unreleased]` 排在 `0.1.3` **之后**（违反 Keep a Changelog） | 明确版本边界：要么把这些条目并入 `0.1.3`，要么 bump 到新版本并同步 `__init__.py`/`server.json`；`[Unreleased]` 移到文件顶部，与 `RELEASING.md:40` 对齐 |
| D3 | 中 | `README.md:124` / `README.zh-CN.md:125` 写 `fms mcp` 暴露 **5 个**工具（search/show/prompts/stats/doctor），`docs/mcp.md:35-43` 与 CHANGELOG 为 **7 个**（另含 `harnesses`、`latest_session`） | 改为 "seven read-only tools" 或列全 |
| D4 | 中 | `README.md:133-145` / 中文对应表格：`--harness` 漏 `stats`/`resume`，`--cwd`/`--since`/`--include-archived` 漏 `stats`，`--json` 漏 `stats`/`resume`；完全未列 `--explain`/`--timeout`/`--format`/`--no-todos`/`--no-tools`/`prompts --chars`；`fms stats`/`fms resume` 用法行也漏参数 | 按 `cli.py:280-541` 重制两张表 |
| D5 | 中 | `SKILL.md:197` 与 `references/extending.md:95` 写 "`prompts` 列清单要两趟 / CLI counts in one pass and selects a page in a second pass"，但 `service.py:364-394` 三个分支各只遍历一次 `iter_prompts`，CHANGELOG 明确写 "single `iter_prompts` pass"（已 grep 确认两处原文） | 改为 "single pass over `iter_prompts`" |
| D6 | 中 | `SKILL.md:291` 故障排查仍写 "adapter 尚未实现 `iter_prompts`"，与 `AGENTS.md:25` 不变式及实际实现矛盾；`extending.md:154` 写 resume "Claude Code and Codex today"，而 `SKILL.md:155`/CHANGELOG 已列 10 个已验证命令；`extending.md:165` 质量门禁命令写 `core **ui**`（不存在的目录，0.1.1 已改名 `fms_ui`） | 逐条更新为实际行为；`ui` → `fms_ui` |
| D7 | 中 | `references/extending.md:53-70` 把 4 个方法列为 "Required"，但 `base.py` 只有 1 个 `@abstractmethod`，且 `usage_summary`/`resume_argv` 两个可选 hook 未进 contract 表；`.agents/skills/add-harness/SKILL.md:283` 的 per-harness 文档列表漏 `opencode.md`/`gemini-cli.md`/`qwen.md` | 分三栏「抽象方法 / 必须覆盖的契约方法 / 可选 hook」；补齐 3 个引用 |
| D8 | 中 | `SECURITY.md:25-38` 绝对化写 "**no network access** / makes no outbound requests"，但 `cli.py:199-205` `resume --exec` 会启动外部 harness 应用（可写数据/联网）；UI Host 校验/CSP 也未进入 SECURITY | 增加 `## Threat model`：明确 `--exec` 边界、被启动应用不受只读约束、旧 transcript 属不可信输入、UI 防护与无鉴权的现状 |
| D9 | 中 | `docs/compatibility.md`：Legend 要求 Verified 记录版本，但 Kimi/DeepSeek 标 Verified 却写 "app version not recorded"；无统一的 `live`/`synthetic` 证据等级（散落在自由文本）；`docs/scorecard.md:72` 与 `:89`、`:44` 占位符未替换；`docs/competitive-analysis.md` 与 `docs/promotion-plan-0.1.md` 是 2026-11-04 历史快照却未标注，harness 数写 16/18/19 且 release gate 全未勾选 | 增加 Evidence 列并定义 `[live]`/`[synthetic]`；降级缺版本的 Verified；历史文档标注快照日期并归档；替换占位符 |
| D10 | 中 | 示例版本过时：`docs/json-output.md:343`、`references/diagnostics.md:37`、`references/contribution.md:133` 仍写 `0.1.0`（实际 `0.1.3`）；`RELEASING.md:30-31` 写 0.1.1 发布于 2026-11-04，而 `CHANGELOG.md:97` 为 2026-11-03；`RELEASING.md:63,75` 用"首次发布后"的未来时与 `:30` 已发布矛盾 | 统一为 `0.1.3` / `2026-11-03`，或改 `<version>` 占位并注明示例值随版本变化 |
| D11 | 低 | `README.md:166-174` 只索引 `docs/` 8 个文件中的 4 个；中文 README 缺 `docs/json-output.md` 条目、mcp-name 注释为何只在英文版无说明；`CONTRIBUTING.md:105` 写"在 `fms harnesses` 中改状态"（那是命令输出）；`fms_ui/README.md:11` 写 "Node.js 22+" 但 `package.json` 无 `engines` | 增加 docs 索引；补中文条目与注释；改为 `registry.py` 的 READY/PLANNED；补 `engines.node` |

> 注：静态审查中「21 vs 22 harness」的 TOP1 结论已被 WIP diff 修复（见 §1），此处不再列为优先项；D1/D2/D3/D4 仍未修复。

### 2.7 依赖管理、构建与发布

**总体**：运行时零 pip 依赖（`pyproject.toml:40`）、entry points 与包映射有 wheel 测试验证、lockfile 已提交且全链路 `npm ci`、CI 与 release 都重建前端并 diff `fms_ui/static`、SHA256SUMS + `sha256sum -c` + provenance attestation、PyPI Trusted Publishing、绝大多数 action SHA pin。风险集中在**发布链路逻辑**与**依赖来源**。

| 编号 | 严重度 | 证据 | 建议 |
| --- | --- | --- | --- |
| R1 | **高** | `release.yml:7,28-33,160-165` 的 `workflow_dispatch` 同名分支绕过（= S2） | 见 S2 |
| R2 | **高** | `release.yml:167-175` 从 `latest` 下载未校验二进制并持 OIDC 执行（= S3） | 见 S3 |
| R3 | 中高 | `fms_ui/frontend/package-lock.json` 含 **52 处** `https://registry.npmmirror.com/...`（已 grep 确认），与 `registry.npmjs.org` 混用；CI 的 `npm ci` 会按该 URL 从第三方镜像拉包 | 用官方 registry 重建 lock（`npm config set registry` + `npm install --package-lock-only`）并提交；CI 加 `registry-url` 与「lock 中不得出现非官方 registry」检查 |
| R4 | 中 | `package.json:1-28` 无 `engines`/`packageManager`，仓库无 `.nvmrc`，但 jsdom 链要求 Node `>=26` / `^22.22.2`、vitest 要求 `^22.12.0...`，CI/release 固定 `node-version: 22`，`fms_ui/README.md:11` 写 "Node.js 22+"；`@types/node: 26.6.6` 与 Node 22 运行时错配 | 声明 `engines.node >=22.22.2`、`packageManager`、`.nvmrc`；CI 用 `node-version-file` + `--engine-strict`；`@types/node` 降到 22.x |
| R5 | 中 | `pyproject.toml:2` `setuptools>=77.0.3` 仅下限无上界/无 lock；`:42-48` dev extras 已声明（build/coverage/mypy/ruff）但 `ci.yml:12-15,74,92,178,218` 完全不用 `.[dev]`，而是硬编码 `RUFF_VERSION=0.17.3`/`MYPY_VERSION=1.20.2` + 未固定 `pip install build/coverage`；dependabot 只改下限，改不到这些常量 | 收敛到一份 constraints 文件，CI/release 统一 `pip install -e ".[dev]"`；build-system 加上界；让 dependabot 更新 constraints |
| R6 | 中 | `pyproject.toml:61-63` 手写 `packages = [...]`（新增子包会静默漏打包）；`:66` package-data 仅 `static/*` + `static/harness-logos/*` **两层不递归**，而 vite 对非 CSS 资源输出 `static/assets/`；仓库无 `MANIFEST.in`，wheel/sdist 不含 SKILL.md、references、frontend 源码、tools/tests | 改 `packages.find`；package-data 用 `static/**/*`；加「wheel 内 static 文件数 == 仓库」断言；明确 sdist 发行范围（或在 RELEASING.md 写明 skill 文档仅随 ZIP） |
| R7 | 中 | `tools/build_artifacts.py:12` deny-list 过窄 + `copytree(symlinks=False)` 跟随链接（= S13）；`:52-71` `copy2` 保留 mtime、`make_archive` 用当前时间且无排序/`SOURCE_DATE_EPOCH` → 同一 tag 重跑 ZIP 字节不同，配合 `--clobber` 会覆盖已发布资产 | 扩 deny-list 并加 ZIP namelist 断言；用 `zipfile.ZipFile` + 显式 `ZipInfo(date_time)` + `sorted()` + `SOURCE_DATE_EPOCH` 实现可复现构建 |
| R8 | 中 | `release.yml:87-94,139-148` `publish-pypi` 跨 job 下载 whl/sdist 后**未校验 SHA256SUMS**；`:80-85` 先 `rm` 掉构建期生成的 checksum 再重建；`SHA256SUMS.txt` 无 GPG/cosign 签名；`:150-175` `publish-mcp` 在 `publish-pypi` 之后，失败会造成「PyPI 已发布、MCP Registry 未发布」不一致 | 让 checksum 文件随 artifact 传递并在 publish 前 `sha256sum -c`；保留而非删除构建期 checksum；补签名；把 `server.json` 与 mcp-publisher 可用性校验前置到 release job 首步 |
| R9 | 中 | `release.yml` 全文件无 `concurrency`，同 tag 重跑/双 tag 并发会竞态 `--clobber` 与重复 attestation；`publish-mcp` 无 environment 批准与幂等判断；`ci.yml:53,74,92,178,218` `pip install build/coverage` 与 `apt-get install zstd` 无版本固定，与「全部 action SHA pin」标准不一致 | 加 `concurrency`；`publish-mcp` 加 environment 与"已存在则跳过"；`--require-hashes` + 约束文件；CI 加 `pip-audit`/`npm audit`/SBOM（当前 workflows 无任何 audit/SBOM 步骤） |
| R10 | 中 | `release.yml:26,35-78` 只跑 Python 3.14（内置 `compression.zstd`），**发布前从未验证 3.9–3.13 的 zstd CLI 降级路径**，也不跑 ruff/mypy/coverage；`SdistBuildTests` 因 `find_spec("build") is None` 被 skip | release 增加 Python 3.9 + zstd CLI smoke job；`needs` 依赖 CI 全绿；或补齐门禁后再发布 |
| R11 | 中 | 仓库仅一份 MIT LICENSE；`fms_ui/static/app.js` 内含 Vue 3 运行时（`3.5.44`）压缩代码，`harness-logos/` 有 40+ 厂商图标，发布物只附本项目 LICENSE，README 只有商标免责声明 | 增加 `THIRD_PARTY_NOTICES.md`（Vue MIT + 图标来源/许可状态）并随两个 ZIP 与 wheel 分发；对无法确认授权的图标改用中性占位图 |
| R12 | 低 | `.gitignore` 无通用 `node_modules/`、`*.zip`/`*.whl`/`*.tar.gz`、`*.db`/`*.sqlite`/`*.jsonl`、`.screenshots/`（截图可能含敏感信息）；`package.json:25-27` `overrides.minimatch: "^11.0.1"` 是范围而非 pin（lock 解析为 11.0.4） | 补全局忽略规则；`minimatch` 精确 pin；`scorecard.yml:24-29` 缺 SARIF 上传，`pages.yml` 浮动 tag 改 SHA pin 并收窄权限 |

---

## 3. 优先处理清单

### P0 — 立即处理（阻塞发版 / 可直接利用）

| # | 事项 | 落点 | 风险 | 动作 | 工作量 |
| --- | --- | --- | --- | --- | --- |
| P0-1 | **修复测试红灯与真实 home 泄漏** | `tests/cli_support.py:468-472`（WIP）、`pi.py:233`、`tests/test_pi.py` | 641 测试中 11–13 失败；测试读取真实 `~/.pi` 会话，隐私数据进断言/CI 日志；2 个 flaky | 恢复 `FMS_PI_HOME` 映射；`patch.dict(..., clear=True)`；增加"禁止回退真实 home"的隔离测试；同步 `test_session_cache` baseline 与 planned 用例；跑全绿后再考虑发版 | 小（0.5–1 天） |
| P0-2 | **本地 HTTP 面板加鉴权** | `fms_ui/server.py:218-244,275-276` | 本机任意进程一条 curl 读走全部 prompt 全文与绝对路径 | 启动随机 token + 逐请求校验 + `Origin`/`Sec-Fetch-Site` + 精确 Host 匹配；同步 `fms_ui/README.md` 与 `SECURITY.md` | 中（1–2 天） |
| P0-3 | **堵住发布链两处越权** | `release.yml:3-7,28-33,167-175` | 同名分支绕过 tag 校验发布任意 wheel；`latest` 未校验二进制在持 OIDC 凭据的 runner 上执行 | 所有发布 job 加 `github.ref_type == 'tag'`、去 `--clobber`、加 `concurrency`；mcp-publisher 固定 tag + SHA256 校验；OIDC 权限收窄；checkout `persist-credentials: false` | 小（0.5 天） |
| P0-4 | **明确版本边界与 CHANGELOG** | `CHANGELOG.md:7,17-67`、`__init__.py:1`、`server.json` | 已实现并文档化的能力仍标 Unreleased，`0.1.3` 版本语义失真 | 归并条目或 bump 版本；`[Unreleased]` 移到顶部；与 `RELEASING.md:40` 对齐 | 小 |

### P1 — 本迭代（结构性改进，收益最大）

| # | 事项 | 落点 | 预期收益 |
| --- | --- | --- | --- |
| P1-1 | 收敛 service 边界与 adapter 契约 | `service.py:294,424-425`、`base.py:11-34`、`cli.py:177-179`、`server.py:169-175` | 消除 CLI/MCP/UI 三种 detail JSON 形状；契约可被静态检查与契约测试强制 |
| P1-2 | 建立 `Limits`/`Defaults`/版本化 schema 单一来源 | 18 个 adapter 常量、`render.py:145 vs :258`、`cli.py:353-477`、`mcp.py:113`、`server.py:131-183` | 消除同操作不同默认值；行为可预期 |
| P1-3 | 性能三件套：持久化摘要索引 + 过滤下推 + zstd 解码缓存 | `service.py:33-56,141-143`、`registry.py:118-120`、`codex.py:142-155`、`deepseek.py:108-121` | 冷查询 10–100×；`latest --limit 1` 不再读全部历史；压缩 store 少 3–4 次全量解压 |
| P1-4 | 加资源边界 | `codex.py:158-226`、`deepseek.py:124-160`、`util.py:214-223`、`server.py:131-142,263-276`、`mcp.py:186-254` | 防解压炸弹/单请求 DoS；深搜有超时；ref 参数有上限 |
| P1-5 | 默认隐私最小化 + 输出净化 | `models.py:66-85`、`render.py`、`cli.py:515-525`、`util.py:90-110`、`service.py:299-301` | prompt 默认截断 + `--full` opt-in；`--redact`；过滤 ANSI/bidi；错误脱敏 |
| P1-6 | 依赖与供应链净化 | `package-lock.json`（52 镜像 URL）、`package.json`、`pyproject.toml:2,42-48`、`ci.yml`、`pages.yml`、`build_artifacts.py:12,52-71` | 依赖来源可信、Node 版本锁定、可复现 ZIP、第三方许可合规 |
| P1-7 | 文档按 `cli.py` 重制 + SKILL.md 补 MCP | `SKILL.md`、`README.md:124-145`、`add-harness/SKILL.md:26-39`、`extending.md:95,154,165`、`SECURITY.md` | agent 能发现 MCP；选项表准确；威胁模型完整；不再违反 AGENTS.md 不变式 |
| P1-8 | 测试质量：修弱断言、补核心库单测与负输入矩阵、前端 lint/coverage/E2E、Windows 真门禁、branch coverage | `test_cli.py:958-985,46-49`、`test_json_contract.py`、`ci.yml:189,220-224`、`package.json:6-11` | 641 个测试从"数量可信"变"质量可信" |

### P2 — 后续（规模到位后再做）

- 抽 `sqlite_adapter.py` / `prompt_utils.py` 消除 17+9+6 份重复 helper；拆分 900 行级大类。
- adapter 无状态化 + 缓存集中到 `ScanContext`，消除单例并发竞争与 flaky 根因。
- `pkgutil` 自动发现 + 声明式 `HARNESS_META`，由元数据生成文档/契约清单。
- 传输层优化：hash + `immutable` 静态资源、ETag/304、gzip、列表 DTO 裁剪、`/api/projects` limit。
- 前端虚拟滚动、Intl 单例、debounce、POLL_ATTEMPTS 收敛。
- 历史文档归档、Evidence 证据列、`THIRD_PARTY_NOTICES.md`、SBOM/cosign 签名。

---

## 4. 建议实施顺序

1. **第 1 批（1 周内，止血）**：P0-1 → P0-4 → P0-3 → P0-2。先把仓库恢复到"测试全绿、发布链可信、面板有鉴权"的可发布状态；顺手把 `AGENTS.md` 的「Run before finishing」补上 ruff/mypy/coverage。
2. **第 2 批（1–2 个迭代，减债）**：P1-2 → P1-1 → P1-3 → P1-4。先统一常量/默认值（低风险、收益立竿见影），再收边界，再做索引与缓存；每一步配契约/回归测试。
3. **第 3 批（持续）**：P1-5 ~ P1-8 与 P2 项按用户反馈驱动推进；新增 harness 时同步执行 `AGENTS.md` 与 `add-harness/SKILL.md` 的检查清单，避免再次出现 WIP 式遗漏。

---

## 5. 明确应保留的强项（避免改造时误伤）

- 运行时零 pip 依赖、`sqlite mode=ro` 只读打开、全部 subprocess 用 argv、无 `eval`/`pickle`/`shell=True`、Vue 端无 `v-html`。
- `util.py:163-211` 的 head/tail 限界读取与 `test_performance.py` 的有界读/线性预算回归；`fingerprint.py:87-118` 的 `read(cap)+kill` 是解压上限的正确样板。
- `session_cache.py` 的 single-flight + stale-while-revalidate；前端仅提交触发搜索 + `AbortController`。
- 绑定 `127.0.0.1`、Host 白名单、静态资源白名单、CSP 等一整套安全响应头。
- 22 个 adapter 均有测试文件、fixtures 全合成、`python 3.9–3.14` CI 矩阵、`npm ci` + static 漂移检查、SHA256 + provenance + Trusted Publishing、绝大多数 action SHA pin。
- 版本单一来源（`__version__` → dynamic → `server.json` 双重校验）、中英 README 同步、文档覆盖面广且无死链。

---

## 6. 审查局限

- 未运行 `python3 tools/build_artifacts.py`（会产生 `dist/` 产物）与 `npm run build`（会改写 tracked static），因此「可复现构建」「产物漂移」为静态推断；`.pyc` 跟踪情况已用 `git ls-files` 确证为 0。
- 未对真实 harness store 做端到端实测，`docs/compatibility.md` 的 live/verified 声明仅做一致性核对，未复核其真实性。
- 安全项中的「可直接利用」基于本机威胁模型与 CI 权限模型的代码推导，未做实际渗透或发版演练。
- 工作区含未提交 WIP，部分静态结论（harness 数量、矩阵行数）已被 WIP 修复，报告中已单独标注。
