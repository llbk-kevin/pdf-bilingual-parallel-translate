# 原位翻译：默认构建器与 v3 状态

## 提取、编辑与构建

任务操作统一使用 [pipeline 流程](practical.zh-CN.md)，由 prepare 冻结完整运行环境。本参考定义构建器的数据与几何合同。

extract 创建输入清单，不完成翻译。它记录原文 SHA-256、页数、可见几何及不可改写的字形事实。含字母的原生片段默认 unresolved；纯数字/符号默认 preserve，但仍须复核。图片/转曲文字不自动识别，隐藏 OCR 另作标识。设置 inventory_reviewed 前对照可见内容；原生文字少不等于无需翻译。

通过 extract 的稳定块 ID **并核对 source_text** 关联译文。另一次使用不同 flags 的 rawdict/dict 抽取，片段顺序及空白块分组可能不同，不可按那次抽取的块序号贴译文。ID 仅在相同原文/提取器条件下稳定，不承诺跨任意 PDF 编辑或引擎升级稳定；源哈希和重新抽取的字形库存检测变化。

构建器只读输入状态，写出 draft.pdf、draft.state.json 和 draft.font-runs.json。审计/渲染使用生成状态，其中保存实际边界、字号、运行环境和构建器/依赖指纹，并清空旧 qc。输出/报告默认禁止误覆盖。不支持特性和汇总的排版冲突会在保存候选 PDF 前失败，不自动选用其他布局。

## 坐标与映射

v3 使用 schema_version: 3 及 layout.mode: inplace。每页保存从 1 开始的 source_page、output_page、geometry（width、height、cropbox、mediabox、rotation、user_unit）、source_rect [0,0,W,H]、glyphs、blocks、expected_blocks 和 reading_order。字形/source/allowed/cover/actual 框均为裁切、旋转及 UserUnit 后的**可见页面左上角点坐标**。target_bbox 是实际框向右平移 W 后的输出坐标，不可混用 PDF 左下角坐标。

字形事实包括 id、text、bbox、origin、font、size、hidden 和 trace_type。不得为了通过排版检查改写事实。一个连字拆出的零宽 Unicode 尾字仍保留原 bbox；字体、字号、原点和 trace 信息相符时，删除区域由前方承载字形提供。保留连字的一半、替换另一半会被拒绝。其他不支持的零面积字形明确失败，不静默省略。

原生块通过 glyph_ids 和可选的半开区间 glyph_ranges 引用字形，例如 [[0,5],[8,12]]。每个非空白源字形必须恰好归属一个选定范围，包括保留公式和隐藏 OCR。合并片段时将 ID 连接到一个连贯块；保留行内数值时把文字和值的 ID 拆成不同块。同步 expected_blocks 和 reading_order，使之对应最终有序块列表。source_text/source_bbox 和语义、表格、图形锚点应真实有意义。原位表格文字可使用 table-cell 块，原表格线保留；有意组合成 kind: table 时，还需 source_rows/translated_rows 元数据。

提取器不判断数学语义。需保留的符号/数值分离原生归属，但不能据此把中文阅读顺序拆碎。独立公式保留；行内记号按[操作说明](practical.zh-CN.md)的代表页预览步骤处理，完整中文句中可复写核实的短变量。预览变化页时核对受影响的公式与表值，未变化页复用有效观察。记录原文疑点及明确处理方式。

## 块处理方式

| method | 处理 | 必需的编辑信息 |
| --- | --- | --- |
| replace | 删除右侧选中的**可见原生文字**并绘制译文 | 字形 ID/范围、translation、allowed_bbox、字体设置 |
| cover | 如指定则删除隐藏/原生 OCR；在明确图片/转曲标签区域绘制可读中文浮层 | cover_bbox（或 source_bbox）、reason、translation、allowed_bbox；手工标签可无字形 ID |
| preserve | 原样复用，不新绘文字、不产生字体 runs | reason 及保留的 translation/source_text |
| unresolved | 保存待解决决定 | 说明/疑点；选中页存在该块时拒绝构建 |

