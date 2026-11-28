# 译者实操

读取技能入口及本页，使用分配的原文、作者状态、分组材料和编辑模板。命名和模型已由主代理确认。只编辑本人负责的状态和页段，技能问题交主代理处理。

## 翻译

1. 按可读尺度查看原页，包括图片与转曲标签。groups.json 是来源视图，edits-template.json 提供保守候选。合并前确认段落和单元格边界，待译块归零不代表图片文字已覆盖。
2. 先处理正文、公式、表格或截图的代表块，确认可读的 font_size/font_size_min 范围和邻接空白。独立公式与标识保留并说明原因；行内变量按完整句意组织，需要时在中文中复写核对过的短符号和数值。
3. 写入 work/edits.json；分包则写入其状态旁的 edits.json。执行返回的 apply 动作，读取受影响页摘要及诊断。合法译文与合并已保存，排版未通过也不会丢失。续修文件只填写当前 ID 的增量编辑，不重交整份初始模板及其 merge_ids。
4. 代表页排法确认可读后，同类正文编辑可合批提交。首次处理复杂排版、调整公式或表格文字的块归属、修复去字碰撞时，交接前用最新作者状态预览受影响页。执行返回的 build 和 verify 动作，从 render_index 查看页面。

直接执行返回的完整 `argv`。查看总帮助用 `command_prefix + [runner, "--help"]`，查看子命令帮助用 `command_prefix + [runner, subcommand, "--help"]`。前缀包含 Python 解释器和冻结启动入口，`runner` 是脚本路径。查询当前 ID 时用 inspect，指定页码和 groups/blocks；查询 glyphs 还须指定块。返回内容有大小限制，支持 offset/limit。

## 编辑格式

~~~json
{"blocks":[{"page":1,"id":"当前源块ID","method":"replace","translation":"中文","font_size":9,"font_size_min":8}]}
~~~

使用当前 ID。首次合并在 merge_ids 中列出完整源块，后续只修改合并后的 ID。模板不会推荐不确定的跨列合并；明确源分隔线两侧的文字不能合并。错误合并可恢复：

~~~json
{"blocks":[{"page":1,"id":"合并块ID","split":true}]}
~~~

split 恢复完整源文字块，通过 inspect 查询当前 ID，旧译文保存在页面 split_notes。恢复后重新映射译文，不修改原文字形或手工拼接页面 JSON。

处理方式：replace 用于可见原生文字；preserve 附理由用于公式、数值、已有中文；cover 附理由用于图片、转曲或 OCR 文字。覆盖块提供 source_bbox、allowed_bbox，可指定 cover_bbox、cover_fill 和 cover_text_color。中文须能明确关联原图；practical 允许英文残影和配色差异。新增覆盖后检查线条、箭头、表值及标签。

文字留在对应段落／单元格。仅在确认邻接空白后用 allowed_bbox 和 expansion_reason 扩展，不跨格借空间，也不持续缩小字号消除提示。特殊几何见[原位构建](inplace.zh-CN.md)。

apply 集中检查排版、保留字形碰撞和链接。修改前读取已有诊断，简单且唯一的 Figure N → 图 N 自动定位；未解决的链接使用页级 link_overrides_patch，提供 source_link、target_block/target_text/occurrence，或核对后的 right_bbox。保留原跳转目标。

## 分包交付与续修

普通 apply 编辑分包作者状态，向主代理交付目录，另附剩余实质问题及跨页上下文。主代理导入当前结果、维护共享术语并汇总交付备注。

合入后的修复由主状态重新导出受影响页，优先原译者续作。原文或基线冲突交主代理处理。机器检查不能替代独立复核。

独立复核者查看完整交付候选。候选交接后，收到实质反馈再修改；可容忍细节在交接时简要记录。

持久 Node 内核或后台作业使用[工具运行说明](tool-runtime.zh-CN.md)，直接 CLI 工作无需登记内核。
