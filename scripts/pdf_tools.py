#!/usr/bin/env python3
"""Read-only PDF diagnostics for the pdf-bilingual-parallel-translate skill."""
from __future__ import annotations

import argparse
import collections
import ctypes
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path

from pypdf import PdfReader
from pypdf.generic import IndirectObject, StreamObject
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from PIL import ImageChops

from workflow import check_fonts, page_fingerprint, validate_reviews, validate_relocation, pagination_items

SCHEMA_VERSION = 2
_PASSWORD = None
RENDER_METHOD = "pdfium-uniform-matrix-v1"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(value, path=None, overwrite=False):
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path:
        dest = Path(path)
        if dest.exists() and not overwrite:
            raise ValueError(f"Output exists; use --overwrite: {dest}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        # UTF-8 without BOM; exclusive creation unless overwrite was explicit.
        with dest.open("w" if overwrite else "x", encoding="utf-8", newline="\n") as f:
            f.write(text)
    else:
        print(text, end="")


def checked_reader(path):
    r = PdfReader(path)
    if r.is_encrypted and not r.decrypt(""):
        if not _PASSWORD or not r.decrypt(_PASSWORD):
            raise ValueError("PDF requires a valid user-provided password; use --password-env. No guessing.")
    return r


def open_document(path):
    try:
        return pdfium.PdfDocument(str(path), password=_PASSWORD or "")
    except pdfium.PdfiumError as exc:
        raise ValueError("Cannot open PDF; check file and supplied password.") from exc

def deref(value):
    return value.get_object() if isinstance(value, IndirectObject) else value


def object_key(value):
    ref = value if isinstance(value, IndirectObject) else getattr(value, "indirect_reference", None)
    return f"{ref.idnum}:{ref.generation}" if ref else f"direct:{id(value)}"


def stream_bytes(obj):
    # pypdf 6.x stores the original encoded bytes here; get_data() would inflate them.
    data = getattr(obj, "_data", None)
    if not isinstance(data, bytes):
        raise ValueError("Unable to obtain encoded stream bytes; inventory is incomplete.")
    return data


def canonical_object(value, seen=None, depth=0):
    """Compare image semantics without relying on file-local object numbers."""
    seen = set() if seen is None else seen
    if depth > 30:
        raise ValueError("Resource metadata nesting exceeds supported depth.")
    if isinstance(value, IndirectObject):
        key = object_key(value)
        if key in seen:
            return {"cycle": True}
        return canonical_object(deref(value), seen | {key}, depth + 1)
    if isinstance(value, dict):
        is_stream = isinstance(value, StreamObject)
        is_image = is_stream and value.get("/Subtype") == "/Image"
        excluded = {"/Length"} if not is_stream or is_image else {"/Length", "/Filter", "/DecodeParms"}
        data = {str(k): canonical_object(v, seen, depth + 1)
                for k, v in value.items() if str(k) not in excluded}
        if is_stream:
            # Keep original image encoding strict; lookup/profile streams may be losslessly recompressed.
            key = "encoded_sha256" if is_image else "decoded_sha256"
            data[key] = hashlib.sha256(stream_bytes(value) if is_image else value.get_data()).hexdigest()
        return data
    if isinstance(value, (list, tuple)):
        return [canonical_object(x, seen, depth + 1) for x in value]
    if isinstance(value, bytes):
        return {"bytes_sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value) if float(value).is_integer() else float(value)
    if value is None or isinstance(value, (str, bool)):
        return value
    return str(value)


def inventory(reader):
    """Traverse the reachable object graph once, including nested Form resources."""
    seen = set()
    stack = [reader.trailer]
    streams, font_stream_keys = {}, set()
    references = collections.Counter()
    fonts, images, forms = [], [], []
    errors = []
    while stack:
        raw = stack.pop()
        if isinstance(raw, (IndirectObject, dict, list, tuple)):
            key = object_key(raw)
            if isinstance(raw, IndirectObject):
                references[key] += 1
            if key in seen:
                continue
            seen.add(key)
        else:
            continue
        try:
            obj = deref(raw)
            if isinstance(obj, dict):
                for field in ("/FontFile", "/FontFile2", "/FontFile3"):
                    if field in obj:
                        font_stream_keys.add(object_key(obj[field]))
                if obj.get("/Type") == "/Font":
                    fonts.append({"object": key, "name": str(obj.get("/BaseFont", "")),
                                  "subtype": str(obj.get("/Subtype", ""))})
                if isinstance(obj, StreamObject):
                    payload = stream_bytes(obj)
                    item = {"object": key, "encoded_bytes": len(payload),
                            "sha256": hashlib.sha256(payload).hexdigest()}
                    streams[key] = item
                    if obj.get("/Subtype") == "/Image":
                        images.append({**item,
                                       "signature": canonical_hash(canonical_object(obj)),
                                       "width": obj.get("/Width"), "height": obj.get("/Height")})
                    elif obj.get("/Subtype") == "/Form":
                        forms.append(item)
                stack.extend(obj.values())
            elif isinstance(obj, (list, tuple)):
                stack.extend(obj)
        except Exception as exc:
            errors.append({"object": key, "error": str(exc)})
    font_streams = [streams[k] for k in sorted(font_stream_keys) if k in streams]
    for item in [*fonts, *font_streams, *images, *forms]:
        item["incoming_references"] = references[item["object"]]
    image_keys = {x["object"] for x in images}
    form_keys = {x["object"] for x in forms}
    classified = font_stream_keys | image_keys | form_keys
    other_bytes = sum(v["encoded_bytes"] for k, v in streams.items() if k not in classified)

    def duplicates(items, field):
        groups = collections.defaultdict(list)
        for item in items:
            groups[item[field]].append(item)
        return [{"fingerprint": fingerprint, "objects": [x["object"] for x in group],
                 "copies": len(group), "extra_encoded_bytes_hint":
                     sum(x["encoded_bytes"] for x in group[1:])}
                for fingerprint, group in groups.items() if len(group) > 1]

    return {
        "reachable_objects": len(seen),
        "counts": {"font_dictionaries": len(fonts), "font_streams": len(font_streams),
                   "images": len(images), "forms": len(forms)},
        "encoded_bytes": {
            "fonts": sum(x["encoded_bytes"] for x in font_streams),
            "images": sum(x["encoded_bytes"] for x in images),
            "forms": sum(x["encoded_bytes"] for x in forms),
            "other_reachable_streams": other_bytes},
        "fonts": sorted(fonts, key=lambda x: x["object"]),
        "font_streams": font_streams, "images": images, "forms": forms,
        "duplicate_font_streams": duplicates(font_streams, "sha256"),
        "duplicate_image_streams": duplicates(images, "sha256"),
        "errors": errors,
        "accounting_note": "Unique reachable encoded streams only; incoming references count object-graph edges, "
                           "not page paint operations. The residual also includes "
                           "object/xref streams, dictionaries, unused/history data and container "
                           "overhead; it is not an exact ownership attribution. Duplicate raw "
                           "image bytes are suspects, not proof of interchangeable resources."
    }


def displayed_chars(page):
    """Characters in top-left visible-page coordinates, including rotation/crop."""
    width, height = page.get_size()
    factor = 10
    dw, dh = max(1, round(width * factor)), max(1, round(height * factor))
    textpage = page.get_textpage()
    result = []
    try:
        for i in range(textpage.count_chars()):
            u = pdfium_c.FPDFText_GetUnicode(textpage, i)
            if not u or u > 0x10FFFF:
                continue
            char = chr(u)
            if char.isspace():
                continue
            try:
                left, bottom, right, top = textpage.get_charbox(i)
                points = []
                for x, y in ((left, bottom), (right, top)):
                    dx, dy = ctypes.c_int(), ctypes.c_int()
                    ok = pdfium_c.FPDF_PageToDevice(page, 0, 0, dw, dh, 0, x, y, dx, dy)
                    if not ok:
                        raise ValueError("PDF coordinate conversion failed.")
                    points.append((dx.value * width / dw, dy.value * height / dh))
                xs, ys = zip(*points)
                box = [min(xs), min(ys), max(xs), max(ys)]
                if box[2] < 0 or box[0] > width or box[3] < 0 or box[1] > height:
                    continue
                result.append({"char": char, "bbox": box,
                               "font_size": float(pdfium_c.FPDFText_GetFontSize(textpage, i))})
            except pdfium.PdfiumError:
                continue
    finally:
        textpage.close()
    return result


def in_rect(char, rect):
    x0, y0, x1, y1 = char["bbox"]
    return rect[0] <= (x0+x1)/2 <= rect[2] and rect[1] <= (y0+y1)/2 <= rect[3]


def is_cjk(char):
    return "\u3400" <= char <= "\u9fff" or "\U00020000" <= char <= "\U0003134f"


def outline_items(reader):
    result = []
    def walk(items):
        for item in items:
            if isinstance(item, list):
                walk(item)
            else:
                p = reader.get_destination_page_number(item)
                result.append({"title": str(item.title), "page": p + 1 if p is not None else None})
    walk(reader.outline)
    return result


def link_target(reader, annot):
    a = deref(annot.get("/A", {}))
    if a.get("/S") == "/URI":
        return {"kind": "uri", "uri": str(a.get("/URI", ""))}
    dest = annot.get("/Dest", a.get("/D"))
    if dest is None:
        return {"kind": str(a.get("/S", "unknown")), "detail": str(a)}
    dest = deref(dest)
    if isinstance(dest, str):
        named = reader.named_destinations.get(dest)
        if named:
            p = reader.get_destination_page_number(named)
            return {"kind": "internal", "page": None if p is None else p + 1,
                    "name": dest}
        return {"kind": "named", "name": dest}
    if isinstance(dest, (list, tuple)) and dest:
        first = dest[0]
        target = None
        if isinstance(first, IndirectObject):
            for i, p in enumerate(reader.pages):
                if object_key(p) == object_key(first):
                    target = i + 1
                    break
        elif isinstance(first, int):
            target = int(first) + 1
        return {"kind": "internal", "page": target,
                "view": canonical_object(dest[1:])}
    return {"kind": "unknown", "detail": canonical_object(dest)}


def pdf_metadata(path, reader=None, with_char_summary=True):
    reader = reader or checked_reader(path)
    doc = open_document(path)
    pages, findings = [], []
    try:
        for i, page in enumerate(reader.pages):
            rendered = doc[i]
            textpage = rendered.get_textpage()
            try:
                text = textpage.get_text_range()
            finally:
                textpage.close()
            links = []
            for ref in deref(page.get("/Annots", [])):
                annot = deref(ref)
                if annot.get("/Subtype") == "/Link":
                    links.append({"rect": [float(x) for x in annot.get("/Rect", [])],
                                  "target": link_target(reader, annot)})
            size = list(rendered.get_size())
            item = {"page": i+1, "visible_size_pt": size, "rotation": page.rotation,
                    "mediabox": list(map(float, page.mediabox)),
                    "cropbox": list(map(float, page.cropbox)),
                    "user_unit": float(page.get("/UserUnit", 1)),
                    "text_characters": len(text.strip()), "links": links,
                    "annotation_count": len(deref(page.get("/Annots", [])))}
            if with_char_summary:
                chars = displayed_chars(rendered)
                sizes = sorted(x["font_size"] for x in chars)
                item.update({"visible_nonspace_characters": len(chars),
                             "cjk_characters": sum(is_cjk(x["char"]) for x in chars),
                             "min_font_pt": sizes[0] if sizes else None,
                             "median_font_pt": sizes[len(sizes)//2] if sizes else None})
            if page.rotation:
                findings.append({"code": "rotated_page", "page": i+1})
            if list(page.mediabox) != list(page.cropbox):
                findings.append({"code": "crop_differs_from_media", "page": i+1})
            if len(text.strip()) < 20:
                findings.append({"code": "little_extractable_text", "page": i+1,
                                 "note": "May be a cover, image, outlines or a scan; inspect visually."})
            if "\ufffd" in text:
                findings.append({"code": "replacement_characters", "page": i+1})
            pages.append(item)
            rendered.close()
    finally:
        doc.close()
    resources = inventory(reader)
    total = Path(path).stat().st_size
    resources["unclassified_file_bytes"] = total - sum(resources["encoded_bytes"].values())
    return {"schema_version": SCHEMA_VERSION, "tool": "pdf-bilingual-parallel-translate/inspect",
            "file": str(Path(path).resolve()), "sha256": sha256_file(path), "bytes": total,
            "page_count": len(pages), "pages": pages, "bookmarks": outline_items(reader),
            "resources": resources, "findings": findings}


def parse_pages(value, count):
    if value == "all":
        return list(range(count))
    result = set()
    for segment in value.split(","):
        if re.fullmatch(r"\d+-\d+", segment):
            a, b = map(int, segment.split("-"))
            if a > b:
                raise ValueError("Page range must be ascending.")
            result.update(range(a-1, b))
        elif segment.isdigit():
            result.add(int(segment)-1)
        else:
            raise ValueError(f"Invalid page selection: {segment}")
    if not result or min(result) < 0 or max(result) >= count:
        raise ValueError("Page selection is outside this PDF.")
    return sorted(result)


def render_image(page, dpi=144, max_pixels=40000000):
    width, height = page.get_size()
    scale = dpi/72
    if math.ceil(width*scale)*math.ceil(height*scale) > max_pixels:
        raise ValueError("Render exceeds --max-pixels; use a suitable DPI or larger explicit limit.")
    bitmap = pdfium.PdfBitmap.new_native(math.ceil(width*scale), math.ceil(height*scale),
                                         pdfium_c.FPDFBitmap_BGRA)
    bitmap.fill_rect((255, 255, 255, 255), 0, 0, bitmap.width, bitmap.height)
    matrix = pdfium_c.FS_MATRIX(scale, 0, 0, scale, 0, 0)
    clip = pdfium_c.FS_RECTF(0, 0, bitmap.width, bitmap.height)
    pdfium_c.FPDF_RenderPageBitmapWithMatrix(bitmap, page, ctypes.byref(matrix),
                                           ctypes.byref(clip), pdfium_c.FPDF_ANNOT)
    try:
        return bitmap.to_pil().convert("RGB").copy()
    finally:
        bitmap.close()


def page_mapping(state, count):
    if not state:
        return {i: {"source_page": i+1, "output_page": i+1} for i in range(count)}
    return {int(p["source_page"])-1: p for p in state["pages"]}


def region_for(mapping, source_page):
    sw, sh = source_page.get_size()
    return mapping.get("source_rect", [0, 0, sw, sh])


def compare_images(source_img, output_img, rect, dpi, pixel_tolerance, max_changed_ratio):
    scale = dpi/72
    # Match the ceil-sized source bitmap, not a second independently rounded extent.
    left, top = round(rect[0]*scale), round(rect[1]*scale)
    box = (left, top, left + source_img.width, top + source_img.height)
    if (box[0] < 0 or box[1] < 0 or box[2] > output_img.width or
            box[3] > output_img.height or box[2] <= box[0] or box[3] <= box[1]):
        return {"passed": False, "reason": "source_region_outside_output"}, None
    crop = output_img.crop(box)
    if crop.size != source_img.size:
        return {"passed": False, "reason": "source_region_size_changed",
                "source_pixels": list(source_img.size), "region_pixels": list(crop.size)}, None
    diff = ImageChops.difference(source_img, crop)
    channels = diff.split()
    maximum = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
    hist = maximum.histogram()
    changed = sum(hist[pixel_tolerance+1:])
    ratio = changed/(source_img.width*source_img.height)
    return {"passed": ratio <= max_changed_ratio,
            "changed_pixel_ratio": ratio, "pixel_tolerance": pixel_tolerance,
            "max_changed_ratio": max_changed_ratio,
            "note": "Raster comparison at the recorded DPI, not a semantic or interactive proof."}, diff



def caption_positions(chars):
    text = "".join(c["char"] for c in chars)
    positions = collections.defaultdict(list)
    for match in re.finditer(r"(?:Figure|Fig\.?|图)(\d+(?:\.\d+)*)", text, re.IGNORECASE):
        c = chars[match.start()]
        positions[match.group(1)].append((c["bbox"][1]+c["bbox"][3])/2)
    return positions

def content_streams(reader):
    unique = {}
    for n, page in enumerate(reader.pages, 1):
        raw = page.get('/Contents')
        if raw is None:
            continue
        obj = deref(raw)
        items = list(obj) if isinstance(obj, (list, tuple)) else [raw]
        for item in items:
            stream = deref(item)
            if not isinstance(stream, StreamObject):
                continue
            key = object_key(item)
            if key not in unique:
                payload = stream_bytes(stream)
                unique[key] = {'object': key, 'pages': [], 'encoded_bytes': len(payload),
                               'sha256': hashlib.sha256(payload).hexdigest(),
                               'compressed': bool(stream.get('/Filter'))}
            unique[key]['pages'].append(n)
    return list(unique.values())


def caption_findings(srcchars, rightchars, mapping, rect, height):
    findings = []
    if 'blocks' in mapping:
        for block in mapping['blocks']:
            if block.get('kind') != 'caption' or not block.get('target_bbox'):
                continue
            sc = [c for c in srcchars if in_rect(c, block['source_bbox'])]
            oc = [c for c in rightchars if in_rect(c, block['target_bbox'])]
            a, b = caption_positions(sc), caption_positions(oc)
            for label in a.keys() & b.keys():
                if len(a[label]) == len(b[label]) == 1:
                    delta = abs(b[label][0] - rect[1] - a[label][0])
                    if delta > max(36, height*.1):
                        findings.append({'figure': block['figure_id'], 'block': block['id'],
                                         'vertical_displacement_pt': round(delta, 2)})
    else:
        a, b = caption_positions(srcchars), caption_positions(rightchars)
        for label in a.keys() & b.keys():
            if len(a[label]) == len(b[label]) == 1:
                delta = abs(b[label][0] - rect[1] - a[label][0])
                if delta > max(36, height*.1):
                    findings.append({'figure': label, 'vertical_displacement_pt': round(delta, 2),
                                     'note': 'Unclassified text match; may be a prose reference.'})
    return findings


def small_text_roles(chars, mapping):
    roles = collections.Counter()
    for char in chars:
        matched = [b['kind'] for b in mapping.get('blocks', [])
                   if b.get('target_bbox') and in_rect(char, b['target_bbox'])]
        roles[matched[0] if len(set(matched)) == 1 else 'unclassified'] += 1
    return dict(roles)


def audit(source, output, state=None, dpi=144, pixel_tolerance=16,
          max_changed_ratio=0.001, max_pixels=40000000):
    sr, outreader = checked_reader(source), checked_reader(output)
    sm, om = pdf_metadata(source, sr, False), pdf_metadata(output, outreader, False)
    findings, pages = [], []

    def issue(severity, code, page=None, **extra):
        findings.append({"severity": severity, "code": code, **({"page": page} if page else {}), **extra})

    if sm["page_count"] != om["page_count"]:
        issue("error", "page_count_changed")
    if sm["resources"]["errors"] or om["resources"]["errors"]:
        issue("error", "resource_inventory_incomplete")
    s_images = {x["signature"] for x in sm["resources"]["images"]}
    o_images = {x["signature"] for x in om["resources"]["images"]}
    if missing := s_images-o_images:
        issue("error", "original_image_resource_changed_or_missing", count=len(missing))
    if added := o_images-s_images:
        issue("warning", "new_image_resources", count=len(added),
              note="Right pane should contain text/vectors; investigate added bitmap resources.")
    for category in ("duplicate_font_streams", "duplicate_image_streams"):
        before = {x["fingerprint"]: x["copies"] for x in sm["resources"][category]}
        for group in om["resources"][category]:
            if group["copies"] > before.get(group["fingerprint"], 1):
                issue("warning", "new_"+category, **group)
    sc_streams, oc_streams = content_streams(sr), content_streams(outreader)
    old_uncompressed = {x["sha256"] for x in sc_streams if not x["compressed"]}
    new_uncompressed = [x for x in oc_streams if not x["compressed"] and x["sha256"] not in old_uncompressed]
    if new_uncompressed:
        issue("warning", "new_uncompressed_page_contents",
              objects=len(new_uncompressed), bytes=sum(x["encoded_bytes"] for x in new_uncompressed),
              affected_pages=sorted({n for x in new_uncompressed for n in x["pages"]}),
              note="New or expanded uncompressed page contents; inspect final lossless compression.")
    source_fonts = {x["sha256"] for x in sm["resources"]["font_streams"]}
    new_font_bytes = sum(x["encoded_bytes"] for x in om["resources"]["font_streams"]
                         if x["sha256"] not in source_fonts)
    if new_font_bytes > 5*1024*1024:
        issue("warning", "large_added_font_payload", bytes=new_font_bytes,
              note="Investigation trigger only; inspect used glyphs and subset lifecycle.")
    mapping = page_mapping(state, sm["page_count"])
    source_doc, result_doc = open_document(source), open_document(output)
    try:
        for i in range(len(source_doc)):
            m = mapping.get(i)
            if not m:
                issue("error", "missing_page_mapping", i+1)
                continue
            j = int(m["output_page"])-1
            if not 0 <= j < len(result_doc):
                issue("error", "output_page_missing", i+1)
                continue
            sp, op = source_doc[i], result_doc[j]
            rect = region_for(m, sp)
            sw, sh = sp.get_size()
            ow, oh = op.get_size()
            if abs(rect[2]-rect[0]-sw)>0.1 or abs(rect[3]-rect[1]-sh)>0.1:
                issue("error", "source_region_scaled", i+1)
            expected_size, expected_rect = [2*sw, sh], [0, 0, sw, sh]
            geometry = {"expected_output_size_pt": expected_size, "actual_output_size_pt": [ow, oh],
                        "expected_source_rect": expected_rect, "actual_source_rect": rect,
                        "tolerance_pt": 0.1}
            geometry["passed"] = (abs(ow-2*sw) <= 0.1 and abs(oh-sh) <= 0.1 and
                                   all(abs(a-b) <= 0.1 for a,b in zip(rect, expected_rect)))
            if abs(ow-2*sw) > 0.1 or abs(oh-sh) > 0.1:
                issue("error", "unequal_pane_geometry", i+1, **geometry)
            if any(abs(a-b) > 0.1 for a,b in zip(rect, expected_rect)):
                issue("error", "source_region_misplaced", i+1, **geometry)
            if ow <= rect[2]+1:
                issue("error", "no_right_translation_region", i+1)
            srcchars = displayed_chars(sp)
            dstchars = displayed_chars(op)
            leftchars = [c for c in dstchars if in_rect(c, rect)]
            rightchars = [c for c in dstchars if c["bbox"][0] >= rect[2]]
            source_counter = collections.Counter(c["char"] for c in srcchars)
            left_counter = collections.Counter(c["char"] for c in leftchars)
            if source_counter != left_counter:
                issue("warning", "source_text_layer_changed", i+1,
                      missing_characters=sum((source_counter-left_counter).values()),
                      extra_characters=sum((left_counter-source_counter).values()))
            cjk = [c for c in rightchars if is_cjk(c["char"])]
            if srcchars and not cjk and m.get("kind") != "no-translation-needed":
                issue("warning", "no_searchable_chinese_on_right", i+1)

            pipes = sum(c["char"] == "|" for c in rightchars)
            if pipes >= 12 and cjk:
                issue("warning", "possible_flattened_table", i+1, separators=pipes,
                      note="Many pipe separators; inspect whether table rows/columns became prose.")
            for finding in caption_findings(srcchars, rightchars, m, rect, sh):
                issue("warning", "caption_anchor_displaced", i+1, **finding)
            small = [c for c in cjk if c["font_size"] < 8]
            if small:
                roles = small_text_roles(small, m)
                marginal = set(roles) <= {'header', 'footer'}
                issue('info' if marginal else 'warning',
                      'small_marginal_text' if marginal else 'small_chinese_text', i+1,
                      count=len(small), roles=roles,
                      note='Role/location classification is not visual acceptance; inspect legibility.')
            if any(c["bbox"][2] > ow+0.5 or c["bbox"][3] > oh+0.5 for c in rightchars):
                issue("warning", "text_crosses_output_boundary", i+1)
            si, oi = render_image(sp,dpi,max_pixels), render_image(op,dpi,max_pixels)
            pixels, diff = compare_images(si,oi,rect,dpi,pixel_tolerance,max_changed_ratio)
            if not pixels["passed"]:
                issue("error", "source_visual_changed", i+1, comparison=pixels)
            si.close(); oi.close()
            if diff:
                diff.close()
            # Compare source links by destination AND clickable rectangle; additions are allowed.
            target_map = {a+1: int(b["output_page"]) for a,b in mapping.items()}
            expected_links = []
            for link in sm["pages"][i]["links"]:
                expected = json.loads(json.dumps(link))
                target = expected["target"]
                if target.get("kind") == "internal" and target.get("page") is not None:
                    target["page"] = target_map.get(target["page"], target["page"])
                expected_links.append(canonical_hash(expected))
            actual_links = collections.Counter(canonical_hash(x) for x in om["pages"][j]["links"])
            if collections.Counter(expected_links)-actual_links:
                issue("warning", "source_links_changed", i+1,
                      note="Inspect link rectangles/destinations, especially after coordinate normalization.")
            if om["pages"][j]["annotation_count"] < sm["pages"][i]["annotation_count"]:
                issue("warning", "annotations_removed", i+1)
            pages.append({"source_page": i+1, "output_page": j+1,
                          "source_rect": rect, "source_visual": pixels, "pane_geometry": geometry,
                          "searchable_chinese_characters": len(cjk),
                          "small_chinese_characters": len(small)})
            sp.close(); op.close()
    finally:
        source_doc.close(); result_doc.close()
    expected_bookmarks = [{**b, "page": int(mapping[b["page"]-1]["output_page"])
                           if b["page"] and b["page"]-1 in mapping else b["page"]}
                          for b in sm["bookmarks"]]
    if collections.Counter(map(canonical_hash, expected_bookmarks))-collections.Counter(map(canonical_hash,om["bookmarks"])):
        issue("error", "source_bookmarks_missing_or_changed")
    delta = {k: om["resources"]["encoded_bytes"][k]-v
             for k,v in sm["resources"]["encoded_bytes"].items()}
    delta["unclassified_file_bytes"] = (om["resources"]["unclassified_file_bytes"]-
                                       sm["resources"]["unclassified_file_bytes"])
    return {"schema_version": 1, "tool": "pdf-bilingual-parallel-translate/audit",
            "source": {"sha256": sm["sha256"], "bytes": sm["bytes"], "pages": sm["page_count"]},
            "output": {"sha256": om["sha256"], "bytes": om["bytes"], "pages": om["page_count"]},
            "size_delta_bytes": om["bytes"]-sm["bytes"], "classified_delta_bytes": delta,
            "source_resources": sm["resources"], "output_resources": om["resources"],
            "render_dpi": dpi, "render_method":RENDER_METHOD, "pages": pages, "findings": findings,
            "page_content_streams":{"source":sc_streams,"output":oc_streams},
            "finding_summary":dict(collections.Counter(x["code"] for x in findings)),
            "mechanical_pass": not any(x["severity"]=="error" for x in findings),
            "semantic_review_required": True, "visual_review_required": True,
            "limitations": ["Does not prove translation correctness, reading order, table semantics or label alignment.",
                            "Font size/boundary checks are hints; outlines and wholly clipped text may evade extraction.",
                            "Raster checks cover displayed appearance, not accessibility, layers, forms or script behavior.",
                            "Link matching is conservative for normalized rotation/crop coordinates; verify flagged targets."]}


def content_hash(state):
    keys = ["source", "layout", "glossary", "pages", "issues"]
    if state.get("schema_version") == 2:
        keys.append("document")
    return canonical_hash({k: state.get(k) for k in keys})


def resolve_state_file(base, value):
    if not isinstance(value, str) or not value:
        raise ValueError("Expected a non-empty path in state.")
    p = Path(value)
    return p if p.is_absolute() else base/p


def check_state(state_path, final=False):
    state_path = Path(state_path)
    state = read_json(state_path)
    if not isinstance(state,dict):
        raise ValueError("State must be a JSON object.")
    errors, warnings = [], []
    base = state_path.parent

    def error(code, **extra):
        errors.append({"code": code, **extra})

    if state.get("schema_version") not in (1, 2):
        error("unsupported_state_schema")
    if not isinstance(state.get("layout"), dict):
        error("missing_layout")
    if not isinstance(state.get("glossary"), list):
        error("missing_glossary")
    for term in state.get("glossary", []) if isinstance(state.get("glossary"),list) else []:
        if not isinstance(term,dict) or not term.get("source") or not term.get("target"):
            error("invalid_glossary_entry")

    layout = state.get("layout", {})
    if isinstance(layout, dict):
        builder = layout.get("builder")
        if builder:
            try:
                if sha256_file(resolve_state_file(base,builder["path"])) != builder["sha256"]:
                    error("builder_fingerprint_changed")
            except (KeyError, TypeError, ValueError, OSError) as exc:
                error("builder_unavailable", detail=str(exc))
        elif final:
            error("missing_builder")

        for asset in layout.get("inputs", []):
            try:
                if sha256_file(resolve_state_file(base,asset["path"])) != asset["sha256"]:
                    error("layout_input_fingerprint_changed",path=asset["path"])
            except (KeyError, TypeError, ValueError, OSError) as exc:
                error("layout_input_unavailable",detail=str(exc))
        fonts = layout.get("fonts", [])
        if not isinstance(fonts, list):
            error("invalid_font_registry")
        elif final and not fonts:
            error("missing_font_registry")
        else:
            for font in fonts:
                if not isinstance(font,dict) or not all(font.get(k) for k in ("name","sha256","source","purpose")):
                    error("incomplete_font_record")
    try:
        source = resolve_state_file(base, state["source"]["path"])
        actual_source_sha = sha256_file(source)
        count = len(checked_reader(source).pages)
        if actual_source_sha != state["source"]["sha256"]:
            error("source_fingerprint_changed")
    except (KeyError, ValueError, OSError) as exc:
        error("source_unavailable", detail=str(exc))
        actual_source_sha, count = None, 0
    pages = state.get("pages", [])
    if not isinstance(pages, list):
        pages = []
        error("invalid_pages")
    page_numbers, output_numbers, ids = [], [], set()
    for page in pages:
        if not isinstance(page, dict):
            error("invalid_page_record"); continue
        n = page.get("source_page")
        if type(n) is not int or not 1 <= n <= count:
            error("invalid_source_page", page=n)
        page_numbers.append(n)
        j = page.get("output_page")
        if type(j) is not int or not 1 <= j <= count:
            error("invalid_output_page", page=n)
        output_numbers.append(j)
        rect = page.get("source_rect")
        if not isinstance(rect,list) or len(rect)!=4 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in rect) or rect[2]<=rect[0] or rect[3]<=rect[1]:
            error("invalid_source_rect", page=n)
        expected = page.get("expected_blocks")
        blocks = page.get("blocks")
        if not isinstance(expected,list) or not all(isinstance(x,str) and x for x in expected) or len(expected)!=len(set(expected)):
            error("invalid_block_inventory",page=n); expected=[]
        if not isinstance(blocks,list):
            error("invalid_blocks",page=n); blocks=[]
        actual_ids = []
        if not page.get("inventory_reviewed"):
            (error if final else lambda c,**kw: warnings.append({"code":c,**kw}))("inventory_not_reviewed",page=n)
        if page.get("kind") == "no-translation-needed":
            if not page.get("reason"):
                error("missing_page_exemption_reason",page=n)
        elif page.get("kind") != "translated" or not expected:
            error("missing_translation_inventory",page=n)
        for block in blocks:
            if not isinstance(block,dict):
                error("invalid_block",page=n); continue
            bid = block.get("id")
            if not isinstance(bid,str) or not bid or bid in ids:
                error("invalid_or_duplicate_block_id",page=n,block=bid)
            if not isinstance(bid,str):
                bid = "<invalid>"
            ids.add(bid); actual_ids.append(bid)
            if not isinstance(block.get("source_text"),str) or not block["source_text"].strip():
                error("missing_source_text",page=n,block=bid)
            if not isinstance(block.get("kind"),str):
                error("missing_block_kind",page=n,block=bid)
            bbox = block.get("source_bbox")
            if not isinstance(bbox,list) or len(bbox)!=4 or not all(type(v) in (int,float) and math.isfinite(v) for v in bbox) or bbox[2]<=bbox[0] or bbox[3]<=bbox[1]:
                error("invalid_source_bbox",page=n,block=bid)

            target_bbox = block.get("target_bbox")
            if target_bbox is not None and (not isinstance(target_bbox,list) or len(target_bbox)!=4
                    or not all(type(v) in (int,float) and math.isfinite(v) for v in target_bbox)
                    or target_bbox[2]<=target_bbox[0] or target_bbox[3]<=target_bbox[1]):
                error("invalid_target_bbox",page=n,block=bid)
            if block.get("kind") == "table":
                table = block.get("table",{})
                sr, tr = table.get("source_rows"), table.get("translated_rows")
                if (not isinstance(sr,list) or not sr or not isinstance(tr,list) or len(sr)!=len(tr)
                        or any(not isinstance(row,list) or not row for row in sr)
                        or any(not isinstance(row,list) for row in tr)
                        or [len(row) for row in sr] != [len(row) for row in tr]):
                    error("table_structure_missing_or_changed",page=n,block=bid)
                elif any(not isinstance(a,str) or not isinstance(b,str) or (a.strip() and not b.strip())
                         for ar,br in zip(sr,tr) for a,b in zip(ar,br)):
                    error("table_cell_translation_missing",page=n,block=bid)
            if block.get("kind") in ("caption","figure-label") and not block.get("figure_id"):
                error("figure_anchor_missing",page=n,block=bid)
            status = block.get("status")
            if status not in ("translated","verbatim","pending"):
                error("invalid_block_status",page=n,block=bid)
            if status == "pending":
                (error if final else lambda c,**kw: warnings.append({"code":c,**kw}))("pending_translation",page=n,block=bid)
            elif not isinstance(block.get("translation"),str) or not block["translation"].strip():
                error("missing_translation",page=n,block=bid)
            if status == "verbatim" and not block.get("reason"):
                error("missing_verbatim_reason",page=n,block=bid)
        if collections.Counter(expected) != collections.Counter(actual_ids):
            error("block_inventory_mismatch",page=n)
    if sorted(n for n in page_numbers if type(n) is int) != list(range(1,count+1)):
        error("source_page_coverage_incomplete")
    if sorted(n for n in output_numbers if type(n) is int) != list(range(1,count+1)):
        error("output_page_mapping_not_one_to_one")
    if state.get("schema_version") == 2:
        if not isinstance(state.get("document"), dict) or state["document"].get("source_kind") not in ('original', 'english-original', 'official-chinese', 'generated-translation'):
            error("missing_document_identity")
        for page in pages:
            block_ids = [b.get("id") for b in page.get("blocks", []) if isinstance(b, dict)]
            if page.get("reading_order") != block_ids:
                error("reading_order_missing_or_inconsistent", page=page.get("source_page"))
            ctx = page.get("context_pages", [])
            if not isinstance(ctx, list) or any(type(n) is not int or not 1 <= n <= count for n in ctx):
                error("invalid_context_pages", page=page.get("source_page"))
    try:
        pagination_items(state)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        error("invalid_pagination", detail=str(exc))
    computed_hash = content_hash(state)
    output = state.get("output", {})
    actual_output_sha = None
    if output:
        try:
            outpath = resolve_state_file(base, output["path"])
            actual_output_sha = sha256_file(outpath)
            if actual_output_sha != output.get("sha256"):
                error("output_fingerprint_changed")
            if len(checked_reader(outpath).pages) != count:
                error("output_page_count_changed")
        except (KeyError, ValueError, OSError) as exc:
            error("output_unavailable",detail=str(exc))
    elif final:
        error("missing_final_output")
    qc = state.get("qc", {})
    if not isinstance(qc,dict):
        error("invalid_qc"); qc = {}
    if qc:
        if "migration" in state or qc.get("content_sha256") != computed_hash:
            if validate_relocation(state, state_path, content_hash):
                warnings.append({"code":"verified_path_only_migration",
                                 "note":"Original review retained; no claim of new semantic review."})
            else:
                error("stale_qc_content")
        if qc.get("source_sha256") != actual_source_sha:
            error("stale_qc_source")
        if qc.get("output_sha256") != actual_output_sha or actual_output_sha is None:
            error("stale_qc_output")
    if final:
        for category in ("translation_pages","visual_pages"):
            reviewed = qc.get(category,[])
            if not isinstance(reviewed,list) or any(type(x) is not int for x in reviewed) or sorted(reviewed)!=list(range(1,count+1)):
                error("incomplete_"+category)
        if not qc.get("reviewer") or not qc.get("reviewed_at"):
            error("missing_review_attribution")
        if qc.get("structure") != "passed":
            error("structure_not_passed")
        try:
            report = read_json(resolve_state_file(base,qc["audit_path"]))
            if report.get("tool") != "pdf-bilingual-parallel-translate/audit" or not report.get("mechanical_pass"):
                error("audit_not_passed")
            if (report["source"]["sha256"]!=actual_source_sha or report["output"]["sha256"]!=actual_output_sha):
                error("stale_audit")
            if any(x["severity"]=="warning" for x in report.get("findings",[])) and not qc.get("structure_notes"):
                error("audit_warnings_not_explained")
        except (KeyError, ValueError, OSError) as exc:
            error("audit_unavailable",detail=str(exc))
        for issue in state.get("issues",[]):
            if not isinstance(issue,dict) or issue.get("status") not in ("resolved","retained"):
                error("unresolved_issue",detail=issue)
            elif issue.get("status")=="retained" and not issue.get("note"):
                error("retained_issue_without_explanation",detail=issue)
    if final and state.get("schema_version") == 2:
        errors.extend(validate_reviews(state, state_path))
        try:
            font_report_path = resolve_state_file(base, qc["font_report"]["path"])
            if sha256_file(font_report_path) != qc["font_report"]["sha256"]:
                error("font_report_changed")
            fr = read_json(font_report_path)
            fresh = check_fonts(state_path, resolve_state_file(base, qc["font_assignments"]))
            if fr != fresh or not fresh["mechanical_pass"]:
                error("font_check_not_passed_or_stale")
        except (KeyError, ValueError, OSError) as exc:
            error("font_check_unavailable", detail=str(exc))
    return {"schema_version":2,"tool":"pdf-bilingual-parallel-translate/check-state",
            "state_version":state.get("schema_version"),
            "review_evidence_level":"page-bound-v2" if state.get("schema_version")==2 else "legacy-attestation-v1",
            "quality_certified":False, "mechanical_checks_passed":not errors,
            "computed_content_sha256":computed_hash, "errors":errors,"warnings":warnings,
            "valid":not errors,"final_checks":final,"ready_for_delivery":final and not errors,
            "note":"Checks consistency and recorded review coverage. It cannot attest that a "
                   "person/model actually inspected pages or that translations are correct."}


def save_png(image, path, overwrite=False):
    p = Path(path)
    if p.exists() and not overwrite:
        raise ValueError(f"Output exists; use --overwrite: {p}")
    p.parent.mkdir(parents=True,exist_ok=True)
    # The exclusive file handle also avoids unintended replacement races.
    with p.open("wb" if overwrite else "xb") as f:
        image.save(f,format="PNG")


def render_command(args):
    doc = open_document(args.pdf)
    source = open_document(args.source) if args.source else None
    state = read_json(args.state) if args.state else None
    mapping = page_mapping(state,len(source)) if source else {}
    by_output = {int(v["output_page"])-1:v for v in mapping.values()}
    rows=[]
    try:
        for i in parse_pages(args.pages,len(doc)):
            page=doc[i]; im=render_image(page,args.dpi,args.max_pixels)
            name=f"page-{i+1:04d}.png"
            save_png(im,Path(args.out)/name,args.overwrite)
            row={"output_page":i+1,"image":name,"pixels":list(im.size),
                 "image_sha256":sha256_file(Path(args.out)/name),
                 "pixel_sha256":hashlib.sha256(im.tobytes()).hexdigest()}
            if state and i in by_output:
                row["page_content_sha256"] = page_fingerprint(state, by_output[i]["source_page"])
            if source:
                m=by_output.get(i)
                if m is None:
                    raise ValueError(f"No source mapping for output page {i+1}")
                sp=source[int(m["source_page"])-1]
                sim=render_image(sp,args.dpi,args.max_pixels)
                sn=f"page-{i+1:04d}-source.png"
                save_png(sim,Path(args.out)/sn,args.overwrite)
                comparison,diff=compare_images(sim,im,region_for(m,sp),args.dpi,
                                               args.pixel_tolerance,args.max_changed_ratio)
                row.update({"source_page":m["source_page"],"source_image":sn,"comparison":comparison})
                if diff:
                    dn=f"page-{i+1:04d}-difference.png"
                    save_png(diff,Path(args.out)/dn,args.overwrite)
                    row["difference_image"]=dn;diff.close()
                sim.close();sp.close()
            rows.append(row);im.close();page.close()
    finally:
        doc.close()
        if source:source.close()
    report={"schema_version":1,"tool":"pdf-bilingual-parallel-translate/render",
            "output_sha256":sha256_file(args.pdf),"dpi":args.dpi,"pages":rows,
            "visual_review_completed":False}
    report["settings"] = {"method":RENDER_METHOD, "dpi":args.dpi,
                          "pdfium_version":str(pdfium.PDFIUM_INFO), "annotations":True,
                          "color":"RGB", "background":"white"}
    report["settings_sha256"] = canonical_hash(report["settings"])
    if args.source:report["source_sha256"]=sha256_file(args.source)
    write_json(report,Path(args.out)/"index.json",args.overwrite)
    return report


def main(argv=None):
    if hasattr(sys.stdout,"reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest="command",required=True)
    inspect=subs.add_parser("inspect",help="Read the source PDF and report page/resource baselines.")
    inspect.add_argument("pdf",type=Path)
    inspect.add_argument("--out",type=Path)
    audit_parser=subs.add_parser("audit",help="Compare the original PDF and its bilingual output.")
    audit_parser.add_argument("source",type=Path);audit_parser.add_argument("output",type=Path)
    audit_parser.add_argument("--state",type=Path);audit_parser.add_argument("--out",type=Path)
    render=subs.add_parser("render",help="Render pages and optional source/difference images.")
    render.add_argument("pdf",type=Path);render.add_argument("--out",type=Path,required=True)
    render.add_argument("--source",type=Path);render.add_argument("--state",type=Path)
    render.add_argument("--pages",default="all")
    check=subs.add_parser("check-state",help="Validate recovery data and version-bound review records.")
    check.add_argument("state",type=Path);check.add_argument("--final",action="store_true")
    check.add_argument("--out",type=Path)
    font_check=subs.add_parser("check-fonts",help="Check actual assigned fonts against draw-time text runs.")
    font_check.add_argument("state",type=Path);font_check.add_argument("--assignments",type=Path,required=True)
    font_check.add_argument("--out",type=Path)
    for p in (inspect,audit_parser,render,check,font_check):
        p.add_argument("--password-env",help="Name of an environment variable holding an explicitly supplied password")
        p.add_argument("--overwrite",action="store_true",help="Replace explicitly selected reports/renders only.")
    for p in (audit_parser,render):
        p.add_argument("--dpi",type=int,default=144)
        p.add_argument("--max-pixels",type=int,default=40000000)
        p.add_argument("--pixel-tolerance",type=int,default=16)
        p.add_argument("--max-changed-ratio",type=float,default=0.001)
    args=parser.parse_args(argv)
    global _PASSWORD
    _PASSWORD = os.environ.get(args.password_env) if args.password_env else None
    try:
        if args.password_env and _PASSWORD is None:
            raise ValueError("The named password environment variable is unavailable.")
        if args.command in ("audit","render"):
            if not 36<=args.dpi<=600 or not 0<=args.pixel_tolerance<=255 or not 0<=args.max_changed_ratio<=1 or args.max_pixels<1:
                raise ValueError("Invalid rendering/comparison limits.")
        # Never let --out overwrite an input, even when --overwrite was supplied.
        inputs=[getattr(args,k,None) for k in ("pdf","source","output","state","assignments")]
        dest=getattr(args,"out",None)
        if dest and any(p and Path(p).resolve()==Path(dest).resolve() for p in inputs):
            raise ValueError("Report/render output must not replace an input.")
        if args.command=="inspect":
            report=pdf_metadata(args.pdf)
            failed=bool(report["resources"]["errors"])
        elif args.command=="audit":
            state=read_json(args.state) if args.state else None
            if args.state:
                check_result=check_state(args.state)
                if check_result["errors"]:
                    raise ValueError("Fix state consistency before using it for audit: "+
                                     json.dumps(check_result["errors"],ensure_ascii=False))
                state_source=resolve_state_file(args.state.parent,state["source"]["path"])
                if sha256_file(args.source)!=sha256_file(state_source):
                    raise ValueError("State source does not match audit source.")
            report=audit(args.source,args.output,state,args.dpi,args.pixel_tolerance,
                         args.max_changed_ratio,args.max_pixels)
            failed=not report["mechanical_pass"]
        elif args.command=="render":
            if args.state and not args.source:
                raise ValueError("--state requires --source.")
            if args.state:
                state=read_json(args.state)
                checked=check_state(args.state)
                if checked["errors"]:
                    raise ValueError("Fix state consistency before rendering with it.")
                if state["source"]["sha256"] != sha256_file(args.source):
                    raise ValueError("State source does not match render source.")
            report=render_command(args)
            print(json.dumps({"index":str(args.out/"index.json"),"pages":len(report["pages"]),
                              "visual_review_completed":False},ensure_ascii=False))
            return 0
        elif args.command=="check-fonts":
            report=check_fonts(args.state,args.assignments)
            failed=not report["mechanical_pass"]
        else:
            report=check_state(args.state,args.final)
            failed=not report["valid"]
        write_json(report,getattr(args,"out",None),args.overwrite)
        if args.out:
            print(json.dumps({"report":str(args.out),"mechanical_success":not failed},ensure_ascii=False))
        return 2 if failed else 0
    except Exception as exc:
        print(json.dumps({"error":type(exc).__name__,"message":str(exc)},ensure_ascii=False),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