为图片/转曲标签新增块时，填写唯一 id、kind、人工核对的 source_text/source_bbox、glyph_ids: []、glyph_ranges: []、method: cover、cover_bbox、allowed_bbox、translation、reason 和 font_size。浮层保持局部且对应关系清楚；practical 允许露底和英文残字，不为清除残字扩大框。用户明确允许少量局部遮挡时，记录准确边界/理由并目视验证，不静默掩盖影响含义的数据。

隐藏 OCR 不能使用 replace：仅删隐藏文本，扫描图上的英文仍然存在。使用带可见标签范围的 cover，或说明理由后 preserve。保留周围图形几何和有效符号；扫描文字无法识别时，不编造原文。

## 字体、拟合与行内记号

layout.fonts 登记 {name, source, sha256, purpose, face_index?}，source 相对状态解析；来源/许可情况保存在恢复说明中。block.font 选择登记名称。缺字时按已核验登记字体回退，没有字形则失败。原字体/图片不是让交付 PDF 依赖外部资源的理由。中文字体在全文件共享，全部页面完成后子集化。

font_size 为期望字号；可选 font_size_min 和 font_size_step（默认 0.25 pt）允许有界拟合，没有下限字段时固定字号。查看实际页面后为每块选择清晰可读的下限。构建器记录 actual_font_size、layout_lines 和 actual_glyph_boxes。能容纳时保持英文词/型号完整，将常见行尾标点与前一单元合并，只有单个单元超过整行时才拆字，不缩短译文。溢出报告具体块和所需/可用高度。

allowed_bbox 默认等于原框，扩展或移动须填写 expansion_reason，说明已确认的相邻空白。不挪动图片、曲线框或表格网格腾位置。构建器通过 fontTools 测量译文字形轮廓（MuPDF glyph_bbox 可能返回字体全局框），原生字体的原始上升部虚高时采用绘制 trace 框；检查这些框与保留原生文字、其他译文字形和 cover 的碰撞，而非笼统拒绝允许框重叠；一次汇总选中页的所有已检测冲突。图形/背景相互作用、阅读顺序和可读性仍需视觉检查。

rotation 支持逆时针 0/90/180/270 度；提取保留 source_angle 与 orthogonal。非正交原生替换会拒绝；明确设计的 cover 可选择支持的方向。color 为从原生片段继承的 RGB [0..1]，彩底白标题尤其需要保留；cover_fill、cover_text_color 可选指定浮层背景和文字的 [0,1] RGB 三元组，缺省独立于原生 color，默认为白底黑字。缺省 color 为黑色。

仅支持平衡且不嵌套的 <sub>…</sub> 与 <sup>…</sup>，如 I<sub>out2</sub> 或 V<sup>2</sup>。以正文的 0.7 倍字号和基线偏移绘制；实际 runs 保存可见字符、所用字体、字号和 baseline_shift，不含标签。其他标签失败。复杂独立公式保留原矢量，不扁平化成 ASCII 下划线或反复的文字解释。

字体伴随文件为 schema_version 1，含 output_sha256 和 runs，每个 run 保存 page、block、font（登记名称）、text、font_size、baseline_shift 和可选 fallback_from。check-fonts 对 preserve 块免除新绘制覆盖要求，并验证实际译文 runs。字体覆盖不等于视觉验收。

## 几何、资源与交互

左右两侧通常从同一个打开的源文档调用 show_pdf_page，复用 graft 映射。先在右侧去字，再放入左侧，使用 images=0、graphics=0、text=0、fill=False。预检发现 Form 封装影响保真时，可为零旋转、零原点的适用页面选用原生左栏内容流，保留原资源并裁切到左侧区域。只有合并区域不会碰到保留字形时才合并相邻中心线掩码，保留图片像素、软遮罩、曲线、彩色填充和表格线。仅无损压缩非图片流，不重编码原图流。 保存候选前比较去字前后右栏可定位的保留字形。preserved_glyph_removed 会报告缺失位置和相关替换块。

