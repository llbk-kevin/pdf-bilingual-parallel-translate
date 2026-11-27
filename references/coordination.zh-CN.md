# 主代理协调流程

## 确认与准备

主代理按[命名规则](naming.zh-CN.md)在首次出计划或请用户确认前查证官网版本和中文版。将查询结果和原文选项与精确命名表、代理工作表一起展示。工作表包含稳定任务名、文档／物理页、翻译／复核／写入职责、模型与强度、新上下文、依赖及交接位置。接受计划即确认两张表，明确选定的原文按用户决定执行，续跑不重复询问。每份需翻译的 PDF 有一个当前状态写入者和独立复核覆盖；写入者可以翻译，不额外设置纯传话代理。

主代理使用当前会话模型。建议 Luna xhigh，以用户选择为准，明确传入 model='gpt-6-luna'、reasoning_effort='xhigh'、fork_turns='none'。同一宿主／账号做一次最小可用性探针后复用结果；静态列表缺项表示未核实，不能据此判定不可用。记录请求参数及能取得的宿主证据，实际模型元数据缺失标为未核实，不增加等待门槛。实际失败或不匹配时保存队列，替换模型前询问。

通过 scripts/coordination.py --config <CODEX_HOME>/config.toml 读取宿主容量。首次未设置或明显影响任务时，询问是否修改为具体值；等待时可按现有槽位排队。只改已批准设置，保存恢复点，提醒完整退出并重启 Codex，重启后核对工具能力。

完成批准的改名及原文哈希核对后：

~~~text
python scripts/pipeline.py prepare --source SOURCE.pdf --state TASK/recovery/state.json --font CHINESE_FONT
~~~

prepare 先检查页面内容流和嵌套图形，再提取字形。触及已知解析 token 上限时，仅对该流按限定预算重试一次。仍失败时，查看报告中的原文物理页、对象路径和所触发的限制。

按返回动作和产物路径操作。查看原文渲染，依据正文密度、表格、公式和跨页语义分配页段。跨页句子／续表交同一负责人，相邻页作为只读上下文。明确图内标签和参考文献范围：题名及说明翻译，作者、期刊、标准号、网址和年份保留。布局方法先在代表页预览，再批量推广。

## 派工与合入

译者只收到入口、practical.md、确认后的原文／状态及生成材料；复核者收到入口、review.md 和生成的交接材料，不接收译者通过结论。work/coordination.json 保存实际代理 ID、职责、阶段及检查点。沿用 coordination.py validate-plan 检查现有台账，字段见[维护说明](maintenance.zh-CN.md#协作记录合同)。

分包文档使用：

~~~text
pipeline package --state AUTHOR_STATE --pages RANGE --out TASK/work/packages/NAME --owner TASK_NAME
pipeline import-package --state AUTHOR_STATE --package PACKAGE_A --package PACKAGE_B
~~~

采用返回的命令数组。译者交付当前分包状态，另附问题说明。将已就绪的包一次导入。命令逐包核对原文、分配页、源事实和主状态基线，然后合并，只检查和保存一次主状态。出现冲突时列出包名和受影响页，整批不写入。重复导入相同结果时保留原状态。

从当前主状态重新导出冲突页，由原译者续修。写入者维护共享术语，另行汇总交付备注。不同文档可以并行写入，同一状态只能有一个写入者。

动态派发就绪工作，不设固定代理数或角色配额。一份候选就绪即可复核，其他文档继续翻译。槽位满时保存队列，等待完成事件或有界等待。修复／复查优先原代理，仅为独立工作或原代理不可恢复时增派。累计创建数、当前运行数和续作次数分别报告。

系统余量默认 max(2 GiB, 物理内存的10%)；work/resource-settings.json 可覆盖 memory_reserve_bytes，或明确设置 memory_checks_enabled=false。用户任务指令优先。内存不足只让新增重任务排队，轻量编辑及已有渲染查看仍可继续；Python worker 准入单独计算。持久内核／后台作业才读取[工具运行说明](tool-runtime.zh-CN.md)。

## 核验、发布与恢复

译者完成局部预览后，构建并核验完整交付候选，安排独立逐页复核。多人复核时，在 verify 中重复传入 `--review-pages`，为每人分配互不重复且合计覆盖待复核页的物理页段。按 review_handoff 提供各自路径及原文页到候选页的对应关系，再用生成的 review 命令一起登记。修复实质问题后，verify 用 `--previous-state` 指定旧候选，只安排仍需复查的页。局部预览不能发布。

只有返回可发布动作后才发布。交付备注写入 `work/delivery-notes.json`，每条填写 `description`、`status`（`open`、`resolved` 或 `retained`），保留项填写 `note`。确认修复结果后才关闭实质问题，仍标为 open 的问题阻止发布。只改备注时沿用同一候选和复核记录，按更新后的备注发布。成品放在原文旁；发布核对依赖并保存作者快照以供按需恢复。

重启后读取记录的路径和代理 ID，检查运行中作业，再续跑。不要按文件时间猜测最新状态。技能变更由主代理使用新版 pipeline refreeze --state AUTHOR_STATE --out NEW_RECOVERY_DIR，不原地改活跃冻结脚本；重新导出受影响分包。主代理定位修复技能缺陷，译者提供证据。旧候选及其观察保持原样。
