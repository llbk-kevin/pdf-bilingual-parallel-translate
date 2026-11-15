# 集群翻译与独立复核

## 派工与宿主设置

每份 PDF 都建立翻译任务和使用全新上下文的独立复核任务，包括单份短文档。主代理沿用当前会话模型。翻译和复核建议 Luna xhigh，用户选择和实际可用模型优先。采用建议模型时，在派工参数中显式指定 model 和 reasoning_effort，并对独立复核使用 fork_turns=none；记录实际派工值。长文档按章节、完整语义及工作量增加任务，每个源页有一个当前编辑归属。

通过实际子代理工具检查能力，用 scripts/coordination.py --config <CODEX_HOME>/config.toml 只读查看宿主设置。未配置 agents.max_concurrent_threads_per_session 时使用宿主默认值。首次使用且没有显式设置，或容量影响派工时，说明当前情况并询问是否调整到具体值。决定写入 work/coordination.json，等待这个可选决定时可按现有容量处理队列。用户批准精确值后才写配置。修改后保存检查点，提醒用户完整退出并重新启动 Codex，重启后核对工具实际能力。配置值本身不能证明当前有效容量。

先按[命名流程](naming.zh-CN.md)处理，再 prepare 和派工。交接确认路径、冻结 command_prefix/runner、页归属和简洁清单，相邻页作为只读上下文。跨页续句和续表交给同一任务理解，再分别放回原页。

## 动态调度

按可用槽位派发当前可执行任务，翻译和复核数量动态变化。候选通过机器检查后复核就绪，其他 PDF 可以继续翻译。槽位满时保存队列，等待完成或可用事件。保存交接后，通过宿主支持的操作释放已完成代理。使用有界等待，可用情况变化后再尝试创建。用户指定的阶段顺序优先。

work/coordination.json 保存任务 ID、文档、页段、phase（translate/review）、status（queued/running/completed/blocked）、depends_on、实际代理 ID 和产物路径。ready_tasks(tasks, available_slots) 选择依赖已满足的任务，优先处理就绪复核，不预留固定角色槽位。创建和等待通过宿主工具执行。复核者在全新上下文接收原文、候选渲染、验收要求及空白观察模板。

每份文档状态同一时刻由一个写入者负责，不同文档可以并行更新。复核者提交真实观察，由指定的文档写入者登记并合入补丁。主代理负责整体决策与发布。

## 分包与恢复

通过 pipeline package --state recovery/state.json --pages RANGE --out work/packages/PACKAGE --owner AGENT_ID 导出连贯页段。每包包含编辑状态、简洁清单、基线及只读相邻页。译者保存 edits.json，在包内应用和预览。文档写入者带配对清单合入补丁，相同补丁指纹可重放；基线冲突只退回受影响页。

使用 status 汇总活跃包和候选进度，将代理 ID、已提交路径、未完成页及阻断写入磁盘。原代理可用时续跑，或由新代理根据检查点接剩余任务。审核复用要求页面证据和依赖匹配。

使用 verify 的 review_handoff 和 observations_template，修复阻断前先登记通过页，再通过 --previous-state 复用有效证据。汇报实际阶段变化和阻断。构建读取原文与保存状态，产物保存在同名工作目录。

本地提取和渲染使用 --workers auto 或正整数，同机 CPU/内存租约协调并行 PDF 作业，资源遥测记录实际进程数及选择理由。最终 PDF 由单一写入者生成。
