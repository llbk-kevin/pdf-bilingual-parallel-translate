"""Synthetic, regenerable integration fixtures; no user documents or fonts."""
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import pdf_tools as t
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import (NameObject, NumberObject, DictionaryObject,
                           DecodedStreamObject, ArrayObject, FloatObject)
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image

def source_pdf(dest, crop_rotate=False, duplicates=False):
    buf=io.BytesIO()
    c=canvas.Canvas(buf,pagesize=(240,300),invariant=1)
    im=Image.new("RGB",(12,12),(180,30,40))
    for n in range(2):
        c.drawString(30,260,f"Source {n+1}: 12 km if time <= 5 h.")
        c.beginForm("diagram"+str(n),0,0,100,100)
        c.drawImage(ImageReader(im),30,35,width=40,height=40)
        c.endForm()
        c.doForm("diagram"+str(n))
        c.linkURL("https://example.org/reference",(30,245,160,260))
        c.bookmarkPage("p"+str(n))
        c.addOutlineEntry("Section "+str(n+1),"p"+str(n))
        c.showPage()
    c.save()
    w=PdfWriter(clone_from=PdfReader(buf))
    if crop_rotate:
        for p in w.pages:
            p.cropbox.lower_left=(10,15)
            p.cropbox.upper_right=(230,285)
            p.rotate(90)
    if duplicates:
        add_duplicate_images(w)
    w.write(dest)

def image_objects(w):
    # Uses pypdf internal object array only for deliberate synthetic corruption.
    return [obj for obj in w._objects if isinstance(obj,dict) and obj.get("/Subtype")=="/Image"]

def add_duplicate_images(w):
    obj=image_objects(w)[0]
    dup=copy.deepcopy(obj)
    dup.indirect_reference=None
    ref=w._add_object(dup)
    key=NameObject("/FixtureExtraImages")
    if key not in w._root_object:w._root_object[key]=ArrayObject()
    w._root_object[key].append(ref)

def font_duplicates(w):
    payload=DecodedStreamObject()
    payload.set_data(b"SYNTHETIC-FONT-PAYLOAD"*40)
    a=w._add_object(payload)
    payload2=DecodedStreamObject()
    payload2.set_data(b"SYNTHETIC-FONT-PAYLOAD"*40)
    b=w._add_object(payload2)
    w._root_object[NameObject("/FixtureFontDescriptors")]=ArrayObject([
        w._add_object(DictionaryObject({NameObject("/FontFile2"):a})),
        w._add_object(DictionaryObject({NameObject("/FontFile2"):b}))])

def bilingual(source,dest,normalize=False,corrupt=False,duplicate=False,fonts=False):
    w=PdfWriter(clone_from=source)
    for p in w.pages:
        if normalize:
            p.transfer_rotation_to_content()
            x0,y0,x1,y1=map(float,p.cropbox)
            p.add_transformation(Transformation().translate(-x0,-y0))
            # Synthetic fixture deliberately leaves link coordinates untransformed;
            # audit must report the conservative warning.
            width,height=x1-x0,y1-y0
            p.mediabox.lower_left=(0,0)
            p.mediabox.upper_right=(width*2,height)
            p.cropbox.lower_left=(0,0)
            p.cropbox.upper_right=(width*2,height)
        else:
            width,height=float(p.cropbox.width),float(p.cropbox.height)
            p.mediabox.upper_right=(width*2,height)
            p.cropbox.upper_right=(width*2,height)
        overlay=io.BytesIO()
        c=canvas.Canvas(overlay,pagesize=(width*2,height),invariant=1)
        c.drawString(width+15,height-30,"Companion translation")
        if corrupt:
            c.setFillColorRGB(0,0,0)
            c.rect(0,0,width,height,fill=1,stroke=0)
        c.save()
        p.merge_page(PdfReader(overlay).pages[0])
    if duplicate:add_duplicate_images(w)
    if fonts:font_duplicates(w)
    w.write(dest)

