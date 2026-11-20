# Skill maintenance

## Repository and installation

Maintain llbk-kevin/pdf-bilingual-parallel-translate on main. The installed entry is <CODEX_HOME>/skills/pdf-bilingual-parallel-translate. If CC Switch manages it, resolve the link before editing and verify its type, target and updated contents afterwards. Edit an unmanaged directory in place. Report broken links or divergent copies before making changes.

## Validation and publication

Keep SKILL.md and README.md aligned, along with each changed English reference and its .zh-CN.md counterpart. Keep commands, field names and examples equivalent. Use UTF-8 without BOM and check Markdown links and agents/openai.yaml. Run the installed skill-creator validator when available.

Install requirements-dev.txt in a suitable environment and run from the repository:

~~~text
python -m unittest discover -s tests -v
python scripts/pipeline.py --help
python scripts/pdf_tools.py --help
~~~

The suite generates its own PDFs and fonts. Use the relevant regressions for behavior changes. Exercise page geometry and original-pane isolation for coordinate changes, encoded images and masks for resource changes, and evidence reuse and publication paths for pipeline changes. For optional visual fixtures, run tests/generate_layout_samples.py --out <external-dir> --font <permitted-Chinese-font>, adding --face-index for a font collection.

Keep user inputs, translations, renders, recovery files, fonts and credentials outside the repository. Follow AGENTS.md for commit format and normal push to origin/main.

## Implementation constraints

For coordination changes, test the work-plan validator with full/split page ownership, independent review identities, explicit model requests and real-evidence classification, repeated original-worker continuations and lightweight progress during a heavy-work queue. A static model list is not a capability test. Use a small independent trial from the revised entrypoint; keep its confirmation table, dispatch ledger and checkpoints outside the repository. Count unique agent IDs separately from continuations and concurrent activity.

For tool-lifecycle changes, test success/failure/cancel/orphan/PID reuse, bounded log transport and UTF-8 paths. Run repeated synthetic large-state queries and jobs in an isolated parent, recording initial/peak/end memory and post-warmup growth. Validate real host reset by disappearance of the registered PID/start identity; mark unsupported or unverified cleanup explicitly. Keep host process details and task measurements outside the repository.

- Compress non-image streams without re-encoding original images. Audit traverses reachable resources and checks encoded image streams and their display semantics. Review the encoded-stream inventory when changing the pypdf major version.
- Normalize UserUnit in the in-memory PDFium rendering copy. Use the same matrix and pixel origin for both panes.
- Use source drawing traces and translated fontTools outlines for deletion and collision bounds. Disable font timestamp recalculation for repeatable builds.
- Read raw PDF destination arrays to preserve nullable XYZ coordinates. Follow the geometry and interaction contracts in [inplace.md](inplace.md).

Compare the same input when changing batch drawing, PDF serialization or worker count. Record stage wall/CPU time, peak working set, state bytes, object counts and rendered pages. Check pixels, fonts, navigation and shared resources before changing defaults. The build job and pipeline event records supply timing and scope. Use isolated state copies for comparisons; reserve a full-size trial for a separate maintenance run.

For preparation/freezing changes, test cross-drive references, rollback before publishing state, input preservation and new-version package handoff. Exercise coordination event replay and model identity, and preserve valid local-review reuse. Add a focused regression when a concrete failure reveals a gap. Keep task-specific evidence in the task folder.

For behavior changes, inspect related rules, callers and tests and update conflicts at their source. Maintain the current workflow/state contract and remove obsolete adapters and duplicate entry points. Record concrete remaining issues in the local maintenance report.
