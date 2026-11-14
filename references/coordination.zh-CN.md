# 集群翻译与独立复核

## 派工

单份 PDF 少于 80 个物理源页时用直接流程。多份 PDF、单份达到 80 页或明确要求独立复核时，使用主代理协调。主代理推荐 GPT-6.1 Terra high，用户也可选 Sol 或 Astra。翻译、复核分别使用全新上下文的 Luna xhigh。起步两路翻译、一路复核，已有可读候选先交复核，出现积压再调整分工。

用冻结的 Python 环境逐份预检。长文档初始按连续 30–50 个源页估算，结合章节、文字密度、公式、表格及段落边界调整。每个源页只有一个译者。相邻页提供只读上下文。跨页续句、续表、行末断词和连续图注交给同一译者理解，再按原页放回。译者接收原文、负责页段、分包清单与冻结入口。独立复核者接收原文、候选渲染、页段和验收标准。

## 交接

从文档工作目录运行。将示例替换为实际页段、路径和代理标识：

~~~shell
python recovery/pipeline.py package --state recovery/state.json --pages 31-68 --out work/packages/chapter-2 --owner AGENT_ID
python recovery/pipeline.py status --state recovery/state.json --packages work/packages/chapter-2 --candidate PACKAGE_CANDIDATE.state.json
~~~

每包含可编辑状态、清单、分包基线及只读的相邻页清单。译者把补丁保存为包内的 edits.json，在小状态中应用后构建并核验预览。分包预览不能发布。复核者实际查看页面，提交绑定候选的观察，另报阻断项。主代理用 review 先登记通过页，保留这些已完成的复核。

只有主代理更新主状态。每份补丁依序配一份清单：

~~~shell
python recovery/pipeline.py apply --state recovery/state.json --edits work/packages/chapter-2/edits.json --package work/packages/chapter-2/package.json
python recovery/pipeline.py build --state recovery/state.json
python recovery/pipeline.py verify --state FINAL.state.json --previous-state FIRST_PACKAGE.state.json --previous-state SECOND_PACKAGE.state.json
~~~

已提交的同一补丁指纹可安全重放。基线变化会指出冲突的源页，重新导出受影响的未完成页段，使用当前块 ID 写增量。共享词汇和问题记录由主代理合入。显式上下文依赖须存在且一致，预览观察才能带入完整候选。整本导航和文档级检查在完整声明范围执行。

## 进度与恢复

逐份用 status 汇总活跃分包和候选状态，查看待译、待清点、已保存补丁、已合入、已构建、有效复核、已发布、阻断项和下一步。汇总中的复核数对应传入的候选，能否带入完整版由 verify 判断。交接记录保存实际代理标识、已提交路径和未完成页。恢复时查分包清单、已合入补丁、候选状态及在运行的作业和 PID；优先接回原代理。原代理不可用时，新代理只接未完成页及明确退回项。新版本另建分包目录。

阶段变化和阻断即时汇报，长任务约每 20 分钟汇总有变化的进度。等待优先使用完成事件和磁盘日志。Windows 后台构建以隐藏窗口启动，作业 JSON 记录工作进程 PID、阶段、页数和可记录的退出状态；强制中断可能留下 running，重试前确认该进程。整个任务使用同一套已验证的 Python 环境。长页段提取和渲染可比较 --workers 1 与 --workers 2，Windows 可用内存不足时回退单进程。最终 PDF 由单进程写入。
