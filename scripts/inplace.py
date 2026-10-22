#!/usr/bin/env python3
"""Extract and build source-faithful in-place bilingual pages (state v3)."""
from __future__ import annotations
import argparse
import copy
import io
import json
import math
import os
import re
import sys
from pathlib import Path
import pymupdf as fitz
from workflow import digest, canonical, resolve, pagination_items

METHODS = {'replace', 'cover', 'preserve', 'unresolved'}

def rect(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4 or not all(type(x) in (int, float) and math.isfinite(x) for x in value):
        raise ValueError('Expected four finite rectangle coordinates')
    r = fitz.Rect(value)
    if r.is_empty or r.is_infinite:
        raise ValueError('Rectangle must have positive area')
    return r

def box(r):
    return [round(v, 5) for v in r]

def contains(outer, inner, tolerance=.02):
    return (outer.x0-tolerance <= inner.x0 and outer.y0-tolerance <= inner.y0 and
            outer.x1+tolerance >= inner.x1 and outer.y1+tolerance >= inner.y1)

def selected_pages(value, count):
    if value == 'all':
        return list(range(1, count+1))
    found = set()
    for part in value.split(','):
        ends = part.split('-')
        if len(ends) > 2 or any(not v.isdigit() for v in ends):
            raise ValueError('Pages must be all or one-based selections such as 1,3-5')
        a, b = int(ends[0]), int(ends[-1])
        if not 1 <= a <= b <= count:
            raise ValueError('Page selection outside source')
        found.update(range(a, b+1))
    return sorted(found)

def open_source(source, password=None):
    doc = fitz.open(source)
    if doc.needs_pass and not doc.authenticate(password or ''):
        raise ValueError('A valid explicitly supplied password is required')
    return doc

def relative(path, base):
    return os.path.relpath(Path(path).resolve(), Path(base).resolve()).replace('\\', '/')

def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def geometry(page):
    return {'width': page.rect.width, 'height': page.rect.height,
            'cropbox': box(page.cropbox), 'mediabox': box(page.mediabox),
            'rotation': page.rotation,
            'user_unit': page.parent.xref_get_key(page.xref, 'UserUnit')[1]}

def text_inventory(page, number):
    """Visible-coordinate glyph inventory including hidden OCR and native span grouping."""
    matrix = page.rotation_matrix
    traces = {}
    for trace in page.get_texttrace():
        for c in trace['chars']:
            key = (c[0], round(c[2][0], 3), round(c[2][1], 3))
            traces.setdefault(key, []).append(trace)
    glyphs, blocks = [], []
    flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES
    if next(page.annots(),None) is not None:
        # Annotation appearances are migrated independently, never translated as
        # page content. A display list excludes them from extraction explicitly.
        rotation=page.rotation
        try:
            page.set_rotation(0)
            raw=fitz.TextPage(page.get_displaylist(annots=False).get_textpage(flags=flags)).extractRAWDICT()
        finally:page.set_rotation(rotation)
    else:raw=page.get_text('rawdict',flags=flags)
    for bi, b in enumerate(raw['blocks']):
        if b['type'] != 0:
            continue
        for li, line in enumerate(b['lines']):
            direction = fitz.Point(line['dir']) * fitz.Matrix(matrix.a, matrix.b, matrix.c, matrix.d, 0, 0)
            raw_angle = (-math.degrees(math.atan2(direction.y, direction.x))) % 360
            angle = (round(raw_angle/90)*90) % 360
            orthogonal = abs((raw_angle-angle+180)%360-180) < .01
            for si, span in enumerate(line['spans']):
                ids, letters, bounds, hidden_flags = [], [], [], []
                for ci, c in enumerate(span['chars']):
                    key = (ord(c['c']), round(c['origin'][0], 3), round(c['origin'][1], 3))
                    trace = next(iter(traces.get(key, [])), {})
                    hidden = trace.get('type') == 3 or trace.get('opacity', 1) == 0
                    r = fitz.Rect(c['bbox']) * matrix
                    gid = 'p%d-g%d' % (number, len(glyphs))
                    glyphs.append({'id': gid, 'text': c['c'], 'bbox': box(r),
                                   'origin': list(fitz.Point(c['origin']) * matrix),
                                   'hidden': hidden, 'trace_type': trace.get('type'),
                                   'font': span['font'], 'size': span['size']})
                    ids.append(gid); letters.append(c['c']); bounds.append(r); hidden_flags.append(hidden)
                if not ids or not ''.join(letters).strip():
                    continue
                r = fitz.Rect(bounds[0])
                for br in bounds[1:]:
                    r |= br
                text = ''.join(letters)
                preserve = not any(ch.isalpha() for ch in text)
                hidden = all(hidden_flags)
                method = 'preserve' if preserve else 'unresolved'
                bid = 'p%d-b%s' % (number, canonical([bi,li,si,text,box(r)])[:12])
                blocks.append({'id': bid, 'kind': 'text', 'source_text': text,
                    'source_bbox': box(r), 'glyph_ids': ids, 'source_group':bi, 'source_line':li,
                    'glyph_ranges': [[0,len(ids)]], 'hidden_ocr': hidden,
                    'method': method, 'status': 'verbatim' if preserve else 'pending',
                    'reason': 'Numeric or symbolic source span; confirm during inventory review' if preserve else '',
                    'translation': text if preserve else '', 'allowed_bbox': box(r),
                    'actual_bbox': None, 'font_size': span['size'], 'rotation': angle,
                    'expansion_reason': '', 'cover_bbox': None,
                    'source_angle': raw_angle, 'orthogonal': orthogonal,
                    'color': [((span['color'] >> shift) & 255)/255 for shift in (16,8,0)]})
    # Raw extraction may include whitespace-only spans: retain them in the inventory but
    # exclude them from coverage, since they carry no visible semantic content.
    return glyphs, blocks

def extract(source, state_path, pages='all', overwrite=False, password=None):
    source, state_path = Path(source).resolve(), Path(state_path).resolve()
    if source == state_path:
        raise ValueError('State must not overwrite the original')
    if state_path.exists() and not overwrite:
        raise ValueError('State exists; use --overwrite explicitly')
    doc = open_source(source, password)
    try:
        selected = selected_pages(pages, len(doc))
        state = {'schema_version': 3, 'document': {'source_kind': 'original'},
            'source': {'path': relative(source,state_path.parent), 'sha256':digest(source), 'page_count':len(doc)},
            'layout': {'mode':'inplace', 'fonts':[], 'body_size_pt':10,
                       'coordinate_system':'visible-page-top-left-points',
                       'pagination_strategy': None}, 'glossary':[], 'issues':[], 'pages':[], 'qc':{}}
        for output_number, n in enumerate(selected, 1):
            page = doc[n-1]
            glyphs, blocks = text_inventory(page, n)
            state['pages'].append({'source_page':n, 'output_page':output_number,
                'source_rect':[0,0,page.rect.width,page.rect.height], 'geometry':geometry(page),
                'kind':'translated' if blocks else 'no-translation-needed',
                'reason':'' if blocks else 'No native text found; inspect images and vector outlines before accepting',
                'inventory_reviewed':False, 'glyphs':glyphs, 'blocks':blocks,
                'expected_blocks':[b['id'] for b in blocks], 'reading_order':[b['id'] for b in blocks],
                'context_pages':[], 'visual_text_review':'pending'})
        write_json(state_path,state)
        return {'state':str(state_path),'pages':selected,'schema_version':3}
    finally:
        doc.close()

def selected_glyphs(block, by_id):
    ids = block.get('glyph_ids', [])
    if len(ids) != len(set(ids)) or any(g not in by_id for g in ids):
        raise ValueError('Invalid glyph IDs: '+block['id'])
    ranges = block.get('glyph_ranges', [[0,len(ids)]]) if ids else []
    indices = []
    for start, end in ranges:
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(ids):
            raise ValueError('Invalid glyph range: '+block['id'])
        indices.extend(range(start,end))
    if len(indices) != len(set(indices)):
        raise ValueError('Overlapping glyph ranges: '+block['id'])
    return [by_id[ids[i]] for i in indices]

def effective_glyph_boxes(page,glyphs):
    # Raw span bboxes can use a font-wide ascent (e.g. CambriaMath 50 pt at
    # 9 pt). Trace boxes are tied to the drawn glyph size; keep raw facts intact.
    traces={}
    matrix=page.rotation_matrix
    for trace in page.get_texttrace():
        for code,gid,origin,bbox in trace['chars']:
            p=fitz.Point(origin)*matrix
            traces[(code,round(p.x,3),round(p.y,3))]=box(fitz.Rect(bbox)*matrix)
    return {g['id']:traces.get((ord(g['text']),round(g['origin'][0],3),round(g['origin'][1],3)),g['bbox']) for g in glyphs}

def ligature_carriers(glyphs):
    carriers={}
    previous=None
    for g in glyphs:
        r=fitz.Rect(g['bbox'])
        if not r.is_empty:
            previous=g;continue
        if not g['text'].strip():continue
        if previous and g.get('trace_type') is None and previous['font']==g['font'] and abs(previous['size']-g['size'])<.001:
            p=fitz.Rect(previous['bbox']);x,y=g['origin']
            if p.x0-.02<=x<=p.x1+.02 and p.y0-.02<=y<=p.y1+.02:
                carriers[g['id']]=previous['id']
    return carriers

def validate_page(page, fresh, final=False):
    errors = []
    def fail(message):
        errors.append({'code':'invalid_inplace_state','page':page.get('source_page'),'detail':message})
    if page.get('geometry') != fresh.get('geometry') or page.get('glyphs') != fresh.get('glyphs'):
        fail('Source geometry/glyph inventory changed; re-extract before editing translations')
    by_id = {g['id']:g for g in fresh['glyphs']}
    owned = {}
    try:
        bounds = fitz.Rect(0,0,fresh['geometry']['width'],fresh['geometry']['height'])
        for block in page['blocks']:
            method = block.get('method')
            if method not in METHODS:
                raise ValueError('Unknown method: '+block['id'])
            glyphs = selected_glyphs(block,by_id)
            for g in glyphs:
                if g['id'] in owned:
                    raise ValueError('Glyph assigned twice: '+g['id'])
                owned[g['id']] = method
            allowed = rect(block['allowed_bbox'])
            if not contains(bounds,allowed):
                raise ValueError('Allowed box outside visible page: '+block['id'])
            if not contains(rect(block['source_bbox']),allowed) and not block.get('expansion_reason'):
                raise ValueError('Expanded box requires an explicit adjacent-blank-space reason: '+block['id'])
            actual = block.get('actual_bbox')
            if actual is not None and not contains(allowed,rect(actual)):
                raise ValueError('Actual box exceeds allowed box: '+block['id'])
            if method == 'replace' and block.get('orthogonal') is False:
                raise ValueError('Non-orthogonal native text requires explicit cover treatment: '+block['id'])
            if method == 'replace' and (not glyphs or any(g['hidden'] for g in glyphs)):
                raise ValueError('Replace requires visible native glyphs; hidden OCR needs cover or preserve: '+block['id'])
            if method == 'cover':
                cover = rect(block.get('cover_bbox') or block['source_bbox'])
                if not contains(bounds,cover) or not block.get('reason'):
                    raise ValueError('Cover requires an in-page rectangle and explicit image/outline/OCR reason: '+block['id'])
            if method == 'preserve' and not block.get('reason'):
                raise ValueError('Preserve requires a reason: '+block['id'])
            if method in ('replace','cover') and not str(block.get('translation','')).strip():
                raise ValueError('Missing translation: '+block['id'])
            if final and method == 'unresolved':
                raise ValueError('Unresolved block: '+block['id'])
        carriers=ligature_carriers(fresh['glyphs'])
        for tail,carrier in carriers.items():
            if (owned.get(tail) in ('replace','cover')) != (owned.get(carrier) in ('replace','cover')):
                raise ValueError('Cannot split a ligature between preserve and replacement: '+carrier+' / '+tail)
        unowned = [g['id'] for g in fresh['glyphs'] if g['text'].strip() and g['id'] not in owned]
        if unowned:
            raise ValueError('Unassigned glyphs: '+','.join(unowned[:8]))
    except (ValueError,KeyError,TypeError) as exc:
        fail(str(exc))
    return errors

def validate_state(state, source, password=None, final=False):
    if state.get('schema_version') != 3 or state.get('layout',{}).get('mode') != 'inplace':
        return [{'code':'invalid_inplace_state','detail':'Expected v3 inplace state; use example_build.py explicitly for v1/v2'}]
    errors = []
    if digest(source) != state['source']['sha256']:
        return [{'code':'source_fingerprint_changed'}]
    with open_source(source,password) as doc:
        for page in state['pages']:
            n = page['source_page']
            if not 1 <= n <= len(doc):
                errors.append({'code':'invalid_source_page','page':n}); continue
            glyphs, _ = text_inventory(doc[n-1],n)
            errors.extend(validate_page(page,{'geometry':geometry(doc[n-1]),'glyphs':glyphs},final))
    return errors

STATIC_ANNOTATIONS={'/Highlight','/Underline','/StrikeOut','/Squiggly','/Square','/Circle','/Ink','/Stamp'}
TEXT_MARKUP_ANNOTATIONS={'/Highlight','/Underline','/StrikeOut','/Squiggly'}

def annotation_policy(annotation,page,page_state=None):
    from pypdf.generic import StreamObject
    subtype=str(annotation.get('/Subtype'))
    if subtype not in STATIC_ANNOTATIONS:
        raise ValueError('Unsupported visible annotation type '+subtype+'; no appearance is silently discarded')
    if page.rotation:
        raise ValueError('Rotated-page annotation appearances need a custom migration')
    if any(k in annotation for k in ('/A','/AA','/Popup','/IRT','/OC')):
        raise ValueError('Annotation actions, popup/reply threads or layers need a custom migration')
    appearance=annotation.get('/AP')
    normal=appearance.get_object().get('/N') if appearance else None
    normal=normal.get_object() if hasattr(normal,'get_object') else normal
    if not isinstance(normal,StreamObject) or '/BBox' not in normal:
        raise ValueError('Static annotation requires a single normal /AP/N appearance stream')
    source_rect=fitz.Rect([float(v) for v in annotation['/Rect']])*page.transformation_matrix
    if not contains(page.rect,source_rect):
        raise ValueError('Partly cropped annotation appearance requires explicit clipping support')
    if subtype in TEXT_MARKUP_ANNOTATIONS and page_state:
        by_id={g['id']:g for g in page_state['glyphs']}
        selected={g['id'] for b in page_state['blocks'] if b['method'] in ('replace','cover') for g in selected_glyphs(b,by_id)}
        effective=effective_glyph_boxes(page,page_state['glyphs'])
        if any(g['id'] in selected and source_rect.intersects(fitz.Rect(effective[g['id']])) for g in page_state['glyphs'] if g['text'].strip()):
            raise ValueError('Text-markup annotation touches replaced text; provide a custom translated-anchor appearance')
    return source_rect

def check_interactions(doc, selected, state=None):
    # Text clipping changes following paint operations when removed; refuse it in
    # nested forms too rather than treating its glyphs as ordinary visible text.
    from pypdf import PdfReader
    from pypdf.generic import ContentStream
    reader=PdfReader(io.BytesIO(doc.tobytes()))
    def check_stream(stream,resources,seen):
        if stream is not None:
            for operands,operator in ContentStream(stream,reader).operations:
                if operator==b'Tr' and operands and int(operands[0])>=4:
                    raise ValueError('Text clipping render modes 4-7 are unsupported; refusing to change clipped graphics')
        for ref in resources.get('/XObject',{}).values():
            obj=ref.get_object()
            if obj.get('/Subtype')!='/Form':continue
            key=getattr(ref,'idnum',id(obj))
            if key in seen:continue
            seen.add(key);check_stream(obj,obj.get('/Resources',resources),seen)
    page_states={p['source_page']:p for p in state['pages']} if state else {}
    for n in selected:
        p=reader.pages[n-1];check_stream(p.get_contents(),p.get('/Resources',{}),set())
        for ref in p.get('/Annots',[]):
            annotation=ref.get_object()
            if annotation.get('/Subtype')!='/Link':annotation_policy(annotation,doc[n-1],page_states.get(n))
    # show_pdf_page copies page graphics, not annotations or document structures.
    if doc.embfile_count() or doc.get_ocgs():
        raise ValueError('Attachments/optional-content layers require explicit preservation support; refusing to flatten')
    for n in selected:
        page = doc[n-1]
        if list(page.widgets() or []):
            raise ValueError('Interactive widgets are unsupported on source page %d; refusing to discard them' % n)
        for link in page.get_links():
            if link['kind'] not in (fitz.LINK_URI,fitz.LINK_GOTO):
                raise ValueError('Unsupported link kind on page %d' % n)
            if link['kind'] == fitz.LINK_GOTO and link.get('page',-1)+1 not in selected and not (state and state.get('document',{}).get('delivery_scope')=='sample'):
                raise ValueError('Selected pages exclude a link destination from page %d; include its destination' % n)
    for item in doc.get_toc(simple=False):
        dest = item[3]
        point=dest.get('to')
        if point is not None and not all(math.isfinite(v) for v in point):
            raise ValueError('Nonfinite bookmark axes require a raw-destination custom migration')
        if dest.get('kind',fitz.LINK_GOTO) not in (fitz.LINK_NONE,fitz.LINK_GOTO,fitz.LINK_URI):
            raise ValueError('Unsupported bookmark action; refusing to discard it')

def migrate_raw_links(source_doc,source_path,pdf_bytes,selected,password=None,state=None):
    """Preserve destination modes and nullable axes that get_links cannot represent."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NullObject, FloatObject
    reader=PdfReader(source_path)
    if reader.is_encrypted:reader.decrypt(password or '')
    composed=PdfReader(io.BytesIO(pdf_bytes))
    # append shares cloned resources while avoiding clone_from's source /Size
    # heuristic (direct objects may become additional indirect objects).
    writer=PdfWriter();writer.append(composed,import_outline=False)
    # Clone the original tree: append's outline importer drops no-action headings.
    if composed.trailer["/Root"].get("/Outlines"):
        writer._root_object[NameObject("/Outlines")]=composed.trailer["/Root"]["/Outlines"].clone(writer)
    if composed.metadata:writer.add_metadata(composed.metadata)
    source_numbers={(p.indirect_reference.idnum,p.indirect_reference.generation):i for i,p in enumerate(reader.pages)}
    mapping={n-1:i for i,n in enumerate(selected)}
    transforms={}
    for n in selected:
        p=source_doc[n-1];rotation=p.rotation;rm=p.rotation_matrix
        p.set_rotation(0);tm=p.transformation_matrix;p.set_rotation(rotation)
        transforms[n-1]=tm*rm
    def numeric(value):
        if value is None or isinstance(value,NullObject):return None
        number=float(value)
        if not math.isfinite(number):raise ValueError('Nonfinite raw link coordinate')
        return number
    def number(value):return NullObject() if value is None else FloatObject(value)
    def coordinate(x,y,a,b,offset):
        x,y=numeric(x),numeric(y)
        if (abs(a)>1e-8 and x is None) or (abs(b)>1e-8 and y is None):return None
        return a*(x or 0)+b*(y or 0)+offset
    def destination(value,pane):
        value=value.get_object() if hasattr(value,'get_object') else value
        if isinstance(value,str):
            names=reader.named_destinations
            named=names.get(value) or names.get(value.lstrip('/'))
            if named is None:raise ValueError('Unknown named link destination: '+value)
            value=named.dest_array
        if not isinstance(value,(list,ArrayObject)) or len(value)<2:raise ValueError('Unsupported raw link destination')
        ref=value[0]
        if hasattr(ref,'idnum'):target=source_numbers.get((ref.idnum,ref.generation))
        else:target=int(ref) if isinstance(ref,int) else None
        if target not in mapping:
            if state and state.get('document',{}).get('delivery_scope')=='sample':return None
            raise ValueError('Selected pages exclude raw link destination')
        p=source_doc[target];w,h=p.rect.width,p.rect.height
        m=transforms[target]*fitz.Matrix(1,0,0,1,pane*w,0)*fitz.Matrix(1,0,0,-1,0,h)
        mode=str(value[1]);args=list(value[2:])
        if mode=='/XYZ' and len(args)==3:
            x,y,z=args
            args=[number(coordinate(x,y,m.a,m.c,m.e)),number(coordinate(x,y,m.b,m.d,m.f)),number(numeric(z))]
        elif mode in ('/FitH','/FitBH') and len(args)==1:
            if abs(m.d)>1e-8:args=[number(coordinate(None,args[0],m.b,m.d,m.f))]
            else:
                args=[number(coordinate(None,args[0],m.a,m.c,m.e))]
                mode='/FitBV' if mode=='/FitBH' else '/FitV'
        elif mode in ('/FitV','/FitBV') and len(args)==1:
            if abs(m.a)>1e-8:args=[number(coordinate(args[0],None,m.a,m.c,m.e))]
            else:
                args=[number(coordinate(args[0],None,m.b,m.d,m.f))]
                mode='/FitBH' if mode=='/FitBV' else '/FitH'
        elif mode=='/FitR' and len(args)==4:
            if any(numeric(a) is None for a in args):raise ValueError('Null FitR rectangle unsupported')
            r=fitz.Rect([float(a) for a in args])*m;args=[FloatObject(v) for v in r]
        elif mode in ('/Fit','/FitB') and not args:pass
        else:raise ValueError('Unsupported raw destination mode: '+mode)
        return ArrayObject([writer.pages[mapping[target]].indirect_reference,NameObject(mode),*args])
    page_states={p['source_page']:p for p in state['pages']} if state else {}
    for ps in page_states.values():
        ps.pop('link_mappings',None);ps.pop('omitted_links',None)
    def right_rectangles(n,link_number,source_rect):
        if n not in page_states:return [source_rect]
        ps=page_states[n]
        override=next((v for v in ps.get('link_overrides',[]) if v['source_link']==link_number),None)
        if override:
            if 'target_block' in override:
                block=next((b for b in ps['blocks'] if b['id']==override['target_block']),None)
                if block is None:raise ValueError('Unknown link target_block')
                visible=''.join(re.sub(r'</?(?:sub|sup)>','',block['translation']).split())
                needle=''.join(override.get('target_text','').split())
                occurrence=override.get('occurrence',1)
                if not needle or type(occurrence) is not int or occurrence<1:raise ValueError('Link anchor requires target_text and positive occurrence')
                found=[m.start() for m in re.finditer(re.escape(needle),visible)]
                if len(found)<occurrence:raise ValueError('Link anchor text not found: '+block['id'])
                start=found[occurrence-1];values=block.get('actual_glyph_boxes',[])[start:start+len(needle)]
                if len(values)!=len(needle):raise ValueError('Link anchor glyph positions unavailable')
                union=rect(values[0])
                for value in values[1:]:union|=rect(value)
                values=[box(union)]
            else:values=override.get('right_bboxes') or [override['right_bbox']]
            boxes=[rect(v) for v in values]
            if any(not contains(source_doc[n-1].rect,r) for r in boxes):raise ValueError('Right link override outside pane')
            return boxes
        effective=effective_glyph_boxes(source_doc[n-1],ps['glyphs'])
        linked=[g for g in ps['glyphs'] if g['text'].strip() and source_rect.contains((fitz.Rect(effective[g['id']]).tl+fitz.Rect(effective[g['id']]).br)/2)]
        ids={g['id'] for g in linked}
        affected=[b for b in ps['blocks'] if b['method'] in ('replace','cover') and ids.intersection(b.get('glyph_ids',[]))]
        if not affected:return [source_rect]
        needle=''.join(g['text'] for g in linked if not g['text'].isspace())
        matches=[]
        for block in affected:
            visible=''.join(re.sub(r'</?(?:sub|sup)>','',block['translation']).split())
            boxes=block.get('actual_glyph_boxes',[])
            if len(visible)!=len(boxes):raise ValueError('Actual link glyph mapping incomplete: '+block['id'])
            if needle and visible.count(needle)==1:
                index=visible.index(needle);matches.append(boxes[index:index+len(needle)])
            elif ids.issuperset(g for g in block.get('glyph_ids',[]) if next((v['text'].strip() for v in ps['glyphs'] if v['id']==g),False)):
                matches.append(boxes)
        if len(matches)!=1 or not matches[0]:
            raise ValueError('Right link text cannot be mapped uniquely on page %d link %d; provide page.link_overrides right_bbox' % (n,link_number))
        union=fitz.Rect(matches[0][0])
        for value in matches[0][1:]:union|=fitz.Rect(value)
        return [union]
    for n in selected:
        p=source_doc[n-1];w,h=p.rect.width,p.rect.height
        link_number=-1
        for ref in reader.pages[n-1].get('/Annots',[]):
            annotation=ref.get_object()
            if annotation.get('/Subtype')!='/Link':continue
            link_number+=1
            raw_action=annotation.get('/A')
            raw_action=raw_action.get_object() if raw_action else {}
            raw_dest=raw_action.get('/D') if raw_action.get('/S')=='/GoTo' else annotation.get('/Dest')
            if raw_dest is not None and destination(raw_dest,0) is None:
                page_states.get(n,{}).setdefault('omitted_links',[]).append({'source_link':link_number,'reason':'Destination outside explicitly selected sample'})
                continue
            if annotation.get('/AP'):raise ValueError('Link appearance streams require explicit preservation support')
            for pane in (0,1):
                copied=DictionaryObject()
                for key,value in annotation.items():
                    if key not in ('/P','/Rect','/A','/Dest','/QuadPoints','/StructParent','/NM'):
                        copied[NameObject(key)]=value.clone(writer) if hasattr(value,'clone') else value
                m=transforms[n-1]*fitz.Matrix(1,0,0,1,pane*w,0)*fitz.Matrix(1,0,0,-1,0,h)
                source_rect=fitz.Rect([float(a) for a in annotation['/Rect']])*transforms[n-1]
                destination_rects=right_rectangles(n,link_number,source_rect) if pane else [source_rect]
                if pane and n in page_states:
                    page_states[n].setdefault('link_mappings',[]).append({'source_link':link_number,'source_bbox':box(source_rect),'right_bboxes':[box(r) for r in destination_rects],
                        'visible_border':bool((annotation.get('/Border') and len(annotation['/Border'])>=3 and float(annotation['/Border'][2])>0) or (annotation.get('/BS') and float(annotation['/BS'].get('/W',0))>0))})
                visible_to_pdf=fitz.Matrix(1,0,0,-1,pane*w,h)
                copied[NameObject('/Rect')]=ArrayObject([FloatObject(v) for v in destination_rects[0]*visible_to_pdf])
                if '/QuadPoints' in annotation and not pane:
                    values=annotation['/QuadPoints'];points=[]
                    for j in range(0,len(values),2):
                        point=fitz.Point(float(values[j]),float(values[j+1]))*m;points.extend([FloatObject(point.x),FloatObject(point.y)])
                    copied[NameObject('/QuadPoints')]=ArrayObject(points)
                action=annotation.get('/A')
                if action:
                    action=action.get_object()
                    if action.get('/S')=='/URI':copied[NameObject('/A')]=action.clone(writer)
                    elif action.get('/S')=='/GoTo':copied[NameObject('/Dest')]=destination(action['/D'],pane)
                    else:raise ValueError('Unsupported raw link action')
                elif '/Dest' in annotation:copied[NameObject('/Dest')]=destination(annotation['/Dest'],pane)
                else:raise ValueError('Link has no supported destination')
                writer.add_annotation(mapping[n-1],copied)
                for extra_rect in destination_rects[1:]:
                    extra=DictionaryObject(copied)
                    extra[NameObject('/Rect')]=ArrayObject([FloatObject(v) for v in extra_rect*visible_to_pdf])
                    writer.add_annotation(mapping[n-1],extra)
    static_count=0
    for n in selected:
        p=source_doc[n-1];w,h=p.rect.width,p.rect.height
        if n in page_states:page_states[n]['annotation_mappings']=[]
        for annotation_number,ref in enumerate(reader.pages[n-1].get('/Annots',[])):
            annotation=ref.get_object()
            if annotation.get('/Subtype')=='/Link':continue
            source_rect=annotation_policy(annotation,p,page_states.get(n))
            for pane in (0,1):
                copied=DictionaryObject()
                m=transforms[n-1]*fitz.Matrix(1,0,0,1,pane*w,0)*fitz.Matrix(1,0,0,-1,0,h)
                for key,value in annotation.items():
                    if key not in ('/P','/Rect','/QuadPoints','/InkList','/NM'):
                        copied[NameObject(key)]=value.clone(writer) if hasattr(value,'clone') else value
                copied[NameObject('/Rect')]=ArrayObject([FloatObject(v) for v in fitz.Rect([float(v) for v in annotation['/Rect']])*m])
                def points(values):
                    result=[]
                    for j in range(0,len(values),2):
                        point=fitz.Point(float(values[j]),float(values[j+1]))*m
                        result.extend([FloatObject(point.x),FloatObject(point.y)])
                    return ArrayObject(result)
                if '/QuadPoints' in annotation:copied[NameObject('/QuadPoints')]=points(annotation['/QuadPoints'])
                if '/InkList' in annotation:copied[NameObject('/InkList')]=ArrayObject([points(v) for v in annotation['/InkList']])
                writer.add_annotation(mapping[n-1],copied);static_count+=1
            if n in page_states:
                page_states[n]['annotation_mappings'].append({'source_annotation':annotation_number,
                    'subtype':str(annotation['/Subtype']),'source_bbox':box(source_rect),
                    'right_bbox':box(source_rect),'appearance':'preserved-normal-stream'})
    # Consolidate page instructions so tiny q/Q wrapper streams are compressed
    # too; image streams remain untouched. Drop their now-unreferenced fragments.
    for page in writer.pages:page.compress_content_streams()
    writer.compress_identical_objects(remove_duplicates=True,remove_unreferenced=True)
    buf=io.BytesIO();writer.write(buf);return buf.getvalue()

def load_fonts(state,state_path):
    from fontTools.ttLib import TTFont
    fonts = {}
    for i, reg in enumerate(state['layout'].get('fonts', [])):
        name = reg['name']
        if name in fonts:
            raise ValueError('Duplicate font registry name')
        path = resolve(state_path.parent,reg['source']).resolve()
        if digest(path) != reg['sha256']:
            raise ValueError('Font fingerprint changed: '+name)
        tt = TTFont(path,fontNumber=reg.get('face_index',0),recalcTimestamp=False)
        cmap = tt.getBestCmap() or {}
        coverage = {u for u,g in cmap.items() if tt.getGlyphID(g)}
        buf=io.BytesIO();tt.save(buf);tt.close()
        data=buf.getvalue()
        bounds_font=TTFont(io.BytesIO(data),recalcTimestamp=False)
        glyph_set=bounds_font.getGlyphSet()
        font=fitz.Font(fontbuffer=data)
        fonts[name]={'font':font,'data':data,'coverage':coverage,'alias':'Bilingual%d'%i,
                     'glyph_set':glyph_set,'cmap':cmap,'units':bounds_font['head'].unitsPerEm,'bounds_cache':{},'bounds_font':bounds_font}
        reg['source']=relative(path,state_path.parent)
    return fonts

def ink_bounds(font,codepoint):
    # MuPDF glyph_bbox may return the font-wide box; measure the actual outline.
    from fontTools.pens.boundsPen import BoundsPen
    cache=font['bounds_cache']
    if codepoint not in cache:
        pen=BoundsPen(font['glyph_set'])
        font['glyph_set'][font['cmap'][codepoint]].draw(pen)
        cache[codepoint]=fitz.Rect([v/font['units'] for v in (pen.bounds or (0,0,0,0))])
    return cache[codepoint]

def _layout_text_once(block,fonts):
    if not fonts:
        raise ValueError('Register a permitted font with source/hash before translating')
    size=block.get('font_size',10)
    if type(size) not in (int,float) or not math.isfinite(size) or size<=0:
        raise ValueError('Invalid font size: '+block['id'])
    preferred=block.get('font',next(iter(fonts)))
    if preferred not in fonts:
        raise ValueError('Unknown preferred font: '+preferred)
    candidates=[preferred]+[f for f in fonts if f!=preferred]
    rotation=block.get('rotation',0)
    if rotation not in (0,90,180,270):
        raise ValueError('Text rotation must be 0,90,180,270')
    allowed=rect(block['allowed_bbox'])
    width,height=(allowed.width,allowed.height) if rotation in (0,180) else (allowed.height,allowed.width)
    chars=[]
    mode=None
    styled=[]
    for part in re.split(r'(<[^>]*>)',block['translation']):
        if part.startswith('<') and part.endswith('>'):
            if part in ('<sub>','<sup>') and mode is None:
                mode=part[1:-1]
            elif mode and part=='</'+mode+'>':
                mode=None
            else:raise ValueError('Only balanced non-nested sub/sup markup is supported: '+block['id'])
            continue
        scale=.7 if mode else 1.0
        shift=(.25 if mode=='sub' else -.35 if mode=='sup' else 0)*size
        styled.extend((ch,scale,shift) for ch in part)
    if mode:raise ValueError('Unclosed sub/sup markup: '+block['id'])
    for ch,scale,shift in styled:
        name=next((f for f in candidates if ch.isspace() or ord(ch) in fonts[f]['coverage']),None)
        if name is None:
            raise ValueError('Missing glyph U+%04X in %s'%(ord(ch),block['id']))
        font=fonts[name]['font']
        chars.append((ch,name,font.glyph_advance(ord(ch))*size*scale if ch!='\n' else 0,scale,shift))
    ascent=max(fonts[n]['font'].ascender*size*scale-shift for c,n,w,scale,shift in chars)
    descent=max(-fonts[n]['font'].descender*size*scale+shift for c,n,w,scale,shift in chars)
    leading=block.get('leading',max(size*1.2,ascent+descent))
    if leading<ascent+descent-.01:
        raise ValueError('Leading overlaps glyph extents: '+block['id'])
    lines=[[]];lengths=[0.0]
    # Keep English words/model numbers and CJK closing punctuation together.
    # Only a token wider than the entire line may fall back to glyph wrapping.
    closing='，。；：！？、）】》〉」』〕］％,.;:!?%)]}'
    opening='（【《〈「『〔［([{'
    tokens=[]
    for char in chars:
        ch=char[0]
        word=bool(re.fullmatch(r'[A-Za-z0-9_./+%°µΩ−-]',ch))
        if tokens and ch!='\n' and tokens[-1][-1][0]!='\n' and (
                ch in closing or tokens[-1][-1][0] in opening or
                (word and all(re.fullmatch(r'[A-Za-z0-9_./+%°µΩ−-]',v[0]) for v in tokens[-1]))):
            tokens[-1].append(char)
        else:tokens.append([char])
    for token in tokens:
        if token[0][0]=='\n':
            lines[-1].extend(token);lines.append([]);lengths.append(0);continue
        token_width=sum(c[2] for c in token)
        chunks=[token] if token_width<=width+.001 else [[c] for c in token]
        for chunk in chunks:
            chunk_width=sum(c[2] for c in chunk)
            if chunk_width>width+.001:
                raise ValueError('Block overflow (single glyph): '+block['id'])
            if lines[-1] and lengths[-1]+chunk_width>width+.001:
                lines.append([]);lengths.append(0)
            lines[-1].extend(chunk);lengths[-1]+=chunk_width
    used_height=ascent+descent+(len(lines)-1)*leading
    if used_height>height+.01:
        raise ValueError('Block overflow: %s needs %.2f pt, allowed %.2f; edit explicit adjacent blank box or font size'%(block['id'],used_height,height))
    def transform(x,y):
        if rotation==0:return fitz.Point(allowed.x0+x,allowed.y0+y)
        if rotation==90:return fitz.Point(allowed.x0+y,allowed.y1-x)
        if rotation==180:return fitz.Point(allowed.x1-x,allowed.y1-y)
        return fitz.Point(allowed.x1-y,allowed.y0+x)
    points=[transform(x,y) for x,y in [(0,0),(max(lengths),0),(0,used_height),(max(lengths),used_height)]]
    actual=fitz.Rect(min(p.x for p in points),min(p.y for p in points),max(p.x for p in points),max(p.y for p in points))
    glyph_boxes=[]
    for line_num,line in enumerate(lines):
        x=0
        for ch,name,advance,scale,shift in line:
            if not ch.isspace():
                # Use actual font glyph bounds instead of whole allowed rectangles.
                gb=ink_bounds(fonts[name],ord(ch))
                xy=[transform(x+gb.x0*size*scale,ascent+line_num*leading+shift-gb.y1*size*scale),
                    transform(x+gb.x1*size*scale,ascent+line_num*leading+shift-gb.y0*size*scale)]
                glyph_boxes.append(box(fitz.Rect(min(p.x for p in xy),min(p.y for p in xy),max(p.x for p in xy),max(p.y for p in xy))))
            x+=advance
    return lines,leading,ascent,transform,box(actual),preferred,glyph_boxes

def layout_text(block,fonts):
    maximum=block.get('font_size',10)
    minimum=block.get('font_size_min')
    if minimum is None:minimum=maximum
    step=block.get('font_size_step',.25)
    if (type(minimum) not in (int,float) or not math.isfinite(minimum) or minimum<=0 or minimum>maximum
            or type(step) not in (int,float) or not math.isfinite(step) or step<=0):
        raise ValueError('Invalid bounded font fitting settings: '+block['id'])
    sizes=[max(minimum,maximum-i*step) for i in range(math.ceil((maximum-minimum)/step)+1)]
    for size in sizes:
        try:
            value=_layout_text_once({**block,'font_size':size},fonts)
            block['actual_font_size']=size
            block['layout_lines']=[''.join(c[0] for c in line) for line in value[0]]
            block['actual_glyph_boxes']=value[-1]
            return value
        except ValueError as exc:
            if 'overflow' not in str(exc) or size==minimum:raise
    raise ValueError('Block overflow: '+block['id'])

class CollisionIndex:
    """Small spatial grid; avoids quadratic PDF glyph/rectangle allocation."""
    def __init__(self):self.cells={};self.items=[]
    def cells_for(self,r):
        for x in range(math.floor(r.x0/32),math.floor(r.x1/32)+1):
            for y in range(math.floor(r.y0/32),math.floor(r.y1/32)+1):yield x,y
    def add(self,kind,identifier,value):
        r=fitz.Rect(value)
        if r.is_empty:return
        key=len(self.items);self.items.append((kind,identifier,r))
        for cell in self.cells_for(r):self.cells.setdefault(cell,[]).append(key)
    def intersections(self,value,threshold=.02):
        r=fitz.Rect(value);seen=set()
        for cell in self.cells_for(r):
            for key in self.cells.get(cell,[]):
                if key in seen:continue
                seen.add(key);kind,identifier,other=self.items[key]
                if (r&other).get_area()>threshold:yield kind,identifier

def verify_draw_collisions(block,boxes,index):
    conflicts=set()
    for value in boxes:
        for kind,other in index.intersections(value):
            if kind=='cover' and other==block['id']:continue
            description={'preserved':'Translation overlaps preserved glyph',
                         'translation':'Translations overlap','cover':'Translation overlaps another cover'}[kind]
            conflicts.add(description+': '+block['id']+' / '+other)
    return sorted(conflicts)


def build(source,state_path,output,pages='all',overwrite=False,password=None):
    source,state_path,output=map(lambda p:Path(p).resolve(),(source,state_path,output))
    destinations=[output,output.with_suffix('.state.json'),output.with_suffix('.font-runs.json')]
    if source in destinations or state_path in destinations:
        raise ValueError('Output must not overwrite source or authoring state')
    if any(p.exists() for p in destinations) and not overwrite:
        raise ValueError('Output exists; use --overwrite explicitly')
    state=copy.deepcopy(json.loads(state_path.read_text(encoding='utf-8')))
    errors=validate_state(state,source,password,False)
    if errors:raise ValueError(json.dumps(errors,ensure_ascii=False))
    dependencies=[]
    for item in state['layout'].get('inputs',[]):
        dependency=resolve(state_path.parent,item['path']).resolve()
        if digest(dependency)!=item['sha256']:raise ValueError('External input fingerprint changed: '+item['path'])
        if dependency in destinations:raise ValueError('Output must not overwrite a declared dependency')
        dependencies.append({**item,'path':relative(dependency,output.parent)})
    src=open_source(source,password)
    out=fitz.open()
    try:
        available={p['source_page']:p for p in state['pages']}
        selected=sorted(available) if pages=='all' else selected_pages(pages,len(src))
        if any(n not in available for n in selected):
            raise ValueError('Selected page missing from state')
        state['pages']=[available[n] for n in selected]
        for p in state['pages']:
            errors=validate_page(p,p,True)
            if errors:raise ValueError(json.dumps(errors,ensure_ascii=False))
        check_interactions(src,selected,state)
        fonts=load_fonts(state,state_path)
        labels=dict(pagination_items(state))
        build_errors=[]
        runs=[];saved_links={n:src[n-1].get_links() for n in selected};toc=src.get_toc(simple=False)
        # Capture source rotation before zeroing it. show_pdf_page does not account for
        # the source page Rotate entry; an explicit inverse rotation is required.
        for j,n in enumerate(selected):
            pstate=available[n];pstate['output_page']=j+1
            original=src[n-1];w,h=original.rect.width,original.rect.height;rotation=original.rotation
            effective_boxes=effective_glyph_boxes(original,pstate['glyphs'])
            original.set_rotation(0)
            page=out.new_page(width=2*w,height=h)
            page_fonts=set()
            if original.get_contents():
                page.show_pdf_page(fitz.Rect(0,0,w,h),src,n-1,rotate=-rotation)
                page.show_pdf_page(fitz.Rect(w,0,2*w,h),src,n-1,rotate=-rotation)
            by_id={g['id']:g for g in pstate['glyphs']}
            pstate['redaction_regions']=[]
            deleted=set();masks=[];carriers=ligature_carriers(pstate['glyphs'])
            for b in pstate['blocks']:
                if b['method'] not in ('replace','cover'):continue
                glyphs=selected_glyphs(b,by_id)
                for g in glyphs:
                    if not g['text'].strip():continue
                    effective=by_id[carriers[g['id']]] if g['id'] in carriers else g
                    r=rect(effective_boxes[effective['id']]);pstate['redaction_regions'].append(box(r));cx=(r.x0+r.x1)/2;cy=(r.y0+r.y1)/2
                    # A small interior box triggers native text removal without
                    # blanking colored backgrounds, curves, images or neighbor text.
                    mask=fitz.Rect(cx-.01,cy-.01,cx+.01,cy+.01)
                    masks.append((g['id'],mask));deleted.add(g['id'])
            protected_index=CollisionIndex()
            for g in pstate['glyphs']:
                if g['id'] not in deleted and g['text'].strip():protected_index.add('preserved',g['id'],effective_boxes[g['id']])
            # Merge adjacent center masks only when the union cannot touch retained
            # text. This reduces annotation operations without broad page erasure.
            merged=[]
            for gid,mask in masks:
                if merged:
                    previous=merged[-1][1];candidate=previous|mask
                    horizontal=abs(previous.y0-mask.y0)<.001 and 0<=mask.x0-previous.x1<20
                    vertical=abs(previous.x0-mask.x0)<.001 and 0<=mask.y0-previous.y1<20
                    if (horizontal or vertical) and not list(protected_index.intersections(candidate,0)):
                        merged[-1]=(merged[-1][0]+','+gid,candidate);continue
                merged.append((gid,mask))
            for gid,mask in merged:
                collisions=[identifier for kind,identifier in protected_index.intersections(mask,0)]
                if collisions:build_errors.append({'page':n,'block':'redaction','glyph':gid,'detail':'Redaction mask intersects preserved glyphs: '+','.join(collisions)})
                page.add_redact_annot(mask+fitz.Rect(w,0,w,0),fill=False,cross_out=False)
            if masks:
                page.apply_redactions(images=0,graphics=0,text=0)
            collision_index=CollisionIndex()
            for g in pstate['glyphs']:
                if g['id'] not in deleted and not g['hidden'] and g['text'].strip():collision_index.add('preserved',g['id'],effective_boxes[g['id']])
            covers=[(b['id'],rect(b.get('cover_bbox') or b['source_bbox'])) for b in pstate['blocks'] if b['method']=='cover']
            for identifier,cover in covers:collision_index.add('cover',identifier,cover)
            draw_blocks=list(pstate['blocks'])
            if n in labels:
                label=labels[n]
                target=rect(label['target_bbox'])
                allowed=[target.x0-w,target.y0,target.x1-w,target.y1]
                if not contains(fitz.Rect(0,0,w,h),rect(allowed)):raise ValueError('Page label outside Chinese pane')
                draw_blocks.append({**label,'method':'label','translation':label['text'],'allowed_bbox':allowed})
            for b in draw_blocks:
                b['status']='verbatim' if b['method']=='preserve' else 'translated'
                if b['method']=='preserve':
                    b['actual_bbox']=None;b['target_bbox']=None;continue
                if b['method']=='cover':
                    cover=rect(b.get('cover_bbox') or b['source_bbox'])
                    protected=[g['id'] for g in pstate['glyphs'] if g['id'] not in deleted and not g['hidden'] and g['text'].strip() and cover.intersects(fitz.Rect(effective_boxes[g['id']]))]
                    if protected:build_errors.append({'page':n,'block':b['id'],'detail':'Cover intersects preserved native text: '+','.join(protected)})
                    page.draw_rect(cover+fitz.Rect(w,0,w,0),color=None,fill=(1,1,1),overlay=True)
                try:
                    lines,leading,ascent,transform,actual,preferred,glyph_boxes=layout_text(b,fonts)
                except ValueError as exc:
                    build_errors.append({'page':n,'block':b['id'],'detail':str(exc)});continue
                for detail in verify_draw_collisions(b,glyph_boxes,collision_index):
                    build_errors.append({'page':n,'block':b['id'],'detail':detail})
                for glyph_box in glyph_boxes:collision_index.add('translation',b['id'],glyph_box)
                b['actual_bbox']=actual;b['target_bbox']=[actual[0]+w,actual[1],actual[2]+w,actual[3]]
                if b['method']=='label':
                    pstate['pagination'].update(target_bbox=b['target_bbox'],actual_font_size=b['actual_font_size'],actual_glyph_boxes=glyph_boxes)
                for line_num,line in enumerate(lines):
                    advance=0
                    for ch,name,char_width,scale,shift in line:
                        record={'page':n,'block':b['id'],'font':name,'text':ch,'font_size':b['actual_font_size']*scale,'baseline_shift':shift}
                        if name!=preferred:record['fallback_from']=preferred
                        if runs and all(runs[-1].get(k)==record.get(k) for k in ('page','block','font','fallback_from','font_size','baseline_shift')):runs[-1]['text']+=ch
                        else:runs.append(record)
                        if ch!='\n':
                            point=transform(advance,ascent+line_num*leading+shift);point.x+=w
                            font=fonts[name]
                            if name not in page_fonts:
                                page.insert_font(fontname=font['alias'],fontbuffer=font['data']);page_fonts.add(name)
                            page.insert_text(point,ch,fontname=font['alias'],fontsize=b['actual_font_size']*scale,
                                             rotate=b.get('rotation',0),color=(0,0,0) if b['method']=='cover' else tuple(b.get('color',(0,0,0))),overlay=True)
                            advance+=char_width
            original.set_rotation(rotation)
        if build_errors:raise ValueError(json.dumps({'layout_conflicts':build_errors},ensure_ascii=False))
        mapping={n-1:j for j,n in enumerate(selected)}
        new_toc=[]
        for level,title,n,dest in toc:
            if dest.get('kind')==fitz.LINK_NONE:
                new_toc.append([level,title,-1,{'kind':fitz.LINK_NONE}]);continue
            if dest.get('kind')==fitz.LINK_URI:
                new_toc.append([level,title,-1,dest]);continue
            if n in selected:
                d={k:v for k,v in dest.items() if k not in ('xref','id')};d['page']=mapping[n-1]
                new_toc.append([level,title,mapping[n-1]+1,d])
        # A subset may omit ancestor bookmarks. Rebase only retained hierarchy.
        previous=0
        for entry in new_toc:
            entry[0]=min(entry[0],previous+1);previous=entry[0]
        if new_toc:out.set_toc(new_toc)
        state['layout']['omitted_bookmarks_for_unselected_pages']=len(toc)-len(new_toc)
        out.set_metadata(src.metadata)
        out.subset_fonts()
        output.parent.mkdir(parents=True,exist_ok=True)
        # Compress newly composed non-image streams without re-encoding original images/masks.
        for xref in range(1,out.xref_length()):
            if out.xref_is_stream(xref) and out.xref_get_key(xref,'Subtype')[1] != '/Image':
                out.update_stream(xref,out.xref_stream(xref),compress=True)
        data=out.tobytes(garbage=4,deflate=False,no_new_id=True)
        data=migrate_raw_links(src,source,data,selected,password,state)
        output.write_bytes(data)
        state['source']['path']=relative(source,output.parent)
        state['output']={'path':output.name,'sha256':digest(output)}
        for reg in state['layout']['fonts']:
            reg['source']=relative(resolve(state_path.parent,reg['source']),output.parent)
        state['layout']['builder']={'path':relative(__file__,output.parent),'sha256':digest(__file__)}
        helper=Path(__file__).with_name('workflow.py')
        dependencies=[d for d in dependencies if resolve(output.parent,d['path']).resolve()!=helper.resolve()]
        state['layout']['inputs']=dependencies+[{'path':relative(helper,output.parent),'sha256':digest(helper)}]
        state['layout']['runtime']={'pymupdf':fitz.VersionBind}
        state['qc']={}
        write_json(destinations[1],state)
        write_json(destinations[2],{'schema_version':1,'output_sha256':state['output']['sha256'],'runs':runs})
        return {'output':str(output),'state':str(destinations[1]),'assignments':str(destinations[2]),'pages':selected}
    finally:
        src.close();out.close()

def main(argv=None):
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for command in ('extract','build'):
        p=sub.add_parser(command);p.add_argument('--source',required=True);p.add_argument('--state',required=True)
        p.add_argument('--pages',default='all');p.add_argument('--overwrite',action='store_true');p.add_argument('--password-env')
        if command=='build':p.add_argument('--output',required=True)
    a=parser.parse_args(argv)
    password=os.environ.get(a.password_env) if a.password_env else None
    try:
        if a.password_env and password is None:raise ValueError('Password environment variable unavailable')
        if a.command=='extract':result=extract(a.source,a.state,a.pages,a.overwrite,password)
        else:result=build(a.source,a.state,a.output,a.pages,a.overwrite,password)
        print(json.dumps(result,ensure_ascii=False));return 0
    except Exception as exc:
        print(json.dumps({'error':type(exc).__name__,'message':str(exc)},ensure_ascii=False));return 1

if __name__=='__main__':
    raise SystemExit(main())
