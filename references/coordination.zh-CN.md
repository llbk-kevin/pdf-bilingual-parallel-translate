# 集群翻译与独立复核

## 派工与宿主设置

每份 PDF 都安排翻译和全新上下文的独立复核，短文档也适用。主代理沿用当前会话模型。建议 Luna xhigh，以用户选择为准；确认采用时显式传 model='gpt-6-luna'、reasoning_effort='xhigh'、fork_turns='none'。首次页段译者也用新上下文和精简任务包，不继承协调讨论；修复优先让原代理从检查点续作。

首次命名确认或执行计划中，在精确名称表旁展示代理工作表：稳定名称、文档/物理页、翻译/复核/合入职责、模型与强度、上下文方式、依赖及交接位置。每份文档指定一个状态写入者；译者可负责合入，不另设纯传话统筹。首轮分界可暂定、预检后调整。正式派工前按正文密度、表格、公式和跨页语义分包，不只平均页数。单一状态写入者可以合入多个页段负责人的补丁，不代表只能有一个译者。例如任务ID d02_translate_p001_018，展示“D02 手册｜翻译001–018”。续跑沿用名称，不每轮新建fix/finish/resume代理。

正式派工前对目标模型做一个最小非PDF探针，同一宿主/账号/模型/强度复用可用性证据。静态目录缺项表示未验证，不代表不可用。逐个实际代理保存请求参数和可取得的宿主/工具证据；探针与代理自述都不能证明另一个工作代理的实际模型。无法观察该代理的实际模型/强度时，不臆填实际值，标为未核实。真实错误或不匹配时保存队列、先询问替代模型，不静默继承或替换。宿主/账号变化或实际报错后再验证可用性，不逐页重复探针。

可用性探针成功后，仅缺逐代理元数据不阻断按明确已确认参数工作；不要为每个工作者再加启动探针或等待协调者确认的关卡。记录可取得的身份绑定证据，不额外发明强制阶段。

通过实际子代理工具检查能力，用 scripts/coordination.py --config <CODEX_HOME>/config.toml 只读查看宿主设置。未配置 agents.max_concurrent_threads_per_session 时使用宿主默认值。首次使用且没有显式设置，或容量影响派工时，说明当前情况并询问是否调整到具体值。决定写入 work/coordination.json，等待这个可选决定时可按现有容量处理队列。用户批准精确值后才写配置。修改后保存检查点，提醒用户完整退出并重新启动 Codex，重启后核对工具实际能力。配置值本身不能证明当前有效容量。

先按[命名流程](naming.zh-CN.md)确认两张表，再 prepare 和正式派工。续跑沿用记录。主代理可动态调整页界和增加有依据的并行任务，登记并汇报原因；未批准的模型/名称/目标位置变更须确认。文档负责人向主代理提出增派，不脱离台账自行扩散。交接确认路径、冻结command_prefix/runner、页归属、精简清单，以及启动时明确传入的请求模型/强度/上下文参数。区分主代理已知的请求参数与工作者无法观察的实际运行元数据。相邻页只读；跨页续句和续表一起理解，再分别放回原页。

prepare 后首轮分包同时交代代表版式检查。交接区分初始合并补丁与使用当前 ID 的增量编辑。主代理负责技能缺陷定位、修复方案和共享代码修改；试用代理只操作流程、提交证据。主代理按实际诊断类别提出修复；覆盖区与原生保留文字相交不是有效的绕过方式。环境检查成功后使用冻结的 UTF-8 命令前缀。

## 动态调度

按实际槽位和内存动态派工，不固定代理数量或角色配额。候选通过机器检查后复核就绪。修复优先续原译者，复查优先续原复核者；独立并行工作、原代理不可恢复或需要不同专业判断时才增派。保存排队工作并有界等待；补丁/候选就绪或出现阻断时立即交接，使用生成材料，避免多个代理反复传递同一无变化状态。现有作业可完成，低内存只排队新重任务，不冻结轻量编辑和查看已有渲染。汇报实际变化，不循环重复无变化等待。回复结束不代表代理队列会自动继续。用户指定的阶段顺序和资源指令优先。

