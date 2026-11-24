# Conditional tool runtime

Read this only when using persistent Node kernels or background jobs. Direct CLI commands use short-lived processes, write long logs to files and keep all artifacts in the task folder. Use pipeline inspect for bounded state reads; never keep a full state, image array or base64 log in top-level REPL bindings.

## Background jobs

Use the frozen scripts/task_runtime.py start/status/cancel interface for a long-running job. start receives --argv-file (a UTF-8 JSON argument array), --job-dir inside the task, and --task-dir. Output and errors go to files; inspect bounded status instead of buffering logs in Node. Windows supervision is hidden. cancel verifies PID and process-start identity before acting on its own job tree. Save returned paths and exit status. Read --help for optional parameters.

## Persistent kernels

Use the checked Python environment before prepare and its returned frozen prefix afterwards. From the worker's own kernel launch:

~~~text
COMMAND_PREFIX recovery/coordination.py session-register --task-dir TASK --agent ACTUAL_ID
~~~

Registration verifies kernel.js/session identity in the parent chain and records PID, start time and memory. If it cannot verify the caller, report that result rather than guessing. Keep the exact returned record path.

Before handoff, save edits, observations and a restart checkpoint; confirm no unmanaged live jobs remain. Run session-mark --record RECORD --status cleanup_required --checkpoint FILE, then call this worker's own available js_reset. If unavailable mark cleanup_unavailable. Do not start another kernel just to report completion. Register a new kernel only when resuming work.

The coordinator runs sessions --task-dir TASK to observe disappearance of the registered PID/start identity. Only a previously cleanup_required session becomes reset_observed. Completed/interrupted agent labels alone do not prove release. Use a host close operation only when available; never terminate unknown processes by name, size or guessed working directory. A full app restart may release idle host sessions that cannot otherwise be closed.

Check memory with coordination.py memory --task-dir TASK at heavy-work admission or a resource failure, not continuous polling. Read failure diagnostics before retrying unchanged conditions. Memory settings and dynamic scheduling are in [coordination.md](coordination.md).
