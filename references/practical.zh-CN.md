# 阅读模式操作接口

遵循主入口的 practical/strict 取舍。以下示例需替换为实际路径。仅字形拆分、特殊几何或交互问题读取 inplace.md，不把其中严格整本要求带入普通阅读任务。

## 准备与翻译

先一并确认[命名](naming.zh-CN.md)与[代理工作计划](coordination.zh-CN.md)，再按确认后的路径运行 `prepare`。等待确认期间只做原文与路径的只读检查。

使用具备 requirements.txt 的现有或隔离 Python，查找许可允许的中文 TTF/OTF，必要时登记后备字体。路径加引号。在文档工作目录运行：

~~~text
python SKILL/scripts/pipeline.py prepare --source ORIGINAL.pdf --state recovery/state.json --pages 1,3-5 --font CHINESE.ttf --profile practical
~~~

--pages 为原文物理页号，从 1 开始，默认 all。选页明确标为 sample：输出连续编号，source_page 保留源页号；样本外书签及链接记为省略，不重定向。整本仍要求完整源页。字体以路径和哈希登记，重建需可用；PDF 内嵌实际用字子集，阅读不需外部字体。

prepare 在状态旁冻结当前脚本、运行入口/配置及资源预算模块，写 inventory.json 与 preflight.json。后续使用返回的 command_prefix 加 runner，下例用 COMMAND_PREFIX 代表这个前缀。--workers 支持 auto（默认）或正整数，按本机 CPU/内存预算准入，资源遥测记录实际选择。后续包括 verify/review/publish 均使用冻结入口，不把命令变量改回 SKILL/scripts/pipeline.py。维护时如需替换当前任务的脚本，另建恢复目录。先读简洁 inventory，不反复读巨大的字形状态。source_group/source_line 辅助段落归属但不决定阅读顺序。可用 pdf_tools.py render ORIGINAL.pdf --pages SELECTION --out work/source 查看原页，再决定覆盖与公式。风险仅为提示，不是自动翻译结论。公式密集提示属于非阻断启发式，编码异常和实际可见原文优先。AES 支持随 requirements.txt 安装。missing_encryption_dependency 提示补齐依赖，password_required 提示需要源文件密码。目录跳转按声明的选页范围检查，样本外目标报告 sample_link_omitted。practical 登记确认空目标或未定义命名目标的链接和书签，能获得名称时一并记录，并保留外观及标题。strict 要求跳转有效。

准备过程先暂存提取、字体和冷启动检查，通过后提交管理文件，状态最后提交。失败保留已有恢复包及用户自放文件，诊断仍可读取。同盘引用用相对路径，跨盘引用用绝对路径并核对指纹，无需手工复制字体。

派工前直接执行返回的 commands.source_render_argv 一次。commands.status_argv、inspect_argv、build_argv 也带冻结运行器和精确路径，参数数组直接交给子进程 API。package 返回适用于自身状态的命令。shell/import 失败应诊断环境，不绕过冻结入口。

需要修构建代码时，从修订后的仓库入口执行：

~~~text
python SKILL/scripts/pipeline.py refreeze --state recovery/state.json --out recovery-v2
~~~

仅接受作者状态和新目录。保留源文件、字体、译文、字形归属、清点及上下文；新版清空 QC 和分包已应用凭据。核对源哈希及当前状态有效性。旧脚本、候选和证据保持原样。结果返回依赖指纹和新命令。受影响分包重新导出，原补丁按新 manifest 验证；不改依赖或基线哈希来压过冲突。

### 有界状态查询与长命令

用冻结 pipeline inspect 查询，避免在持久 Node REPL 内解析完整状态：

~~~text
COMMAND_PREFIX recovery/pipeline.py inspect --state recovery/state.json
COMMAND_PREFIX recovery/pipeline.py inspect --state recovery/state.json --pages 12 --detail blocks --limit 20
COMMAND_PREFIX recovery/pipeline.py inspect --state recovery/state.json --pages 12 --block ACTUAL_ID --detail glyphs --offset 0 --limit 50
~~~

默认summary；blocks必须显式选页，glyphs还须指定文字块。每次最多200项（默认20），next_offset用于翻页；超过4,000字符的文本会附明确截断标记。超过256 KiB响应预算时减小--limit。查询不修改状态、QC、诊断或事件日志；仍会在短生命周期Python进程加载状态，回答后退出。