work/coordination.json 按下述合同保存已确认工作表与派工历史。ready_tasks(tasks, available_slots, memory=None, reserve_bytes=None, check_memory=True) 优先处理就绪复核，不预留角色槽位。系统余量默认 max(2 GiB, 物理内存10%)。任务work/resource-settings.json可用memory_reserve_bytes覆盖；memory_checks_enabled=false记录用户明确的任务覆盖。调用ready_tasks时以reserve_bytes和check_memory传入。resource_class='light'允许真实轻量工作在重任务等待时继续，缺省为heavy。estimated_memory_bytes未实测时默认256 MiB。系统预留与本轮未改的Python worker租约/估算算法不同。创建和等待由宿主工具完成。

## 工作表合同与检查

派工前及分工变化后运行 `python scripts/coordination.py validate-plan --plan TASK/work/coordination.json`。入口只读，返回ok/errors、模型核对和摘要；无效计划退出1。检查结构，不证明用户授权、模型可用或语义质量。

- documents：id、选定物理页的正整数列表pages、指向翻译/修复任务的state_writer。分包拥有编辑权时，写入者可设owns_edits=false。
- tasks：唯一id与展示名name、document、pages、phase（translate/review/repair）、明确owns_edits、model、reasoning_effort、fork_turns、responsibilities、handoff、depends_on任务ID及status（queued/running/completed/blocked）。首次翻译和复核须fork_turns='none'。只读上下文页不算编辑归属。译者和复核须覆盖全部选页，当前编辑归属不可重叠。原归属完成或转交后才能交给修复任务。复核的依赖链须包含相关译者。
- tasks可记agent_id、artifacts、resource_class、estimated_memory_bytes及resume_count（默认0）。续同一代理时增加resume_count，不重复登记launch。
- launches追加记录：task、唯一实际agent_id、requested_model、requested_effort及可选actual_model/actual_effort、宿主/工具evidence与evidence_agent_id。未生成agent_id的失败调用留作诊断，不算launch。请求不能替换已确认模型；错误或不匹配阻断检查。只有evidence_agent_id与本次agent_id一致且证据指向该代理的宿主/工具记录，实际值才verified；缺证据或仅有探针证据为unverified。model_checks保存探针对象：已创建的agent_id、宿主/账号作用域及可用性结果。

短篇两页PDF用一个拥有[1,2]的translate任务和一个依赖它的review任务，state_writer指向translate。分包时，负责合入的translate任务可依赖各页段，再让复核依赖它。排队/运行中的复核也须依赖重叠页的未完成修复；反馈是产物，不把修复反向依赖同一复核任务造成环。复核者交观察给写入者串行登记。同一代理不能翻译/修复又独立复核该文档，包括历史launch身份。新复核者只收原文、渲染、标准和空模板，不收译者结论。

摘要区分created_agents（工作代理与已登记探针的唯一合计）、work_agents、probe_agents、当前运行工作代理ID、排队/阻断任务和resume_count合计；按记录身份统计，不从调用数、进程数或界面总数猜测。累计数不能称为并发峰值。

每份文档状态同一时刻由一个写入者负责，不同文档可以并行更新。复核者提交真实观察，由指定的文档写入者登记并合入补丁。主代理负责整体决策与发布。

通过 coordination record --plan TASK/work/coordination.json --event FILE 登记 launch、resume、status、model-evidence。事件带唯一 id、type、task。launch 提供 agent_id/requested_model/requested_effort；resume 提供原 agent_id；status 提供 status 及可选 artifacts 对象；model-evidence 提供 agent_id 和可取得的 actual_model/actual_effort/evidence/evidence_agent_id。主代理串行登记。同一事件重放不重复累计；相同 id 的不同内容被拒绝。无效更新不改台账。能取得时保存对应代理的宿主证据，不借用其他代理的探针。

