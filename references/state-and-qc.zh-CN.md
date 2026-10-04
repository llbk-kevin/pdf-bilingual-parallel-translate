# 恢复状态与验收生命周期

## 格式与坐标

使用 UTF-8 无 BOM JSON，新任务的 schema_version 为 2；历史包继续支持版本 1。除绝对路径外，路径相对于 state.json 解析。指纹为实际字节的、小写 SHA-256。以下单页示例说明字段，占位指纹必须替换，不代表完成最终验收。

~~~json
{
  "schema_version": 2,
  "document": {"source_kind": "english-original", "vendor": "example"},
  "source": {
    "path": "original.pdf",
    "sha256": "<actual SHA-256>"
  },
  "output": {
    "path": "bilingual.pdf",
    "sha256": "<actual SHA-256>"
  },
  "layout": {
    "builder": {
      "path": "build.py",
      "sha256": "<actual SHA-256>"
    },
    "fonts": [
      {
        "name": "Chosen font",
        "sha256": "<actual font SHA-256>",
        "source": "Permitted local/source location",
        "purpose": "Chinese regular text"
      }
    ],
    "pane_width_pt": 240,
    "body_size_pt": 10
  },
  "glossary": [
    {
      "source": "supply voltage",
      "target": "电源电压",
      "context": "device input"
    }
  ],
  "pages": [
    {
      "source_page": 1,
      "output_page": 1,
      "source_rect": [
        0,
        0,
        240,
        300
      ],
      "kind": "translated",
      "inventory_reviewed": true,
      "expected_blocks": [
        "p001-body01"
      ],
      "reading_order": ["p001-body01"],
      "context_reviewed": false,
      "blocks": [
        {
          "id": "p001-body01",
          "kind": "paragraph",
          "source_bbox": [
            20,
            30,
            220,
            70
          ],
          "target_bbox": [
            260,
            30,
            460,
            80
          ],
          "source_text": "Supply voltage: 5 V.",
          "translation": "电源电压：5 V。",
          "status": "translated"
        }
      ]
    }
  ],
  "issues": [],
  "qc": {}
}
~~~

source_rect 是输出页中原文区域的矩形，采用可见页面左上角为原点、PDF 点为单位的坐标，必须以 1:1 比例匹配原页可见尺寸。source_bbox 使用原页可见坐标，target_bbox 使用输出页可见坐标。这些坐标已考虑旋转及裁切，PDF 原始左下角坐标需转换后使用。页码均从 1 开始。

## 块与页面记录

每个原页出现一次，每个输出页映射一次。expected_blocks 是经过独立核查的原文清单，blocks 的 ID 必须与其完全一致，且在全文唯一。块类型可用 heading、paragraph、list-item、table、formula、caption、figure-label。

每块保存 source_text 和非空 translation。status 为 translated、verbatim 或 pending。verbatim 必须附 reason，并将保留文字填入 translation。pending 在草稿检查中产生警告，最终检查中产生错误。没有待译内容的页面使用 kind no-translation-needed 并填写 reason，不得以此跳过待译文字。

表格块还需 table.source_rows 与 table.translated_rows，二者是由字符串单元格组成的行数组，对应行单元格数量相同。原文非空的单元格对应译文也不能空。合并跨度、表头角色及脚注锚点保留为额外表格元数据。caption 和 figure-label 必须有 figure_id。可选 target_bbox 验证声明的目标矩形，但不能证明生成脚本实际将文字画在该处。

可按需要补充上下文、原始表达式、阅读顺序与锚点。最终就绪检查要求 layout 包含绑定 SHA 的生成脚本及字体登记表（name、sha256、source、purpose）。可选 layout.inputs 为外部布局/译文数据的 {path, sha256} 记录列表；程序核对已声明的磁盘文件，变化会使状态失效。脚本内容会与磁盘指纹比较；字体登记是必要元数据，不证明实际已嵌入这些字体或本机当前已安装。

## 内容指纹与失效

内容指纹由 source、layout、glossary、pages 和 issues 组成，按键排序、UTF-8 紧凑 JSON 序列化后计算。直接使用工具函数，不另行复制序列化逻辑：

~~~python
import sys
sys.path.insert(0, "<skill-dir>/scripts")
import pdf_tools
state = pdf_tools.read_json("state.json")
fingerprint = pdf_tools.content_hash(state)
~~~

output 和 qc 不参与该指纹，避免循环依赖；二者由独立字节指纹约束。译文、映射、术语表、布局、疑点、原文或生成脚本任何变化都会使旧验收失效。重新生成时清空 qc，更新原文/输出/脚本指纹，运行草稿 check-state 并按需重新生成。不能只换指纹就把旧验收“修复”为有效。

## 最终验收记录

完成最终保存、子集化和清理后，对实际交付文件审计并渲染所有页面。真正逐页查看并完成语义核查后，才填写已检查页码和 qc：