build/verify等冻结长命令，把精确argv数组写入work/job-argv.json。使用记录的Python执行冻结task_runtime.py；它是进程包装器，不替代PDF构建器：

~~~text
PYTHON recovery/task_runtime.py start --task-dir TASK --job-dir TASK/work/jobs/build-001 --argv-file TASK/work/job-argv.json
PYTHON recovery/task_runtime.py status --job-dir TASK/work/jobs/build-001
PYTHON recovery/task_runtime.py cancel --job-dir TASK/work/jobs/build-001
~~~

作业和参数文件都在TASK/work内，作业目录必须新建、不覆盖。--cwd可指定短启动目录，缺省使用任务父目录。独立监督进程写stdout.log、stderr.log和job.json，不依赖REPL存活；status只返回路径和有界错误尾部，不返回全部日志或结果。按需读取尾部或诊断，不用execFile/maxBuffer收集全量输出。取消核对PID及启动时间，只终止本作业worker树；监督进程异常退出会报告orphaned，可通过cancel恢复清理。存在未托管后台子进程时不重置内核。

监督进程及其启动器退出前，status可能为finalizing；等终态后再改名或删除日志。优先使用可用的直接CLI工具；一种shell失败时先检查可用替代入口，再决定是否用Node运行。

在新的 Node 内核处理 PDF 前，先用协调会话命令登记并保留记录路径，复核者也适用。Node只保存路径、小批编辑和摘要。图片逐张读取，避免持久图片Buffer/Base64数组；必要临时读取放函数作用域，并在约定交接点重置。清空一个变量或强制GC不能证明历史模块绑定和原生缓冲已释放。会话登记与清理命令见[集群协作](coordination.zh-CN.md)。

批量 edits.json 原生段落示例：

~~~json
{"blocks":[{"page":1,"id":"paragraph-1","merge_ids":["EXTRACTED-ID-1","EXTRACTED-ID-2"],"method":"replace","translation":"完整段落的中文。","font_size":10,"font_size_min":9},{"page":1,"id":"EXTRACTED-FORMULA-ID","method":"preserve","reason":"保留原公式及数值"}],"inventory_reviewed_pages":[1]}
~~~

替换真实 ID 并核对原文。合并的新 ID 必须唯一，或属于本次 merge_ids；不能借用别的段落 ID。merge_ids 合并字形引用与原框，不跨栏或跨单元格；普通块编辑省略 merge_ids。上述合并成功后再次修改，直接指定新 ID，例如 {"blocks":[{"page":1,"id":"paragraph-1","font_size":9,"font_size_min":8}]}；不要重复已经移除的原 merge_ids。公式混合正文确需拆字形时查 inplace.md，可写小型 JSON 编辑操作处理例外，不从乱码重绘整式。每个原文字形必须且只由一块拥有。短标识、单位、尺寸、公式保留，说明性正文翻译，不能为了省事把正文 preserve。用 apply 返回的 unresolved_count 和 unresolved_by_page 对照待处理块。已预置 preserve 的块仍须核实，只有改变处理方式时才提交编辑。失效 merge_ids 诊断列出源页、目标块和缺失 ID。

图片/转曲新覆盖示例，坐标为可见页左上角 PDF 点：

~~~json
{"blocks":[{"page":3,"id":"scan-note-1","method":"cover","kind":"text","source_text":"Visible English label","source_bbox":[10,20,90,32],"cover_bbox":[10,20,90,32],"allowed_bbox":[10,20,90,32],"translation":"中文说明","font_size":8,"reason":"局部图片标签，已对照图纸检查边界"}],"inventory_reviewed_pages":[3]}
~~~

从原文渲染图量坐标时，索引路径相对编辑JSON：TASK/work/edits.json引用TASK/work/source/index.json，顶层写 "source_render_index":"source/index.json"，不要再加work/。该批所有source_bbox/cover_bbox/allowed_bbox按原始渲染像素输入，apply核对指纹/图片尺寸并按记录DPI换算。不从缩放查看器猜倍率、不混用点和像素；未提供该字段仍是PDF点。双语图或裁剪图不能作为原文索引。