class Diagnostics(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.src=self.root/"source.pdf"
        self.out=self.root/"output.pdf"
        source_pdf(self.src)
        bilingual(self.src,self.out)
    def tearDown(self):
        self.temp.cleanup()
    def state(self):
        builder=self.root/"build.py"
        builder.write_text("# fixture builder\n",encoding="utf-8")
        pages=[]
        for n in (1,2):
            bid=f"p{n}-body"
            pages.append({"source_page":n,"output_page":n,"source_rect":[0,0,240,300],
                          "kind":"translated","inventory_reviewed":True,
                          "expected_blocks":[bid],"blocks":[{"id":bid,"kind":"paragraph",
                          "source_bbox":[30,30,220,60],"source_text":f"Source {n}: 12 km if time <= 5 h.",
                          "translation":f"原文 {n}：时间 ≤ 5 h 时为 12 km。","status":"translated"}]})
        return {"schema_version":1,"source":{"path":"source.pdf","sha256":t.sha256_file(self.src)},
                "output":{"path":"output.pdf","sha256":t.sha256_file(self.out)},
                "layout":{"builder":{"path":"build.py","sha256":t.sha256_file(builder)},
                          "fonts":[{"name":"Fixture","sha256":"0"*64,"source":"generated fixture",
                                    "purpose":"Test metadata, no Chinese font rendered"}]},
                "glossary":[],"pages":pages,"issues":[],"qc":{}}
    def write_state(self,s):
        p=self.root/"state.json"
        p.write_text(json.dumps(s,ensure_ascii=False),encoding="utf-8")
        return p
    def accepted(self):
        s=self.state()
        report=t.audit(self.src,self.out,dpi=72)
        t.write_json(report,self.root/"audit.json")
        s["qc"]={"content_sha256":t.content_hash(s),"source_sha256":s["source"]["sha256"],
                 "output_sha256":s["output"]["sha256"],"translation_pages":[1,2],
                 "visual_pages":[1,2],"reviewer":"test fixture; not a real review",
                 "reviewed_at":"2000-01-01T00:00:00Z","structure":"passed","audit_path":"audit.json",
                 "structure_notes":"Fixture deliberately contains no Chinese."}
        return s
    def codes(self,report):
        return {f["code"] for f in report["findings"]}
    def test_nested_shared_resources_counted_once(self):
        m=t.pdf_metadata(self.src)
        self.assertEqual(m["resources"]["counts"]["images"],1)
        self.assertEqual(m["resources"]["counts"]["forms"],2)
        self.assertGreaterEqual(m["resources"]["images"][0]["incoming_references"],2)
        self.assertEqual(len(m["bookmarks"]),2)
        self.assertEqual(len(m["pages"][0]["links"]),1)
        self.assertFalse(m["resources"]["errors"])
    def test_source_preserved_and_audit_is_repeatable(self):
        before=t.sha256_file(self.out)
        a=t.audit(self.src,self.out,dpi=72)
        b=t.audit(self.src,self.out,dpi=72)
        self.assertTrue(a["mechanical_pass"],a["findings"])
        self.assertEqual(a,b)
        self.assertEqual(before,t.sha256_file(self.out))
        self.assertEqual(sum(a["classified_delta_bytes"].values()),a["size_delta_bytes"])
    def test_rotation_and_crop(self):
        source_pdf(self.src,crop_rotate=True)
        bilingual(self.src,self.out,normalize=True)
        m=t.pdf_metadata(self.src)
        self.assertEqual(m["pages"][0]["visible_size_pt"],[270,220])
        self.assertEqual({x["code"] for x in m["findings"]},{"rotated_page","crop_differs_from_media"})
        a=t.audit(self.src,self.out,dpi=72)
        self.assertTrue(all(p["pane_geometry"]["passed"] for p in a["pages"]))
        self.assertNotIn("source_visual_changed",self.codes(a))
        self.assertNotIn("source_text_changed",self.codes(a))
    def test_source_corruption_detected(self):
        bilingual(self.src,self.out,corrupt=True)
        a=t.audit(self.src,self.out,dpi=72)
        self.assertFalse(a["mechanical_pass"])
        self.assertIn("source_visual_changed",self.codes(a))
    def test_existing_duplicate_is_not_new(self):
        source_pdf(self.src,duplicates=True)
        bilingual(self.src,self.out)
        a=t.audit(self.src,self.out,dpi=72)
        self.assertNotIn("new_duplicate_image_streams",self.codes(a))
        bilingual(self.src,self.out,duplicate=True)
        a=t.audit(self.src,self.out,dpi=72)
        self.assertIn("new_duplicate_image_streams",self.codes(a))
    def test_duplicate_fonts_flagged(self):
        bilingual(self.src,self.out,fonts=True)
        a=t.audit(self.src,self.out,dpi=72)
        self.assertIn("new_duplicate_font_streams",self.codes(a))
    def test_same_image_bytes_different_decode_not_equivalent(self):
        w=PdfWriter(clone_from=self.out)
        obj=image_objects(w)[0]
        obj[NameObject("/Decode")]=ArrayObject([NumberObject(x) for x in (1,0,1,0,1,0)])
        w.write(self.out)
        a=t.audit(self.src,self.out,dpi=72)
        self.assertIn("original_image_resource_changed_or_missing",self.codes(a))
    def test_missing_bookmarks_and_links(self):
        w=PdfWriter(clone_from=self.out)
        del w._root_object["/Outlines"]
        for p in w.pages:del p["/Annots"]
        w.write(self.out)
        a=t.audit(self.src,self.out,dpi=72)
        self.assertIn("source_bookmarks_missing_or_changed",self.codes(a))
        self.assertIn("source_links_changed",self.codes(a))
    def test_final_state_and_stale_content(self):
        s=self.accepted()
        self.assertTrue(t.check_state(self.write_state(s),True)["ready_for_delivery"])
        s["pages"][0]["blocks"][0]["translation"]="changed"
        r=t.check_state(self.write_state(s),True)
        self.assertIn("stale_qc_content",{x["code"] for x in r["errors"]})
    def test_stale_output_builder_and_review_coverage(self):
        s=self.accepted()
        self.out.write_bytes(self.out.read_bytes()+b"\n% revision\n")
        (self.root/"build.py").write_text("# changed\n",encoding="utf-8")
        s["qc"]["visual_pages"]=[1]
        r=t.check_state(self.write_state(s),True)
        codes={x["code"] for x in r["errors"]}
        self.assertTrue({"output_fingerprint_changed","builder_fingerprint_changed",
                         "incomplete_visual_pages","stale_audit"}<=codes)
    def test_missing_translation_inventory_and_table(self):
        s=self.state()
        b=s["pages"][0]["blocks"][0]
        b.update(kind="table",translation="A | B")
        r=t.check_state(self.write_state(s))
        self.assertIn("table_structure_missing_or_changed",{x["code"] for x in r["errors"]})
        b["table"]={"source_rows":[["Item","Value"],["Distance","12 km"]],
                    "translated_rows":[["项目","数值"],["距离","12 km"]]}
        self.assertTrue(t.check_state(self.write_state(s))["valid"])
        b["translation"]=""
        s["pages"][1]["blocks"]=[]
        codes={x["code"] for x in t.check_state(self.write_state(s))["errors"]}
        self.assertTrue({"missing_translation","block_inventory_mismatch"}<=codes)
    def test_figure_requires_anchor(self):
        s=self.state()
        s["pages"][0]["blocks"][0]["kind"]="caption"
        self.assertIn("figure_anchor_missing",{x["code"] for x in t.check_state(self.write_state(s))["errors"]})
    def test_render_index_does_not_claim_review(self):
        dest=self.root/"renders"
        rc=t.main(["render",str(self.out),"--source",str(self.src),"--out",str(dest),"--pages","2","--dpi","72"])
        self.assertEqual(rc,0)
        r=t.read_json(dest/"index.json")
        self.assertFalse(r["visual_review_completed"])
        self.assertEqual([p["output_page"] for p in r["pages"]],[2])
        self.assertTrue(r["pages"][0]["comparison"]["passed"])
        self.assertTrue((dest/"page-0002-difference.png").exists())
    def test_refuse_overwrite_and_invalid_pages(self):
        before=t.sha256_file(self.src)
        self.assertEqual(t.main(["inspect",str(self.src),"--out",str(self.src),"--overwrite"]),1)
        self.assertEqual(before,t.sha256_file(self.src))
        with self.assertRaises(ValueError):t.parse_pages("0,3",2)
        report=self.root/"report.json"
        t.write_json({},report)
        with self.assertRaises(ValueError):t.write_json({},report)
    def test_render_rejects_wrong_source_state(self):
        s=self.state()
        statepath=self.write_state(s)
        other=self.root/"other.pdf"
        source_pdf(other,crop_rotate=True)
        rc=t.main(["render",str(self.out),"--source",str(other),"--state",str(statepath),
                   "--out",str(self.root/"bad-renders")])
        self.assertEqual(rc,1)
        self.assertFalse((self.root/"bad-renders").exists())


    def test_palette_recompression_and_numeric_representation(self):
        from pypdf.generic import ByteStringObject
        w=PdfWriter(clone_from=self.src)
        for image in image_objects(w):
            palette=DecodedStreamObject()
            palette.set_data(bytes([180,30,40]))
            image[NameObject("/ColorSpace")]=ArrayObject([
                NameObject("/Indexed"),NameObject("/DeviceRGB"),NumberObject(0),w._add_object(palette)])
            image[NameObject("/BitsPerComponent")]=NumberObject(8)
            image[NameObject("/Decode")]=ArrayObject([NumberObject(0),NumberObject(255)])
        w.write(self.src)
        bilingual(self.src,self.out)
        w=PdfWriter(clone_from=self.out)
        for image in image_objects(w):
            colors=image["/ColorSpace"]
            colors[3]=w._add_object(colors[3].get_object().flate_encode())
            image[NameObject("/Decode")]=ArrayObject([FloatObject(0.0),FloatObject(255.0)])
        w.write(self.out)
        a=t.audit(self.src,self.out,dpi=72)
        self.assertNotIn("original_image_resource_changed_or_missing",self.codes(a))
        self.assertNotIn("new_image_resources",self.codes(a))
    def test_caption_displacement_and_pipe_table_hints(self):
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        buf=io.BytesIO()
        c=canvas.Canvas(buf,pagesize=(240,300),invariant=1)
        c.drawString(30,40,"Figure 5.1 Overview")
        c.save()
        w=PdfWriter(clone_from=self.src)
        w.pages[0].merge_page(PdfReader(buf).pages[0])
        w.write(self.src)
        bilingual(self.src,self.out)
        buf=io.BytesIO()
        c=canvas.Canvas(buf,pagesize=(480,300),invariant=1)
        c.setFont("STSong-Light",10)
        c.drawString(255,250,"图5.1 概览")
        c.drawString(255,200,"项目|数值|条件|单位|下限|上限|备注|A|B|C|D|E|F|G")
        c.save()
        w=PdfWriter(clone_from=self.out)
        w.pages[0].merge_page(PdfReader(buf).pages[0])
        w.write(self.out)
        codes=self.codes(t.audit(self.src,self.out,dpi=72))
        self.assertIn("possible_flattened_table",codes)
        self.assertIn("caption_anchor_displaced",codes)


    def test_external_layout_data_invalidates_state(self):
        s=self.state()
        data=self.root/"translations.json"
        data.write_text('{"translation":"before"}',encoding="utf-8")
        s["layout"]["inputs"]=[{"path":data.name,"sha256":t.sha256_file(data)}]
        self.assertTrue(t.check_state(self.write_state(s))["valid"])
        data.write_text('{"translation":"after"}',encoding="utf-8")
        codes={x["code"] for x in t.check_state(self.write_state(s))["errors"]}
        self.assertIn("layout_input_fingerprint_changed",codes)

if __name__=="__main__":
    unittest.main()
