# 阅读模式操作接口

遵循主入口的 practical/strict 取舍。以下示例需替换为实际路径。仅字形拆分、特殊几何或交互问题读取 inplace.md，不把其中严格整本要求带入普通阅读任务。

## 准备与翻译

使用具备 requirements.txt 的现有或隔离 Python，查找许可允许的中文 TTF/OTF，必要时登记后备字体。路径加引号。在文档工作目录运行：

~~~text
python SKILL/scripts/pipeline.py prepare --source ORIGINAL.pdf --state recovery/state.json --pages 1,16,34-36 --font CHINESE.ttf --profile practical
~~~

--pages 为原文物理页号，从 1 开始，默认 all。选页明确标为 sample：输出连续编号，source_page 保留源页号；样本外书签及链接记为省略，不重定向。整本仍要求完整源页。字体以路径和哈希登记，重建需可用；PDF 内嵌实际用字子集，阅读不需外部字体。

prepare 冻结脚本到状态旁，写 inventory.json 与 preflight.json。后续包括 verify/review/publish 均使用冻结入口，不把命令变量改回 SKILL/scripts/pipeline.py。仓库更新不会更新已有恢复包；维护确需新脚本时建独立版本包，保留历史。先读简洁 inventory，不反复读巨大的字形状态。source_group/source_line 辅助段落归属但不决定阅读顺序。可用 pdf_tools.py render ORIGINAL.pdf --pages SELECTION --out work/source 查看原页，再决定覆盖与公式。风险仅为提示，不是自动翻译结论。公式密集提示属于非阻断启发式，编码异常和实际可见原文优先。

批量 edits.json 原生段落示例：

~~~json
{"blocks":[{"page":1,"id":"paragraph-1","merge_ids":["EXTRACTED-ID-1","EXTRACTED-ID-2"],"method":"replace","translation":"完整段落的中文。","font_size":10,"font_size_min":9},{"page":1,"id":"EXTRACTED-FORMULA-ID","method":"preserve","reason":"保留原公式及数值"}],"inventory_reviewed_pages":[1]}
~~~

替换真实 ID 并核对原文。merge_ids 合并字形引用与原框，不跨栏或跨单元格；普通块编辑省略 merge_ids。上述合并成功后再次修改，直接指定新 ID，例如 {"blocks":[{"page":1,"id":"paragraph-1","font_size":9,"font_size_min":8}]}；不要重复已经移除的原 merge_ids。公式混合正文确需拆字形时查 inplace.md，可写小型 JSON 编辑操作处理例外，不从乱码重绘整式。每个原文字形必须且只由一块拥有。短标识、单位、尺寸、公式保留，说明性正文翻译，不能为了省事把正文 preserve。

图片/转曲新覆盖示例，坐标为可见页左上角 PDF 点：

~~~json
{"blocks":[{"page":34,"id":"scan-note-1","method":"cover","kind":"text","source_text":"Visible English label","source_bbox":[10,20,90,32],"cover_bbox":[10,20,90,32],"allowed_bbox":[10,20,90,32],"translation":"中文说明","font_size":8,"reason":"局部图片标签，已对照图纸检查边界"}],"inventory_reviewed_pages":[34]}
~~~

若从原文渲染图量坐标，在编辑 JSON 顶层加 "source_render_index":"work/source/index.json"（相对编辑 JSON）。该批所有 source_bbox/cover_bbox/allowed_bbox 均按原始渲染图片像素输入，apply 核对源指纹、图片尺寸并按记录 DPI 换算。不从缩放后的查看器估算倍率，不在同批混用点和像素；未提供该字段仍是 PDF 点。双语图或裁剪图不能用作原文索引。

仅在核实位置添加覆盖。allowed_bbox 扩展必须用 expansion_reason 说明邻接空白，不跨表格格子。apply 也接受按源页键的 context_pages、link_overrides、glossary、issues。link_overrides 的 source_link 按原页 /Link 批注从 0 起算，0 是首个链接，不是从 1 开始的页码；对照原始可点击区域检查生成的 page.link_mappings。链接文字翻译后用 target_block 加 target_text 指向相应文本。术语表和布局为共享依赖。practical 默认本页及声明上下文依赖，strict 未确认上下文时仍沿用全书依赖。改 authoring state 不覆盖旧候选和审核史。

~~~text
python recovery/pipeline.py apply --state recovery/state.json --edits edits.json
python recovery/pipeline.py build --state recovery/state.json
~~~

build 返回 PDF、生成状态及字形运行记录。verify/review/publish 必须用返回的生成状态。调整可 --pages 16，但单页候选不能通过五页样本最终验收。同类冲突从 last-error.json 集中修复后重建。font_size_min 空或缺省为固定字号，不为强制通过不断缩小到不可读。

## 集中检查与真实记录

~~~text
python recovery/pipeline.py verify --state work/RETURNED.state.json
~~~

verify 检查状态、字体、审计，一次生成原文、输出及相关差异图，返回 render_index、错误汇总、review_needed 源页。详细日志按需读。相同输入复用哈希匹配证据，不重复渲染。保留差异也不修改原始测量和 mechanical_pass。

实际打开需查看的页，检查主要正文、图形及覆盖，有阻断疑问才放大。一次不是次数上限：有具体问题可重看，不为消灭小瑕疵重看。observations.json 写真实查看事件或具体观察：

~~~json
{"reviewer":"实际代理或人员","pages":[{"page":1,"evidence":"实际图片查看记录及观察","retained":["保留轻微断行"],"retain_right_difference":"仅确实检查了审计右侧差异时填写：为何不影响阅读"}],"structure_notes":"已检查基本可读性及所需范围"}
~~~

~~~text
python recovery/pipeline.py review --state work/RETURNED.state.json --observations observations.json
~~~

有覆盖的页会由 verify 列出 cover_review_needed。对照原图检查这些区域，特别是其下表格数值、引线和焊盘：像素审计会屏蔽声明覆盖区，不能证明覆盖安全。实际比较后，在该页观察中设置 "covers_checked":true，自动登记覆盖块 ID，不手写逐块证明。覆盖可能遮住图纸时，仅浏览全页不足以确认。

不可预填观察，不手改 qc。渲染不会生成已查看记录。retain_right_difference 仅在 practical 下处理当前精确匹配的 right_graphics_changed_outside_recorded_regions，不能豁免原文损坏、字体、缺页或其他错误，更不能用于主要图形遮挡。strict 仍要求原始审计通过。

编辑重建后 verify --previous-state OLD_ACCEPTED.state.json，仅像素、渲染设置及页依赖完全相同才复用。保留原查看者、时间和证据，只复查变更/依赖页；最终完整候选仍自动检查。共享字体、布局、上下文确实影响其他页时失效，不编辑指纹伪造复用。

## 交付与维护

~~~text
python recovery/pipeline.py publish --state work/RETURNED.state.json --output ACCEPTED.pdf
~~~

publish 自动生成中文交付说明及 publication 记录，状态含源/输出哈希，报告资源增量、范围、保留问题及恢复方法。样本的源大小是完整原文件，并明确不是同页压缩比例。恢复冒烟检查冻结源、字体、构建器和状态一致性；独立重建和重复资源稳定性主要在维护回归，不每次翻译重复。

pipeline-events.jsonl 记录命令耗时和结果，模型翻译/查看时间及工具次数另记。机器日志不代表思考 token。不同规模任务不承诺加速比例。完整错误写 last-error.json，命令返回简短摘要；现有文件需显式 --overwrite。真实例外超出入口能力时保留低层严格/手工工具。
