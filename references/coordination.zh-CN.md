# 集群翻译与独立复核

## 派工与宿主设置

每份 PDF 都建立翻译任务和使用全新上下文的独立复核任务，包括单份短文档。主代理沿用当前会话模型。翻译和复核建议 Luna xhigh，用户选择和实际可用模型优先。采用建议模型时，在派工参数中显式指定 model 和 reasoning_effort，并对独立复核使用 fork_turns=none；记录实际派工值。长文档按章节、完整语义及工作量增加任务，每个源页有一个当前编辑归属。

通过实际子代理工具检查能力，用 scripts/coordination.py --config <CODEX_HOME>/config.toml 只读查看宿主设置。未配置 agents.max_concurrent_threads_per_session 时使用宿主默认值。首次使用且没有显式设置，或容量影响派工时，说明当前情况并询问是否调整到具体值。决定写入 work/coordination.json，等待这个可选决定时可按现有容量处理队列。用户批准精确值后才写配置。修改后保存检查点，提醒用户完整退出并重新启动 Codex，重启后核对工具实际能力。配置值本身不能证明当前有效容量。

先按[命名流程](naming.zh-CN.md)处理，再 prepare 和派工。交接确认路径、冻结 command_prefix/runner、页归属和简洁清单，相邻页作为只读上下文。跨页续句和续表交给同一任务理解，再分别放回原页。

## 动态调度

按可用槽位和内存派发当前可执行任务，翻译和复核数量动态变化。候选通过机器检查后复核就绪，其他 PDF 可以继续翻译。槽位或内存不足时保存队列，等待完成或可用情况变化。按下述步骤完成会话清理后，才认定闲置工作者已释放。使用有界等待，可用情况变化后再尝试创建。用户指定的阶段顺序优先。

work/coordination.json 保存任务 ID、文档、页段、phase（translate/review）、status（queued/running/completed/blocked）、depends_on、实际代理 ID 和产物路径。ready_tasks(tasks, available_slots, memory=None, reserve_bytes=None) 选择依赖已满足的任务，优先处理就绪复核，不预留固定角色槽位。系统余量默认 max(2 GiB, 物理内存的20%)；任务 work/resource-settings.json 中的 memory_reserve_bytes 可覆盖，调用 ready_tasks 时须传入该覆盖值。每项任务可给 estimated_memory_bytes，未实测时默认256 MiB；记录实际占用以改进后续估算。创建和等待通过宿主工具执行。复核者在全新上下文接收原文、候选渲染、验收要求及空白观察模板。

每份文档状态同一时刻由一个写入者负责，不同文档可以并行更新。复核者提交真实观察，由指定的文档写入者登记并合入补丁。主代理负责整体决策与发布。

## 分包与恢复

通过 pipeline package --state recovery/state.json --pages RANGE --out work/packages/PACKAGE --owner AGENT_ID 导出连贯页段。每包包含编辑状态、简洁清单、基线及只读相邻页。译者保存 edits.json，在包内应用和预览。文档写入者带配对清单合入补丁，相同补丁指纹可重放；基线冲突只退回受影响页。

使用 status 汇总活跃包和候选进度，将代理 ID、已提交路径、未完成页及阻断写入磁盘。原代理可用时续跑，或由新代理根据检查点接剩余任务。审核复用要求页面证据和依赖匹配。

使用 verify 的 review_handoff 和 observations_template，修复阻断前先登记通过页，再通过 --previous-state 复用有效证据。汇报实际阶段变化和阻断。构建读取原文与保存状态，产物保存在同名工作目录。

本地提取和渲染使用 --workers auto 或正整数，同机 CPU/内存租约协调并行 PDF 作业，资源遥测记录实际进程数及选择理由。最终 PDF 由单一写入者生成。

## 工具会话归属与清理

派发新一批重任务前运行 scripts/coordination.py memory --task-dir TASK；阶段切换或资源失败后再检查，不连续轮询。内存不足时让新重任务排队，现有作业继续完成。worker准入失败会报告可用量、预留量、估算需求与协调进程RSS，重试前先读这些事实。

工作者从自己的 Node 内核直接启动冻结 Python，执行 scripts/coordination.py session-register --task-dir TASK --agent ACTUAL_ID。脚本核实调用者父进程链中的 kernel.js 和 session ID，在 work/tool-sessions/ 保存PID、启动时间、代理及内存。无法验证时明确报告，不猜测归属。

交接前依次：在任务内保存编辑、观察及恢复检查点；确认存活子作业均已由 task_runtime 登记；执行 session-mark --record RECORD --status cleanup_required --checkpoint FILE；宿主支持时调用该工作者自己的 js_reset。不要为宣布完成又立即启动Node，续跑从磁盘恢复到新内核。不支持重置时标 cleanup_unavailable 并报告；只有宿主确实提供关闭代理操作时才使用。

主代理运行 sessions --task-dir TASK，核对已记录的PID/启动时间身份是否消失；只有原先 cleanup_required 的会话才标 reset_observed。代理完成、中断或关闭标签本身不是清理证据。未知内核单独列出，绝不按名称、大小或猜测工作目录终止。重置内核前确认没有未托管作业；只用 task_runtime cancel 取消其身份核验通过的作业树。宿主无法释放已确认闲置会话时，才把完整重启应用作为最后手段。