~~~json
{
  "content_sha256": "<pdf_tools.content_hash(state)>",
  "source_sha256": "<actual original SHA-256>",
  "output_sha256": "<actual final PDF SHA-256>",
  "translation_pages": [1],
  "visual_pages": [1],
  "reviewer": "<actual reviewer/session>",
  "reviewed_at": "<ISO 8601 with timezone>",
  "structure": "passed",
  "audit_path": "audit.json",
  "structure_notes": "<specific warning resolutions, or no warnings>"
}
~~~

最终就绪要求审计程序通过，并与实际原文/输出指纹一致。有警告时必须填写解释。issues 必须为 resolved，或为 retained 且附 note，说明保留的疑点及用户需要了解的内容。保留疑点应披露，不能悄悄当作准确翻译。

最终检查要求两种页码清单分别且无重复地覆盖所有原页，同时具备检查者/时间、有效生成脚本元数据、输出指纹和审计。程序验证的是记录的一致性，不是记录的真实性：不能仅凭渲染或测试通过就填写验收记录。合成测试可使用明确标为夹具的验收声明验证状态检查行为，但不代表真实文档审阅。

## 恢复与失败处理

不带 --final 的 check-state 检查草稿一致性。文件缺失、原文/输出/生成脚本字节变化、清单缺项或非空 qc 失效均为错误。完成待译块和原文清单审阅后再运行 --final。根据 JSON 的 code/page/block 定位错误，修复根因后重跑。

每完成一批保存状态，生成脚本与其放在一起。恢复时先验证原文指纹，再读取术语、译文、映射及布局决策。不要从旧中文 PDF 提取内容并将其作为权威恢复来源。可清理的渲染图放在紧凑恢复包之外。


## 版本 2：实际审阅证据

新任务使用 schema_version 2；上文基本示例是草稿，最终验收需补充下列证据。增加 document.source_kind（其他原文语言使用 original，或 english-original、official-chinese、generated-translation），以及适用的 vendor 和命名证据。每页 reading_order 必须等于 blocks 的顺序 ID。只有核对语义依赖后才能声明 context_pages 和 context_reviewed:true；否则指纹保守包含全书。layout、glossary 和 issues 始终为依赖。影响含义的疑点包括 page、block、source_quote、concern、treatment；可选 suggested_correction 必须有 evidence。译注附近保留原表达。

在冻结候选版本上执行构建、check-fonts、audit 和全书渲染后再审阅。输出状态引用该版本及实际构建输入。新版本使用新渲染目录，不覆盖已被审阅引用的索引。索引含准确的输出/原文指纹、渲染器版本和设置、PNG 文件哈希、RGB 像素哈希及 page_content_sha256。仅 PNG 元数据变化不影响像素哈希，但当前文件哈希仍须匹配它自己的当前索引。

除版本 1 qc 字段，版本 2 还要求 font_assignments（实际片段报告路径）、font_report {path,sha256}，以及覆盖全部原文页的 page_reviews。viewed 记录如下：

~~~json
{
  "page": 1,
  "mode": "viewed",
  "output_sha256": "<实际 PDF 哈希>",
  "render_index": {"path": "../work/render-v1/index.json", "sha256": "<实际索引哈希>"},
  "settings_sha256": "<索引设置哈希>",
  "image_sha256": "<PNG 文件哈希>",
  "pixel_sha256": "<RGB 像素哈希>",
  "page_content_sha256": "<索引内容哈希>",
  "reviewer": "<实际会话或审阅者>",
  "reviewed_at": "<含时区的 ISO 时间>",
  "evidence": "<实际打开图片的工具事件或审阅笔记引用>"
}
~~~

只有实际打开完整页面并完成检查后才能写 mode viewed。mode reused 保留当前渲染哈希，增加 previous（完整的原始 viewed 记录）及 reuse_reason。两个渲染索引和图片必须保留。只有设置、像素及语义依赖指纹一致才能复用。术语、共享布局、问题或相关上下文变化会使之失效。复用只是记录一致性检查，不证明此前查看者理解了页面；工具不会自动填写审阅声明。

v2 内容指纹额外包含 document。check-state --final 重新核对实际字体分配、字体文件指纹、渲染证据及原文/输出绑定，报告 mechanical_checks_passed、review_evidence_level 和 quality_certified:false。旧 ready_for_delivery 保留兼容，不能认证翻译。版本 1 报告 legacy-attestation-v1，迁移旧包时不能虚构 v2 证据。

## 仅路径迁移

执行已批准改名前，将原状态字节保存为历史快照并保持 qc 不变。只更新当前 source/output 路径，增加 migration，其中包含 kind:path-only、performed_at、reason、previous_state:{path,sha256}、old_source 和 new_source。保留原审计和审阅报告。校验器验证历史内容指纹、qc 相同、PDF 指纹不变，并仅反向替换 source.path 后比较内容相等，然后报告 verified_path_only_migration 而非 stale_qc_content；这是保留旧验收，不是新审阅。构建器、译文或布局改动不能使用例外。其他元数据变化按普通失效处理；重建测试在独立副本进行。