## 分包与恢复

派工前，用 prepare 的 source_render_argv 和冻结环境完成一次渲染冒烟。prepare/package/refreeze 的 commands 数组包含精确路径，直接交给子进程 API，不拼成 shell 字符串。

通过 pipeline package --state recovery/state.json --pages RANGE --out work/packages/PACKAGE --owner AGENT_ID 导出连贯页段。每包包含编辑状态、简洁清单、基线及只读相邻页。译者保存 edits.json，在包内应用和预览。文档写入者带配对清单合入补丁，相同补丁指纹可重放；基线冲突只退回受影响页。

不要原地修改正在使用的冻结脚本。需要修代码时，用修订版 pipeline refreeze --state AUTHORING_STATE --out NEW_RECOVERY_DIR，保留作者内容并建立新入口；旧候选与证据留在原版本。受影响分包从新状态重导，原补丁按新 manifest 验证；真实基线冲突退回，不改指纹绕过。无关工作按已分配版本继续到交接。

使用 status 汇总活跃包和候选进度，将代理 ID、已提交路径、未完成页及阻断写入磁盘。原代理可用时续跑，或由新代理根据检查点接剩余任务。审核复用要求页面证据和依赖匹配。

直接使用verify已有的review_handoff和observations_template，不手工重做交接包。先登记通过页，再用--previous-state复用。交接只需路径、阻断/保留事项和下一步；计数由脚本/台账提供，不手写第二份统计。普通交付到ready的publish即完成，脚本已核对恢复依赖；执行recovery_argv是另一次重建，不是必做冒烟。仅改调度的维护试用同样遵循，除非明确安排重建。构建读取原文及状态，产物留在同名目录。

本地提取和渲染使用 --workers auto 或正整数，同机 CPU/内存租约协调并行 PDF 作业，资源遥测记录实际进程数及选择理由。最终 PDF 由单一写入者生成。

## 工具会话归属与清理

派发新一批重任务前运行 scripts/coordination.py memory --task-dir TASK；阶段切换或资源失败后再检查，不连续轮询。内存不足时让新重任务排队，现有作业继续完成。worker准入失败会报告可用量、预留量、估算需求与协调进程RSS，重试前先读这些事实。

prepare前以已检查的Python环境执行仓库协调命令；prepare后，验证、内存及会话命令也使用返回的command_prefix与recovery/coordination.py，普通系统Python可能缺少冻结依赖。工作者从自己的Node内核直接启动 `COMMAND_PREFIX recovery/coordination.py session-register --task-dir TASK --agent ACTUAL_ID`。脚本核实调用者父进程链中的kernel.js与session ID，在work/tool-sessions/保存PID、启动时间、代理及内存。无法验证时明确报告，不猜测归属。

交接前保存编辑、观察与恢复检查点，确认存活子作业均由task_runtime登记；执行session-mark --record RECORD --status cleanup_required --checkpoint FILE，再在支持时调用自己的js_reset。保留session-register返回的当前内核精确记录路径，不按目录排序或其他代理的“最新文件”选择；重置后按需登记新内核。不要为宣布完成重启Node。不支持重置时标cleanup_unavailable并报告；宿主确有关闭代理操作时才使用。

最终交接时登记完成、产物和可取得的模型证据，运行 sessions，将已观察重置/无法核验结果留在检查点。主代理运行 sessions --task-dir TASK，核对已记录的PID/启动时间身份是否消失；只有原先 cleanup_required 的会话才标 reset_observed。代理完成、中断或关闭标签本身不是清理证据。未知内核单独列出，绝不按名称、大小或猜测工作目录终止。重置内核前确认没有未托管作业；只用 task_runtime cancel 取消其身份核验通过的作业树。宿主无法释放已确认闲置会话时，才把完整重启应用作为最后手段。