仅在已核实的对应位置添加浮层。practical 只要求中文可读、原文对应关系清楚，不要求完全擦除英文、边界精确或背景同色；保留小残字，不为此扩大框或重复重建。可选 cover_fill 和 cover_text_color 为 [0,1] RGB 三元组，缺省为白底黑字。选定一种可读样式即可，不做自动配色。照片上的型号、板卡丝印及微小软件界面标签，在已有必要中文图注或解释时可保留。allowed_bbox 扩展必须用 expansion_reason 说明邻接空白，不跨表格格子。apply 也接受按源页键的 context_pages、link_overrides、glossary、issues。逐条更正优先使用 link_overrides_patch，例如 {"link_overrides_patch":{"1":[{"source_link":0,"target_block":"paragraph-1","target_text":"设计","occurrence":2}]}}。按 source_link 新增或替换，保留其他链接；link_overrides 仍替换整页列表（空列表清空），同页不能同时使用两种接口。occurrence 是 target_block 内匹配的从 1 开始序号，重复锚点须明确指定。link_overrides 的 source_link 按原页 /Link 批注从 0 起算，0 是首个链接，不是从 1 开始的页码；对照原始可点击区域检查生成的 page.link_mappings。链接文字翻译后用 target_block 加 target_text 指向相应文本。术语表和布局为共享依赖。practical 默认本页及声明上下文依赖，strict 未确认上下文时使用全书依赖。改 authoring state 不覆盖旧候选和审核史。

~~~text
COMMAND_PREFIX recovery/pipeline.py apply --state recovery/state.json --edits edits.json
COMMAND_PREFIX recovery/pipeline.py build --state recovery/state.json
~~~

apply 返回 preview_skipped_pages 和 unresolved_by_page，preview_argv 仅包含已完成处理的变化页。preview_argv 参数数组使用当前冻结入口、authoring state 和变化页。直接传给子进程 API，不拼成未转义的 shell 命令。局部调整使用该预览，最终完整候选省略 --pages。build 从当前状态读取原文路径。

build 返回 PDF、生成状态及字形运行记录。verify/review/publish 必须用返回的生成状态。使用 --pages 3 局部预览，交付时构建完整声明范围。局部检查在 PDF 写出前解析最终交付范围内的右栏锚点，包括预览外目标，分包保留 final_source_pages。同类冲突从 last-error.json 集中修复后重建。链接映射错误按选定页集中写入 link_conflicts，包含 page、source_link 和 source_bbox，一批修完，不为逐条报错重复全本构建。降低字号时同时检查 font_size 和 font_size_min，下限不能高于指定字号。font_size_min 空或缺省为固定字号，不为强制通过不断缩小到不可读。preserved_glyph_removed 会指出缺失字符、原页位置、保留块及相邻替换块。先检查原图局部和相关掩码。同一字符及位置重复报错时先诊断，再修复已确认的碰撞并预览完整公式。

## 长文档恢复与分包

使用冻结入口，按原文件物理页号查询进度并依次提交编辑文件。

~~~shell
COMMAND_PREFIX recovery/pipeline.py status --state recovery/state.json --pages 1-40
COMMAND_PREFIX recovery/pipeline.py apply --state recovery/state.json --edits work/chapter-1.json --edits work/chapter-2.json
~~~

多份文档、长文档或独立复核的分包、归属与恢复见[集群协作](coordination.zh-CN.md)。使用编写状态查询翻译进度，使用构建返回的候选状态查询核验与复核。任一批次失败时原编写状态保持原样。局部预览可省略范围外跳转且不能发布，交付时构建完整声明范围。


## 代表页预览与连贯正文

按实际原文选取适用的行内/独立公式、密集单元格或截图代表页。先翻译小段完整内容，用preview_argv构建并查看，再推广到同类页；这是排版方法验证，不另做整本复核。

独立公式原位保留。行内变量正文先组织完整中文句，必要时在句中复写核实的短变量/数值，原生字形仍保留。保持字形归属并记录可见残留；不能为了碰撞检查通过而围绕每个保留字符拆散中文，或把句子散布到远处空白。公式混排同时检查保留符号与译文完整公式是否重复；表格按实际单元格归并，不采用固定横坐标阈值跨列合并。预览整个段落、相关公式和表格单元格，重要符号/数值不可遮挡；完整句与公式可读时，少量孤立原字形按practical保留。

unresolved_count为零后仍对照可见页和inventory，尤其检查提取遗漏的截图、栅格曲线和转曲标签，用局部浮层或明确关联的中文说明翻译主要内容。不能用继续编辑已译原生文字代替这项检查。

## 集中检查与真实记录

译者检查完整性、代表版式和冲突页，独立复核者覆盖交付范围；不额外要求译者登记第二套正式逐页审核。