普通零旋转页面可在左右两栏共用编码流达到 128 KiB、资源自足且仅含路径指令的 Form。构建器追踪源对象身份，核对调用顺序、变换及继承的绘图状态。嵌套、含文字或调用环境无法核实的 Form 沿用原绘图流。构建清单和审计的 `vector_forms` 记录最终绘制路径、唯一共享对象数及其单份存储字节。实际节省量使用相同输入的新旧候选对比。

构建器临时将源 Rotate 置零，再向 show_pdf_page 显式传入反向旋转。裁切、旋转、UserUnit 和混合物理页尺寸均有测试。PDFium 忽略 UserUnit，因此诊断工具仅在内存副本中规范化，再进行统一比例比较。原文件不被修改。

## 导航、批注和图层

预检和构建共用原始 PDF 动作解析。URI 动作按原值复制，包括本地文件 URI。命名或直接 GoTo 目标映射到选中源页，保留 XYZ、Fit/H/V/B/BH/BV/R 模式与空坐标轴。书签保留顺序、受支持的动作及无目标标题。预览和样本记录范围外的目标。practical 对确认空目标的链接保留外观，对应书签保留无跳转标题，均登记；strict 将其报告为无效动作。无法解析的名称、Launch、链式动作和定制链接外观在翻译前报告。

具有单一正常 /AP/N 外观流的静态 Text、Highlight、Underline、StrikeOut、Squiggly、Square、Circle、Ink 和 Stamp 批注复制到两侧。此路径要求未旋转且矩形完整位于可见页内。文字标记触及被替换内容、批注带动作或弹出及回复线程时需另行处理。批注可以引用受支持的图层。单一默认图层配置保留图层身份、顺序和默认可见状态，同名图层仍可独立切换。预检报告其他图层配置、互动表单、附件以及文字剪裁模式 4–7。成品仍须通过原页审计。

右侧链接点击区跟随译文实际字形。源锚文字在受影响译文块中唯一保留时自动定位；整个短块都属于单一链接时可使用实际块范围。不能唯一判断时，明确填写 page.link_overrides，例如 [{"source_link":0,"target_block":"p6-body","target_text":"图3-5","occurrence":1}]。source_link 是该页原 Link 的零基序号，occurrence 从 1 开始；也可明确给出 right_bbox 或 right_bboxes（右区本地可见坐标）。不能仅将原点击矩形平移到已重排的错误行；无法推导且无覆盖记录时构建失败。生成状态的 link_mappings 保存实际范围，仍需点击核验 URI/内部目标。

右侧已复用原印刷页码，应保留编号和无编号封面，不因当前试样页数少而新增编号。仅整份文档无页码时，已有经确认的 physical-total 分页字段可在预留右上区域添加页码/总数，并纳入实际 runs 与碰撞检查。v3 的 preserve-source 分页由现有图文提供，不再重复绘制编号。

## 验证

对生成状态执行 check-state、check-fonts、audit 和 render。check-state --final 核对声明的交付范围与审核证据。选页样本的图片基线及目的页按源页映射处理。推荐用 [流程入口](practical.zh-CN.md) 一次完成检查与渲染。

发布和按需重建见 [building.zh-CN.md](building.zh-CN.md)，验收证据见 [state-and-qc.zh-CN.md](state-and-qc.zh-CN.md)。

生成状态用 `annotation_mappings` 记录迁移的静态批注，用 `redaction_regions` 记录选中字形的原文绘制轨迹框。audit 与 render 都在相同像素原点比较右侧和原文，仅遮罩这些原文字形区域、实际译文字形轮廓框、明确的浮层覆盖、新增编号与移动后的可见链接边框。栅格边缘留两像素余量；其余区域任何像素超过配置的通道容差即失败（`right_graphics_changed_outside_recorded_regions`）。`allowed_bbox` 不会使整段区域免检；缺少删除区域记录会失败，不跳过比较。该检查证明所选分辨率下的局部图形保留，不能代替语义与视觉审阅。

显式 document.delivery_scope: sample 的选页样本记录范围外链接为省略；局部预览仍检查最终交付范围内的右栏锚点，实际跳转按预览范围省略。无跳转目标的书签标题保留原树结构。字号下限为 null 时视为固定请求字号。
