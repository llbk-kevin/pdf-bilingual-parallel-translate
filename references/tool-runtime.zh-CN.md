# 按需工具运行

仅在使用持久 Node 内核或后台作业时读取。直接 CLI 使用短生命周期进程，长日志写文件，产物留在工作目录。查询状态用有界 pipeline inspect，不把整份状态、图片数组或 Base64 日志放进 REPL 顶层绑定。

## 后台作业

长作业使用冻结 scripts/task_runtime.py 的 start/status/cancel。start 接收 --argv-file（UTF-8 JSON 参数数组）、工作目录内的 --job-dir 和 --task-dir。输出及错误写文件，读取有界状态，不在 Node 缓冲日志。Windows 监督进程隐藏启动；cancel 核对 PID 与启动时间后只操作本作业树。保存返回路径和退出状态，可选参数读取 --help。

## 持久内核

prepare 前使用已检查的 Python 环境，之后使用返回的冻结前缀。从工作者自己的内核启动：

~~~text
COMMAND_PREFIX recovery/coordination.py session-register --task-dir TASK --agent ACTUAL_ID
~~~

登记核对父进程链中的 kernel.js／session 身份，保存 PID、启动时间和内存；无法核实则报告，不猜测归属。保留返回的精确记录路径。

交接前保存编辑、观察与恢复检查点，确认无未托管作业。执行 session-mark --record RECORD --status cleanup_required --checkpoint FILE，再调用本代理可用的 js_reset；不支持则标记 cleanup_unavailable。不要为报告完成另启内核，续跑时才按需登记新内核。

主代理用 sessions --task-dir TASK 核实已登记 PID／启动时间身份是否消失；只有原先 cleanup_required 才转为 reset_observed。代理完成／中断本身不是释放证据。宿主有关闭操作时才使用，不按名称、大小或猜测目录终止未知进程。无法关闭的闲置宿主会话可由完整重启应用释放。

重任务准入或资源失败时用 coordination.py memory --task-dir TASK 检查，不持续轮询；重试前读取失败诊断。内存设置和动态派工见[协调流程](coordination.zh-CN.md)。