~~~text
COMMAND_PREFIX recovery/pipeline.py verify --state work/RETURNED.state.json
~~~

verify 检查状态、字体、审计，一次生成原文、输出及相关差异图，返回 render_index、错误汇总和 review_needed。首次 verify 同时报告 inventory_review_needed。将可见原页与清单对照确认后，在该页的实际观察中填 `"inventory_reviewed": true`。同一候选补记清点可复用审计和渲染。verify 返回 rendered_pages、source_rendered_pages、mechanical_reused_pages 和 state_written_bytes，耗时见事件日志。修改后可复用未变化的源页和候选渲染，文档级检查照常执行。保留差异也不修改原始测量和 mechanical_pass。

打开review_needed或inventory_review_needed中的页面，在同一次真实查看中核对源清单、必要覆盖及当前具体差异，登记适用的inventory_reviewed/covers_checked/retain_right_difference证据。仅疑点看差分或放大。独立复核者提交自己的观察；多人复核各存文件，由状态写入者串行登记。先保存无阻断页证据，再修复并用--previous-state复用。使用review_handoff复制observations_template；模板绑定候选/渲染指纹，pages为空。缺字段和错绑分别诊断；不能为避免重看而虚报已完成检查。

~~~json
{"output_sha256":"COPY_FROM_VERIFY","render_index_sha256":"COPY_FROM_VERIFY","reviewer":"实际代理或人员","pages":[{"page":1,"evidence":"实际图片查看记录及观察","retained":["保留轻微断行"],"retain_right_difference":"仅确实检查了审计右侧差异时填写：为何不影响阅读"}],"structure_notes":"已检查基本可读性及所需范围"}
~~~

~~~text
COMMAND_PREFIX recovery/pipeline.py review --state work/RETURNED.state.json --observations observations.json
~~~

verify 列出 cover_review_needed。逐处对照原图与右侧浮层，确认位置对应，表格数值、引线及关键图形可读。局部细节看不清时放大该处。完成比较后在该页观察中设置 "covers_checked":true，由脚本登记覆盖块 ID。

不可预填观察，不手改 qc。渲染不会生成已查看记录。retain_right_difference 仅在 practical 下处理当前精确匹配的 right_graphics_changed_outside_recorded_regions，不能豁免原文损坏、字体、缺页或其他错误，更不能用于主要图形遮挡。strict 仍要求原始审计通过。

集中修改后先预览受影响页，再构建完整候选。运行 verify --previous-state PREVIOUS.state.json，上一版只登记部分页面时也可复用。可重复传入该选项，带上多份相关候选或分包。脚本逐页检查像素、设置和依赖，保留有效记录的原查看者、时间和证据。当前候选的有效观察优先。按 review_needed 补查，并为变化后的差分记录新的判断。完整候选仍执行自动检查。

review 返回 observations_saved、saved_pages、reviewed_pages 和 review_needed。查看 ready 和 errors 确认能否交付。局部审核可通过 verify --previous-state 复用。

观察复用、机械缓存复用和实际渲染页数分别报告。即使登记字体不变，改字也可能改变共享的嵌入字体子集，使其他页的绘制指纹失效。保留实测计数，不改掩码或把审核复用说成无需渲染。

## 交付与维护

~~~text
COMMAND_PREFIX recovery/pipeline.py publish --state work/RETURNED.state.json --output ACCEPTED.pdf
~~~

publish 将交付说明.md 写入工作文件夹，将 publication.json 写在已验收状态旁，并返回相应路径和 task_dir；只向 --output 复制已验收 PDF。说明包含源/输出哈希、资源增量、范围、保留问题及恢复方法。工作文件夹从状态所在的 work/、recovery/ 或 recovery-vN/ 推导；其他布局通过 publish --task-dir DIR 明确指定包含状态的工作文件夹。复制前检查说明、记录及成品目标冲突，替换已有目标须 --overwrite。样本的源大小是完整原文件，并明确不是同页压缩比例。普通交付核对冻结依赖。需要重建时执行返回的 recovery_argv，PDF 及伴随文件写入任务目录的 work/rebuild/accepted.rebuilt.pdf。

pipeline-events.jsonl 记录各命令的耗时、结果和资源遥测。每次失败的完整 diagnostics/ 记录包含阶段和作业路径，由 last-error.json 及事件日志引用。失败时保留退出码、stdout 和 stderr，再读取 --state 旁的 last-error.json 定位问题。现有目标需显式 --overwrite。
