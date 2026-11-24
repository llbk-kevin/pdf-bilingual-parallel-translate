# 技能维护

## 仓库与安装

在 llbk-kevin/pdf-bilingual-parallel-translate 的 main 分支维护技能。安装入口为 <CODEX_HOME>/skills/pdf-bilingual-parallel-translate。由 CC Switch 托管时，先解析链接，在实际目录修改，再核对链接类型、目标和入口内容。未托管的普通目录直接维护。发现断链或独立副本分歧时先报告。

## 验证与提交

同步 SKILL.md、README.md 以及被修改的中英文配对参考，保持命令、字段和示例等价。文本使用 UTF-8 无 BOM。检查 Markdown 链接和 agents/openai.yaml，并在可用时运行 skill-creator 校验器。

在合适的环境安装 requirements-dev.txt，从仓库运行：

~~~text
python -m unittest discover -s tests -v
python scripts/pipeline.py --help
python scripts/pdf_tools.py --help
~~~

测试用代码生成 PDF 和字体。行为变更运行相关回归。修改坐标时检查页尺寸及左侧原文隔离，修改资源时检查编码图片和蒙版，修改流程时检查审核复用及发布路径。如需可视样例，运行 tests/generate_layout_samples.py --out <仓库外目录> --font <允许使用的中文字体>。字体集合可用 --face-index 选面。

用户原文、译本、渲染图、恢复文件、字体和凭据留在仓库之外。按 AGENTS.md 规范提交并正常推送 origin/main。

## 实现约束

修改集群调度时，测试完整/分包页归属、独立复核身份、显式模型请求与真实证据分类、原代理多次续作，以及重任务排队时轻量工作继续。静态模型列表不是能力测试。从新版入口做小型独立试用，确认表、派工台账和检查点留在仓库外。唯一代理ID、续作次数和并发活动分别统计。

修改工具生命周期时，测试成功、失败、取消、监督进程异常退出、PID重用、有界日志传输及UTF-8路径。用隔离父进程反复运行合成大状态查询和作业，记录起点、峰值、结束内存及预热后增长。实际宿主重置须核对已登记PID/启动时间身份消失；不支持或无法验证的清理明确标记。宿主进程详情和任务实测数据留在仓库之外。

- 压缩非图片流，保留原图片编码。审计遍历可达资源，检查图片编码流及显示语义。升级 pypdf 大版本时复核编码流清点。
- 在 PDFium 内存渲染副本中规范化 UserUnit，两侧比较使用相同矩阵和像素原点。
- 使用源文字绘制 trace 和 fontTools 译文字形轮廓判断删除范围及碰撞边界。字体序列化关闭时间戳重算，保证重复构建稳定。
- 读取原始 PDF 目标数组，保留 XYZ 的空坐标。几何和交互细节见 [inplace.zh-CN.md](inplace.zh-CN.md)。

调整批量绘制、PDF 序列化或工作进程数时，使用同一输入比较。记录各阶段墙钟与 CPU 耗时、峰值工作集、状态字节数、对象数及渲染页数。改变默认值前核对像素、字体、导航和共享资源。构建作业及流水线事件记录提供时间与范围。性能对比使用独立状态副本，完整大文档另安排维护验证。

准备或冻结行为变更时，覆盖跨盘引用、状态提交前失败回滚、输入保护和新版本分包交接；验证协调事件重放与模型身份，保留有效的局部审核复用。发现具体缺陷时补充针对性回归。单次任务的验证记录留在任务目录。

行为变更时同时查阅相关旧规则、调用方与测试，在原位置更新冲突处。维护当前流程与状态合同，删除过时适配和重复入口。具体尚未处理的问题留在本地维护报告。

## 协作记录合同


派工前及分工变化后运行 `python scripts/coordination.py validate-plan --plan TASK/work/coordination.json`。入口只读，返回ok/errors、模型核对和摘要；无效计划退出1。检查结构，不证明用户授权、模型可用或语义质量。

- documents：id、选定物理页的正整数列表pages、指向翻译/修复任务的state_writer。分包拥有编辑权时，写入者可设owns_edits=false。
- tasks：唯一id与展示名name、document、pages、phase（translate/review/repair）、明确owns_edits、model、reasoning_effort、fork_turns、responsibilities（字符串）、handoff、depends_on任务ID及status（queued/running/completed/blocked）。首次翻译和复核须fork_turns='none'。只读上下文页不算编辑归属。译者和复核须覆盖全部选页，当前编辑归属不可重叠。原归属完成或转交后才能交给修复任务。复核的依赖链须包含相关译者。
- tasks可记agent_id、artifacts、resource_class、estimated_memory_bytes及resume_count（默认0）。续同一代理时增加resume_count，不重复登记launch。
- launches追加记录：task、唯一实际agent_id、requested_model、requested_effort及可选actual_model/actual_effort、宿主/工具evidence与evidence_agent_id。未生成agent_id的失败调用留作诊断，不算launch。请求不能替换已确认模型；错误或不匹配阻断检查。只有evidence_agent_id与本次agent_id一致且证据指向该代理的宿主/工具记录，实际值才verified；缺证据或仅有探针证据为unverified。model_checks保存探针对象：已创建的agent_id、宿主/账号作用域及可用性结果。

短篇两页PDF用一个拥有[1,2]的translate任务和一个依赖它的review任务，state_writer指向translate。分包时，负责合入的translate任务可依赖各页段，再让复核依赖它。排队/运行中的复核也须依赖重叠页的未完成修复；反馈是产物，不把修复反向依赖同一复核任务造成环。复核者交观察给写入者串行登记。同一代理不能翻译/修复又独立复核该文档，包括历史launch身份。新复核者只收原文、渲染、标准和空模板，不收译者结论。

摘要区分created_agents（工作代理与已登记探针的唯一合计）、work_agents、probe_agents、当前运行工作代理ID、排队/阻断任务和resume_count合计；按记录身份统计，不从调用数、进程数或界面总数猜测。累计数不能称为并发峰值。

每份文档状态同一时刻由一个写入者负责，不同文档可以并行更新。复核者提交真实观察，由指定的文档写入者登记并导入页段结果。主代理负责整体决策与发布。

通过 coordination record --plan TASK/work/coordination.json --event FILE 登记 launch、resume、status、model-evidence。事件带唯一 id、type、task。launch 提供 agent_id/requested_model/requested_effort；resume 提供原 agent_id；status 提供 status 及可选 artifacts 对象；model-evidence 提供 agent_id 和可取得的 actual_model/actual_effort/evidence/evidence_agent_id。主代理串行登记。同一事件重放不重复累计；相同 id 的不同内容被拒绝。无效更新不改台账。能取得时保存对应代理的宿主证据，不借用其他代理的探针。
