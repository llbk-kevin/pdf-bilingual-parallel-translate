#!/usr/bin/env python3
"""Extract and build source-faithful in-place bilingual pages (state v3)."""
from __future__ import annotations
import io
import json
import math
import os
import re
import sys
import tempfile
import time
from collections import defaultdict
from contextlib import closing
from pathlib import Path
import pymupdf as fitz
from workflow import digest, canonical, resolve, pagination_items, state_header_error, valid_rectangle

from resources import WorkerBudget, register_worker, peak_memory, worker_request

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
        doc.close()
        raise ValueError('password_required: A valid explicitly supplied password is required')
    return doc

def relative(path, base):
    target, root = Path(path).resolve(), Path(base).resolve()
    if target.drive.lower() != root.drive.lower():
        return target.as_posix()
    return os.path.relpath(target, root).replace('\\', '/')

def write_compact_state(stream, state):
    """Keep the fast JSON encoder, bounding its output to one page at a time."""
    encode = json.JSONEncoder(ensure_ascii=False, separators=(',', ':')).encode
    stream.write('{')
    for index, (key, value) in enumerate(state.items()):
        if index:
            stream.write(',')
        stream.write(encode(key) + ':')
        if key == 'pages' and isinstance(value, list):
            stream.write('[')
            for page_index, page in enumerate(value):
                if page_index:
                    stream.write(',')
                stream.write(encode(page))
            stream.write(']')
        else:
            stream.write(encode(value))
    stream.write('}\n')


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    compact = isinstance(value, dict) and value.get('schema_version') == 3 and 'layout' in value
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name + '.', suffix='.tmp')
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            if compact:
                write_compact_state(stream, value)
            else:
                stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)

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

def _extract_page(doc, n, output_number):
    page = doc[n-1]
    glyphs, blocks = text_inventory(page, n)
    return {'source_page':n, 'output_page':output_number,
            'source_rect':[0,0,page.rect.width,page.rect.height], 'geometry':geometry(page),
            'kind':'translated' if blocks else 'no-translation-needed',
            'reason':'' if blocks else 'No native text found; inspect images and vector outlines before accepting',
            'inventory_reviewed':False, 'glyphs':glyphs, 'blocks':blocks,
            'expected_blocks':[b['id'] for b in blocks], 'reading_order':[b['id'] for b in blocks],
            'context_pages':[], 'visual_text_review':'pending'}


_extract_worker_doc = None


def _init_extract_worker(source, password, database, lease):
    global _extract_worker_doc
    register_worker(database, lease)
    _extract_worker_doc = open_source(source, password)


def _extract_pages_task(rows):
    started = time.process_time()
    pages = [_extract_page(_extract_worker_doc, n, output_number) for output_number, n in rows]
    return {'pages':pages, 'worker_cpu_seconds':time.process_time()-started, 'worker_peak_bytes':peak_memory()}


def extract(source, state_path, pages='all', overwrite=False, password=None, *,
            profile='practical', workers='auto'):
    source, state_path = Path(source).resolve(), Path(state_path).resolve()
    if source == state_path:
        raise ValueError('State must not overwrite the original')
    if state_path.exists() and not overwrite:
        raise ValueError('State exists; use --overwrite explicitly')
    if profile not in ('practical', 'strict'):
        raise ValueError('Expected practical or strict review profile')
    doc = open_source(source, password)
    try:
        selected = selected_pages(pages, len(doc))
        state = {'schema_version': 3, 'document': {'source_kind': 'original'},
            'source': {'path': relative(source,state_path.parent), 'sha256':digest(source), 'page_count':len(doc)},
            'layout': {'mode':'inplace', 'review_profile':profile, 'fonts':[], 'body_size_pt':10,
                       'coordinate_system':'visible-page-top-left-points',
                       'pagination_strategy': None}, 'glossary':[], 'issues':[], 'pages':[], 'qc':{}}
        rows = list(enumerate(selected, 1))
        worker_request(workers)
        candidates = {rows[0], rows[len(rows)//2], rows[-1]}
        sample = max(candidates, key=lambda row: (doc[row[1]-1].rect.get_area(), len(doc[row[1]-1].get_text())))
        metrics = []
        with WorkerBudget(1, 1, peak_memory(), 'extract-sample') as budget:
            started = time.process_time()
            state['pages'] = [_extract_page(doc, sample[1], sample[0])]
            budget.record({'worker_cpu_seconds':time.process_time()-started, 'worker_peak_bytes':peak_memory()})
            metrics.append(budget.report())
        remaining = [row for row in rows if row != sample]
        if remaining:
            with WorkerBudget(workers, len(remaining), peak_memory(), 'extract',
                              parallel_hint=max(1,math.ceil(metrics[0]['worker_cpu_seconds']*len(remaining)/.5))) as budget:
                if budget.workers == 1:
                    started = time.process_time()
                    state['pages'].extend(_extract_page(doc, n, i) for i, n in remaining)
                    budget.record({'worker_cpu_seconds':time.process_time()-started, 'worker_peak_bytes':peak_memory()})
                else:
                    from concurrent.futures import ProcessPoolExecutor
                    from multiprocessing import get_context
                    size = min(4, max(1, math.ceil(len(remaining)/budget.workers)))
                    batches = [remaining[i:i+size] for i in range(0,len(remaining),size)]
                    with ProcessPoolExecutor(max_workers=budget.workers, mp_context=get_context('spawn'),
                            initializer=_init_extract_worker,
                            initargs=(source,password,str(budget.database),budget.id)) as pool:
                        for result in pool.map(_extract_pages_task,batches):
                            state['pages'].extend(result['pages'])
                            budget.record(result)
                metrics.append(budget.report())
        state['pages'].sort(key=lambda page:page['output_page'])
        write_json(state_path,state)
        return {'state':str(state_path),'pages':selected,'schema_version':3,
                'extract_workers':max(m['workers'] for m in metrics), 'resources':metrics}
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
            bounds=fitz.Rect(bbox)*matrix
            # Repeated-letter ligatures may emit a zero-width tail at the same
            # code/origin as their visible carrier. Do not overwrite its box.
            if not bounds.is_empty:
                traces[(code,round(p.x,3),round(p.y,3))]=box(bounds)
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
            preserve = method == 'preserve'
            if not valid_rectangle(block['source_bbox'], allow_empty=preserve) or not valid_rectangle(block['allowed_bbox'], allow_empty=preserve):
                raise ValueError('Invalid source/allowed rectangle: '+block['id'])
            source_box = fitz.Rect(block['source_bbox'])
            allowed = fitz.Rect(block['allowed_bbox'])
            if source_box.is_empty and (not glyphs or any(not fitz.Rect(g['bbox']).is_empty or not contains(source_box, fitz.Rect(g['bbox'])) for g in glyphs)):
                raise ValueError('Degenerate preserve box must match source glyph facts: '+block['id'])
            if method != 'preserve' and not contains(bounds,allowed):
                raise ValueError('Allowed box outside visible page: '+block['id'])
            if not contains(source_box,allowed) and not block.get('expansion_reason'):
                raise ValueError('Expanded box requires an explicit adjacent-blank-space reason: '+block['id'])
            actual = block.get('actual_bbox')
            if actual is not None and not contains(allowed,rect(actual)):
                raise ValueError('Actual box exceeds allowed box: '+block['id'])
            if method == 'replace' and block.get('orthogonal') is False:
                raise ValueError('Non-orthogonal native text requires explicit cover treatment: '+block['id'])
            if method == 'replace' and (not glyphs or any(g['hidden'] for g in glyphs)):
                raise ValueError('Replace requires visible native glyphs; hidden OCR needs cover or preserve: '+block['id'])
            if method == 'cover':
                for key in ('cover_fill','cover_text_color'):
                    value=block.get(key)
                    if key in block and (not isinstance(value,list) or len(value)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in value)):
                        raise ValueError('Overlay color requires three finite RGB values in [0,1]: '+block['id']+' '+key)
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

def validate_state(state, source, password=None, final=False, *, pages=None):
    problem = state_header_error(state)
    if problem:
        code, detail = problem
        return [{'code': code, 'detail': detail}]
    errors = []
    if digest(source) != state['source']['sha256']:
        return [{'code':'source_fingerprint_changed'}]
    with open_source(source,password) as doc:
        for page in state['pages']:
            n = page['source_page']
            if pages is not None and n not in pages:
                continue
            if not 1 <= n <= len(doc):
                errors.append({'code':'invalid_source_page','page':n}); continue
            glyphs, _ = text_inventory(doc[n-1],n)
            errors.extend(validate_page(page,{'geometry':geometry(doc[n-1]),'glyphs':glyphs},final))
    return errors

STATIC_ANNOTATIONS={'/Text','/Highlight','/Underline','/StrikeOut','/Squiggly','/Square','/Circle','/Ink','/Stamp'}
TEXT_MARKUP_ANNOTATIONS={'/Highlight','/Underline','/StrikeOut','/Squiggly'}

def annotation_policy(annotation,page,page_state=None):
    from pypdf.generic import StreamObject
    subtype=str(annotation.get('/Subtype'))
    if subtype not in STATIC_ANNOTATIONS:
        raise ValueError('Unsupported visible annotation type '+subtype+'; no appearance is silently discarded')
    if page.rotation:
        raise ValueError('Rotated-page annotation appearances need a custom migration')
    from pypdf.generic import NullObject
    if any(not isinstance(raw_object(annotation.get(k, NullObject())), NullObject)
           for k in ('/A','/AA','/Popup','/IRT')):
        raise ValueError('Annotation actions or popup/reply threads need a custom migration')
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


def raw_object(value):
    return value.get_object() if hasattr(value, 'get_object') else value


class RawNavigation:
    """Interpret the same raw actions in preflight and composition."""

    modes = {'/XYZ': 3, '/FitH': 1, '/FitBH': 1, '/FitV': 1, '/FitBV': 1,
             '/FitR': 4, '/Fit': 0, '/FitB': 0}

    def __init__(self, reader):
        self.reader = reader
        self.numbers = {(p.indirect_reference.idnum, p.indirect_reference.generation): i
                        for i, p in enumerate(reader.pages)}
        self.names = reader.named_destinations
        self._raw_names = None

    def raw_names(self):
        if self._raw_names is not None:
            return self._raw_names
        catalog = self.reader.root_object
        if '/Dests' in catalog and '/Dests' in raw_object(catalog.get('/Names', {})):
            raise ValueError('Ambiguous destination dictionaries')
        if '/Dests' in catalog:
            self._raw_names = dict(raw_object(catalog['/Dests']))
            return self._raw_names
        root = raw_object(catalog.get('/Names', {}))
        stack = [root['/Dests']] if '/Dests' in root else []
        names, seen = {}, set()
        while stack:
            branch = raw_object(stack.pop())
            if not isinstance(branch, dict):
                raise ValueError('Invalid destination name tree')
            if id(branch) in seen:
                raise ValueError('Cyclic or shared destination name tree')
            seen.add(id(branch))
            stack.extend(branch.get('/Kids', []))
            values = branch.get('/Names', [])
            if not isinstance(values, list) or len(values) % 2:
                raise ValueError('Invalid destination name entries')
            for i in range(0, len(values)-1, 2):
                key = str(raw_object(values[i]))
                if key in names:
                    names[key] = None  # ambiguous names cannot prove a null target
                else:
                    names[key] = values[i+1]
        self._raw_names = names
        return names

    @staticmethod
    def numeric(value):
        from pypdf.generic import NullObject

        if isinstance(value, NullObject):
            return None
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError('Invalid raw destination coordinate')
        return float(value)

    def parse(self, item, *, heading=False, allow_null=False, allow_actionless=False):
        from pypdf.generic import NullObject

        action = raw_object(item.get('/A', {}))
        value = item.get('/Dest')
        if '/AA' in item or '/Next' in action:
            raise ValueError('Unsupported chained or additional navigation action')
        if action:
            kind = action.get('/S')
            if kind == '/URI' and isinstance(action.get('/URI'), str):
                return kind, action
            if kind != '/GoTo':
                raise ValueError(f'Unsupported raw navigation action: {kind}')
            value = action.get('/D')
        if value is None and not action:
            if heading:
                return None, None
            if allow_actionless:
                return 'null', None
        value = raw_object(value)
        raw_value = value
        if isinstance(value, str):
            if allow_null:
                names = self.raw_names()
                raw_value = raw_object(names.get(value, names.get(value.lstrip('/'))))
                if isinstance(raw_value, dict):
                    raw_value = raw_object(raw_value.get('/D'))
            named = self.names.get(value) or self.names.get(value.lstrip('/'))
            if named is None:
                if allow_null and value not in names and value.lstrip('/') not in names:
                    return 'null', {'undefined_name': value}
                raise ValueError('Unknown named link destination: ' + value)
            value = named.dest_array
        if not isinstance(value, list) or len(value) < 2:
            raise ValueError('Unsupported raw link destination')
        ref, mode, *args = value
        target = self.numbers.get((ref.idnum, ref.generation)) if hasattr(ref, 'idnum') else ref
        if mode not in self.modes or len(args) != self.modes[mode]:
            raise ValueError('Unsupported raw destination mode: ' + str(mode))
        args = [self.numeric(raw_object(arg)) for arg in args]
        if mode == '/FitR' and None in args:
            raise ValueError('Null FitR rectangle unsupported')
        if allow_null and isinstance(ref, NullObject) and isinstance(raw_value, list) and raw_value and isinstance(raw_value[0], NullObject):
            return 'null', None
        if not isinstance(target, int) or not 0 <= target < len(self.numbers):
            raise ValueError('Unknown raw destination page')
        return '/GoTo', (target, mode, args)

    def outlines(self):
        root = self.reader.trailer['/Root']
        first = raw_object(root.get('/Outlines', {})).get('/First')
        stack = [(0, first)]
        seen = set()
        while stack:
            depth, link = stack.pop()
            if link is None:
                continue
            identity = (link.idnum, link.generation) if hasattr(link, 'idnum') else id(link)
            if identity in seen:
                raise ValueError('Cyclic raw bookmark tree')
            seen.add(identity)
            item = raw_object(link)
            yield depth, item
            stack.extend(((depth, item.get('/Next')), (depth + 1, item.get('/First'))))



_LAYER_ID = '/BilingualTemporaryLayerID'


def layer_catalog(reader):
    """Validate the supported single default configuration."""
    root = reader.trailer['/Root']
    catalog = raw_object(root.get('/OCProperties'))
    if catalog is None:
        return None
    if set(catalog) - {'/OCGs', '/D'} or not catalog.get('/OCGs') or '/D' not in catalog:
        raise ValueError('Optional-content layers require a single default configuration')
    config = raw_object(catalog['/D'])
    if set(config) - {'/Name', '/Creator', '/BaseState', '/ON', '/OFF', '/Order', '/RBGroups', '/Locked', '/Intent'}:
        raise ValueError('Optional-content usage rules or alternate configurations require explicit support')
    groups = catalog['/OCGs']
    if len(set(groups)) != len(groups) or any(
            raw_object(group).get('/Type') != '/OCG' or _LAYER_ID in raw_object(group)
            for group in groups):
        raise ValueError('Invalid or unsupported optional-content group identity')
    return catalog


def native_left_supported(page):
    # A zero-origin visible box permits byte-preserving inclusion with only a clip.
    # Keep rotated or offset pages on the existing transform path.
    media, crop = page.mediabox, page.cropbox
    return (not page.rotation and media == crop and crop.x0 == crop.y0 == 0
            and page.rect == crop)



def probe_left_pane(doc, source, selected, reader):
    """Test representative high-risk pages before the translation is written."""
    from pdf_tools import compare_images, open_document, render_image
    import pypdfium2 as pdfium

    # Form nesting and page transparency can affect rendering. Test the first
    # and last page and pages carrying these resources.
    representatives = {selected[0], selected[-1]}
    representatives.update(n for n in selected if '/Group' in reader.pages[n-1]
                           or doc[n-1].get_xobjects())
    findings = []
    with open_document(source) as original:
        for n in sorted(representatives):
            page = doc[n-1]
            if not page.get_contents() or any(
                    raw_object(ref).get('/Subtype') != '/Link' or raw_object(ref).get('/AP')
                    or (len(raw_object(ref).get('/Border', [])) >= 3 and raw_object(ref)['/Border'][2] != 0)
                    or raw_object(raw_object(ref).get('/BS', {})).get('/W', 0) != 0
                    for ref in reader.pages[n-1].get('/Annots', [])):
                continue
            width, height = page.rect.width, page.rect.height
            rotation = page.rotation
            with fitz.open() as probe:
                left = probe.new_page(width=2*width, height=height)
                page.set_rotation(0)
                try:
                    left.show_pdf_page(fitz.Rect(0, 0, width, height), doc, n-1, rotate=-rotation)
                finally:
                    page.set_rotation(rotation)
                # Layered files are compared after their catalog is mapped.
                with pdfium.PdfDocument(probe.tobytes()) as candidate:
                    with closing(original[n-1]) as a, closing(candidate[0]) as b:
                        with render_image(a) as src, render_image(b) as dst:
                            comparison, difference = compare_images(src, dst, (0, 0, width, height), 144, 16, .001)
                            if difference is not None:
                                difference.close()
            if not comparison['passed']:
                supported = native_left_supported(page)
                findings.append({'page': n,
                                 'code': 'native_left_required' if supported else 'source_pane_probe_failed',
                                 'object_type': 'page content / Form XObject',
                                 'comparison': comparison})
    return findings


def attach_native_left(writer, composed_page, original, width, height):
    """Prefix isolated raw source streams, keeping original resource names."""
    from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject
    from pypdf._page import PageObject

    resources_key = NameObject('/Resources')
    left_resources = raw_object(original.get('/Resources', DictionaryObject())).clone(writer)
    # Copy the resource dictionaries before adding names; the originals can be
    # shared by multiple source pages or nested Forms.
    resources = DictionaryObject(left_resources)
    right_resources = composed_page[resources_key]
    renamed = {}
    for category, right in right_resources.items():
        if category == '/ProcSet':
            continue
        left = DictionaryObject(raw_object(resources.get(category, DictionaryObject())))
        for name, ref in raw_object(right).items():
            target = name
            while target in left and left.raw_get(target) != ref:
                target = NameObject(str(target) + '_R')
            if target != name:
                renamed[name] = target
            left[target] = ref
        resources[category] = left

    def stream(data):
        obj = DecodedStreamObject()
        obj.set_data(data)
        return writer._add_object(obj.flate_encode())

    contents = original.get('/Contents')
    if contents is not None:
        contents = contents if isinstance(contents, ArrayObject) else [original.raw_get('/Contents')]
        # q/Q preserve each pane's graphics state; the clip keeps existing marks
        # outside the original page box out of the expanded right pane.
        before = stream(f'q\n0 0 {width:.9g} {height:.9g} re W n\n'.encode('ascii'))
        after = stream(b'Q\n')
        result = ArrayObject([before, *(ref.clone(writer) for ref in contents), after])
    else:
        result = ArrayObject()
    right = composed_page.get_contents()
    if right is not None:
        if renamed:
            right = PageObject._content_stream_rename(right, renamed, writer)
        result.append(stream(right.get_data()))
    composed_page[NameObject('/Contents')] = result
    composed_page[resources_key] = resources
    if '/Group' in original:
        composed_page[NameObject('/Group')] = original['/Group'].clone(writer)



def share_native_images(writer):
    """Reuse images and masks even when their equivalent resource refs differ."""
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject
    from pdf_tools import canonical_object

    images = {}
    refs = {}
    for obj in writer._objects:
        if isinstance(obj, DictionaryObject) and obj.get('/Subtype') == '/Image':
            signature = canonical(canonical_object(obj))
            ref = obj.indirect_reference
            refs[ref] = images.setdefault(signature, ref)

    def rebind(obj):
        if isinstance(obj, DictionaryObject):
            values = obj.items()
        elif isinstance(obj, ArrayObject):
            values = enumerate(obj)
        else:
            return
        for key, child in values:
            if isinstance(child, IndirectObject):
                if child in refs and child != refs[child]:
                    obj[key] = refs[child]
            else:
                rebind(child)

    for obj in writer._objects:
        rebind(obj)


def attach_layer_catalog(writer, catalog):
    """Bind all right-pane copies to the original OCG identities before deduplication."""
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, NameObject, NumberObject

    if catalog is None:
        return []
    output_catalog = catalog.clone(writer)
    output_groups = output_catalog['/OCGs']
    markers = {}
    for i, ref in enumerate(output_groups):
        raw_object(ref)[NameObject(_LAYER_ID)] = NumberObject(i)
        markers[i] = ref

    def rebind(obj):
        if isinstance(obj, DictionaryObject):
            values = list(obj.items())
        elif isinstance(obj, ArrayObject):
            values = list(enumerate(obj))
        else:
            return
        for key, child in values:
            resolved = raw_object(child)
            if isinstance(resolved, DictionaryObject) and resolved.get('/Type') == '/OCG':
                marker = resolved.get(_LAYER_ID)
                if marker not in markers or not isinstance(child, IndirectObject):
                    raise ValueError('Unmapped optional-content group in composed PDF')
                obj[key] = markers[marker]
            elif not isinstance(child, IndirectObject):
                rebind(child)

    for obj in writer._objects:
        rebind(obj)
    writer.root_object[NameObject('/OCProperties')] = output_catalog
    return output_groups


def interaction_reader(doc, source=None, password=None):
    from pypdf import PdfReader

    reader = PdfReader(source if source is not None else io.BytesIO(doc.tobytes()))
    if reader.is_encrypted and not reader.decrypt(password or ''):
        raise ValueError('password_required: A valid explicitly supplied password is required')
    return reader


def check_interactions(doc, selected, state=None, *, collect=False, preview=False, reader=None):
    from pypdf.generic import ContentStream

    reader = interaction_reader(doc) if reader is None else reader
    nav = RawNavigation(reader)
    findings = []

    def report(code, detail, page=None, **location):
        finding = {'code': code, 'detail': detail, **location}
        if page is not None:
            finding['page'] = page
        findings.append(finding)

    def check_stream(stream, resources, seen):
        if stream is not None:
            for operands, operator in ContentStream(stream, reader).operations:
                if operator == b'Tr' and operands and int(operands[0]) >= 4:
                    raise ValueError('Text clipping render modes 4-7 are unsupported; refusing to change clipped graphics')
        for ref in raw_object(resources.get('/XObject', {})).values():
            obj = raw_object(ref)
            if obj.get('/Subtype') != '/Form':
                continue
            child_resources = raw_object(obj.get('/Resources', resources))
            key = (getattr(ref, 'idnum', id(obj)), id(child_resources))
            if key not in seen:
                seen.add(key)
                try:
                    check_stream(obj, child_resources, seen)
                except Exception:
                    seen.discard(key)
                    raise

    catalog = None
    try:
        catalog = layer_catalog(reader)
    except ValueError as exc:
        report('interaction_preflight', str(exc))
    layer_refs = set(catalog['/OCGs']) if catalog is not None else set()
    if doc.embfile_count():
        report('interaction_preflight', 'Embedded attachments require explicit preservation support')
    form = raw_object(reader.trailer['/Root'].get('/AcroForm', {}))
    if form.get('/Fields') or form.get('/XFA'):
        report('interaction_preflight', 'Interactive forms require explicit preservation support')

    page_states = {p['source_page']: p for p in state['pages']} if state else {}
    scope = set(selected)
    allow_omission = preview or state and state.get('document', {}).get('delivery_scope') == 'sample'
    allow_null = state is not None and state.get('layout', {}).get('review_profile') == 'practical'
    try:
        for i, (_, item) in enumerate(nav.outlines()):
            try:
                kind, target = nav.parse(item, heading=True, allow_null=allow_null)
                if kind == 'null':
                    report('source_destination_null', 'Preserve bookmark as a title without an action',
                           bookmark=i, title=str(item.get('/Title', '')), **(target or {}))
            except (ValueError, KeyError, TypeError) as exc:
                report('bookmark_action', str(exc), bookmark=i, title=str(item.get('/Title', '')))
    except ValueError as exc:
        report('bookmark_tree', str(exc))
    seen = set()
    for n in selected:
        original, page = reader.pages[n-1], doc[n-1]
        try:
            check_stream(original.get_contents(), raw_object(original.get('/Resources', {})), seen)
        except (ValueError, KeyError, TypeError) as exc:
            report('interaction_preflight', str(exc), n)
        link_number = -1
        for ref in original.get('/Annots', []):
            annotation = raw_object(ref)
            if annotation.get('/Subtype') != '/Link':
                try:
                    annotation_policy(annotation, page, page_states.get(n))
                    if '/OC' in annotation and annotation.raw_get('/OC') not in layer_refs:
                        raise ValueError('Annotation uses an unsupported optional-content membership')
                except (ValueError, KeyError, TypeError) as exc:
                    report('interaction_preflight', str(exc), n, subtype=str(annotation.get('/Subtype')))
                continue
            link_number += 1
            try:
                if annotation.get('/AP'):
                    raise ValueError('Link appearance streams require explicit preservation support')
                if '/OC' in annotation and annotation.raw_get('/OC') not in layer_refs:
                    raise ValueError('Link uses an unsupported optional-content membership')
                coords = [float(v) for v in annotation['/Rect']]
                if len(coords) != 4 or not all(math.isfinite(v) for v in coords):
                    raise ValueError('Invalid raw link rectangle')
                kind, target = nav.parse(annotation, allow_null=allow_null)
                if kind == 'null':
                    report('source_destination_null', 'Preserve link appearance without an action', n,
                           source_link=link_number, **(target or {}))
                if kind == '/GoTo' and target[0]+1 not in scope:
                    code = 'sample_link_omitted' if allow_omission else 'link_destination_outside_scope'
                    report(code, f'Selected pages exclude a link destination from page {n}', n,
                           source_link=link_number, target_page=target[0]+1)
            except (ValueError, KeyError, TypeError) as exc:
                report('link_action', str(exc), n, source_link=link_number)
    blockers = [finding for finding in findings if finding['code'] not in ('sample_link_omitted', 'source_destination_null')]
    if blockers and not collect:
        raise ValueError(json.dumps({'code': 'interaction_preflight', 'findings': blockers}, ensure_ascii=False))
    return findings


def right_link_resolver(source_doc, page_states):
    link_geometry = {}

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
        if n not in link_geometry:
            link_geometry.clear()
            effective = effective_glyph_boxes(source_doc[n-1], ps['glyphs'])
            centers = CollisionIndex()
            glyphs = {g['id']: g for g in ps['glyphs'] if g['text'].strip()}
            for gid in glyphs:
                bounds = fitz.Rect(effective[gid])
                point = (bounds.tl + bounds.br) / 2
                centers.add('glyph', gid, fitz.Rect(point.x-.001, point.y-.001, point.x+.001, point.y+.001))
            link_geometry[n] = centers, glyphs, effective
        centers, glyphs, effective = link_geometry[n]
        ids = set()
        search = source_rect + fitz.Rect(-.002, -.002, .002, .002)
        for _, gid in centers.intersections(search, 0):
            bounds = fitz.Rect(effective[gid])
            if source_rect.contains((bounds.tl + bounds.br) / 2):
                ids.add(gid)
        linked = [glyphs[gid] for gid in sorted(ids, key=lambda gid: int(gid.rsplit('-g', 1)[1]))]
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
            elif ids.issuperset(g for g in block.get('glyph_ids',[]) if g in glyphs):
                matches.append(boxes)
        if len(matches)!=1 or not matches[0]:
            raise ValueError('Right link text cannot be mapped uniquely on page %d link %d; candidate target_block IDs: %s; provide target_text and occurrence' % (n,link_number, ', '.join(b['id'] for b in affected)))
        union=fitz.Rect(matches[0][0])
        for value in matches[0][1:]:union|=fitz.Rect(value)
        return [union]
    return right_rectangles


def check_right_links(source_doc, reader, selected, state):
    pages = {p['source_page']: p for p in state['pages']}
    resolve_right = right_link_resolver(source_doc, pages)
    nav = RawNavigation(reader)
    scope = set(state['document'].get('final_source_pages',
                    state['document'].get('selected_source_pages', selected)))
    conflicts = []
    geometry = {}
    for n in selected:
        page = source_doc[n-1]
        number = -1
        for ref in reader.pages[n-1].get('/Annots', []):
            annotation = raw_object(ref)
            if annotation.get('/Subtype') != '/Link':
                continue
            number += 1
            kind, target = nav.parse(annotation, allow_null=state['layout'].get('review_profile') == 'practical')
            if kind == 'null' or kind == '/GoTo' and target[0]+1 not in scope:
                continue
            source_rect = fitz.Rect([float(v) for v in annotation['/Rect']]) * page.transformation_matrix * page.rotation_matrix
            try:
                geometry[n, number] = resolve_right(n, number, source_rect)
            except ValueError as exc:
                conflicts.append({'page':n, 'source_link':number, 'source_bbox':box(source_rect),
                                  'detail':str(exc), 'next':'Use link_overrides_patch with target_block, target_text and occurrence.'})
    return conflicts, geometry


def migrate_raw_links(source_doc, source_path, composed_stream, output_stream, selected,
                      password=None, state=None, *, reader=None, native_pages=(), metrics=None, right_links=None, vectors=None):
    """Preserve destination modes and nullable axes that get_links cannot represent."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NullObject, FloatObject
    reader = interaction_reader(source_doc, source_path, password) if reader is None else reader
    composed = PdfReader(composed_stream)
    writer=PdfWriter()
    writer.append(composed,import_outline=False)
    if reader.metadata:
        writer.add_metadata(reader.metadata)
    if metadata := reader.trailer['/Root'].get('/Metadata'):
        writer.root_object[NameObject('/Metadata')] = metadata.clone(writer)
    nav = RawNavigation(reader)
    mapping={n-1:i for i,n in enumerate(selected)}
    transforms={}
    for n in selected:
        p=source_doc[n-1];rotation=p.rotation;rm=p.rotation_matrix
        p.set_rotation(0);tm=p.transformation_matrix;p.set_rotation(rotation)
        transforms[n-1]=tm*rm
    def number(value):return NullObject() if value is None else FloatObject(value)
    def coordinate(x,y,a,b,offset):
        if (abs(a)>1e-8 and x is None) or (abs(b)>1e-8 and y is None):return None
        return a*(x or 0)+b*(y or 0)+offset
    def destination(target, pane):
        target, mode, args = target
        if target not in mapping:
            return None
        p=source_doc[target];w,h=p.rect.width,p.rect.height
        m=transforms[target]*fitz.Matrix(1,0,0,1,pane*w,0)*fitz.Matrix(1,0,0,-1,0,h)
        if mode=='/XYZ':
            x,y,z=args
            args=[number(coordinate(x,y,m.a,m.c,m.e)),number(coordinate(x,y,m.b,m.d,m.f)),number(z)]
        elif mode in ('/FitH','/FitBH'):
            if abs(m.d)>1e-8:args=[number(coordinate(None,args[0],m.b,m.d,m.f))]
            else:
                args=[number(coordinate(None,args[0],m.a,m.c,m.e))]
                mode='/FitBV' if mode=='/FitBH' else '/FitV'
        elif mode in ('/FitV','/FitBV'):
            if abs(m.a)>1e-8:args=[number(coordinate(args[0],None,m.a,m.c,m.e))]
            else:
                args=[number(coordinate(args[0],None,m.b,m.d,m.f))]
                mode='/FitBH' if mode=='/FitBV' else '/FitH'
        elif mode=='/FitR':
            r=fitz.Rect(args)*m;args=[FloatObject(v) for v in r]
        return ArrayObject([writer.pages[mapping[target]].indirect_reference,NameObject(mode),*args])

    parents = []
    omitted_bookmarks = 0
    null_bookmarks = []
    allow_null = state is not None and state.get('layout', {}).get('review_profile') == 'practical'
    for i, (depth, item) in enumerate(nav.outlines()):
        parents = parents[:depth]
        parent = parents[-1] if parents else None
        kind, target = nav.parse(item, heading=True, allow_null=allow_null)
        if kind == 'null':
            null_bookmarks.append({'bookmark': i, 'title': str(item['/Title']), **(target or {})})
        mapped = destination(target, 0) if kind == '/GoTo' else None
        if kind == '/GoTo' and mapped is None:
            omitted_bookmarks += 1
            parents.append(parent)
            continue
        entry = writer.add_outline_item(str(item['/Title']), None, parent=parent,
                                        is_open=item.get('/Count', 0) >= 0)
        copied = raw_object(entry)
        for key in ('/Title', '/C', '/F'):
            if key in item:
                copied[NameObject(key)] = item[key].clone(writer)
        if kind == '/URI':
            copied[NameObject('/A')] = target.clone(writer)
        elif mapped is not None:
            copied[NameObject('/Dest')] = mapped
        parents.append(entry)
    if state is not None:
        state['layout']['omitted_bookmarks_for_unselected_pages'] = omitted_bookmarks
        state['layout']['null_bookmarks'] = null_bookmarks
    for n in sorted(native_pages):
        page = source_doc[n-1]
        attach_native_left(writer, writer.pages[mapping[n-1]], reader.pages[n-1],
                           page.rect.width, page.rect.height)
    page_states={p['source_page']:p for p in state['pages']} if state else {}
    for ps in page_states.values():
        ps.pop('link_mappings',None);ps.pop('omitted_links',None);ps.pop('null_links',None)
    right_rectangles = right_link_resolver(source_doc, page_states)
    link_conflicts=[]
    for n in selected:
        p=source_doc[n-1];w,h=p.rect.width,p.rect.height
        link_number=-1
        for ref in reader.pages[n-1].get('/Annots',[]):
            annotation=ref.get_object()
            if annotation.get('/Subtype')!='/Link':continue
            link_number+=1
            kind, target = nav.parse(annotation, allow_null=allow_null)
            if kind == 'null':
                page_states.get(n, {}).setdefault('null_links', []).append({'source_link': link_number, **(target or {})})
            if kind == '/GoTo' and target[0] not in mapping:
                page_states.get(n, {}).setdefault('omitted_links', []).append({
                    'source_link': link_number, 'target_page': target[0]+1,
                    'reason': 'Destination outside the selected preview or sample'})
                continue
            if annotation.get('/AP'):raise ValueError('Link appearance streams require explicit preservation support')
            source_rect=fitz.Rect([float(a) for a in annotation['/Rect']])*transforms[n-1]
            try:
                right_boxes = ([source_rect] if kind == 'null' else
                               right_links[n,link_number] if right_links is not None and (n,link_number) in right_links else
                               right_rectangles(n,link_number,source_rect))
            except ValueError as exc:
                link_conflicts.append({'page':n,'source_link':link_number,'source_bbox':box(source_rect),'detail':str(exc),
                    'next':'Set link_overrides_patch with target_block, target_text and occurrence, or explicit right_bbox.'})
                continue
            for pane in (0,1):
                copied=DictionaryObject()
                for key,value in annotation.items():
                    if key not in ('/P','/Rect','/A','/Dest','/QuadPoints','/StructParent','/NM'):
                        copied[NameObject(key)]=value.clone(writer) if hasattr(value,'clone') else value
                m=transforms[n-1]*fitz.Matrix(1,0,0,1,pane*w,0)*fitz.Matrix(1,0,0,-1,0,h)
                source_rect=fitz.Rect([float(a) for a in annotation['/Rect']])*transforms[n-1]
                destination_rects=right_boxes if pane else [source_rect]
                if pane and n in page_states:
                    page_states[n].setdefault('link_mappings',[]).append({'source_link':link_number,'source_bbox':box(source_rect),'right_bboxes':[box(r) for r in destination_rects],
                        'visible_border':bool((annotation.get('/Border') and len(annotation['/Border'])>=3 and float(annotation['/Border'][2])>0) or (annotation.get('/BS') and float(annotation['/BS'].get('/W',0))>0))})
                visible_to_pdf=fitz.Matrix(1,0,0,-1,pane*w,h)
                copied[NameObject('/Rect')]=ArrayObject([FloatObject(v) for v in destination_rects[0]*visible_to_pdf])
                if '/QuadPoints' in annotation and (not pane or kind == 'null'):
                    values=annotation['/QuadPoints'];points=[]
                    for j in range(0,len(values),2):
                        point=fitz.Point(float(values[j]),float(values[j+1]))*m;points.extend([FloatObject(point.x),FloatObject(point.y)])
                    copied[NameObject('/QuadPoints')]=ArrayObject(points)
                if kind == '/URI':
                    copied[NameObject('/A')] = target.clone(writer)
                elif kind == '/GoTo':
                    copied[NameObject('/Dest')] = destination(target, pane)
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
                    if key not in ('/P','/Rect','/QuadPoints','/InkList','/NM','/Popup','/IRT','/A','/AA'):
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
    if link_conflicts:raise ValueError(json.dumps({'link_conflicts':link_conflicts},ensure_ascii=False))
    if vectors is not None:
        vectors.apply(writer, selected)
    layers = attach_layer_catalog(writer, layer_catalog(reader))
    if native_pages:
        share_native_images(writer)
    # Consolidate page instructions so tiny q/Q wrapper streams are compressed
    # too; image streams remain untouched. Drop their now-unreferenced fragments.
    for i, page in enumerate(writer.pages):
        if selected[i] not in native_pages:
            page.compress_content_streams()
    if metrics:
        metrics.enter('pypdf_deduplication')
    writer.compress_identical_objects(remove_duplicates=True,remove_unreferenced=True)
    for ref in layers:
        raw_object(ref).pop(_LAYER_ID)
    if metrics:
        metrics.enter('pypdf_write')
    writer.write(output_stream)
    return {'final_xref_slots': len(writer._objects),
            'final_live_objects': sum(obj is not None for obj in writer._objects)}

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


GLYPH_POSITION_TOLERANCE = .02  # PDF points; allow serialization drift, not a new glyph position.


def glyph_location(code, origin):
    return code, origin[0], origin[1]


def right_visible_trace(page, width):
    """Return visible, positioned glyphs in the reused right pane."""
    return [
        glyph_location(code, (origin[0]-width, origin[1]))
        for trace in page.get_texttrace()
        if trace['type'] in (0, 1) and trace.get('opacity', 1) > 0
        for code, gid, origin, bounds in trace['chars']
        if gid >= 0 and origin[0] >= width and not fitz.Rect(bounds).is_empty
    ]


def match_glyph_locations(expected, actual, tolerance=GLYPH_POSITION_TOLERANCE):
    """Find a maximum one-to-one matching of equal glyphs within tolerance."""
    grid = defaultdict(list)
    for j, (code, x, y) in enumerate(actual):
        grid[(code, math.floor(x/tolerance), math.floor(y/tolerance))].append(j)
    candidates = []
    for code, x, y in expected:
        cx, cy = math.floor(x/tolerance), math.floor(y/tolerance)
        options = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid.get((code, cx+dx, cy+dy), ()):
                    _, ax, ay = actual[j]
                    if abs(x-ax) <= tolerance and abs(y-ay) <= tolerance:
                        options.append((abs(x-ax)+abs(y-ay), j))
        candidates.append([j for _, j in sorted(options)])
    # Augment paths avoid both reuse and greedy mismatches for nearby duplicates.
    left_to_right, right_to_left = {}, {}
    for start in range(len(expected)):
        queue = [start]
        parent = {start: None}
        seen_right = set()
        for left in queue:
            for right in candidates[left]:
                if right in seen_right:
                    continue
                seen_right.add(right)
                previous = right_to_left.get(right)
                if previous is None:
                    while left is not None:
                        old = left_to_right.get(left)
                        left_to_right[left] = right
                        right_to_left[right] = left
                        right = old
                        left = parent[left]
                    break
                if previous not in parent:
                    parent[previous] = left
                    queue.append(previous)
            else:
                continue
            break
    return left_to_right


def preserved_glyph_conflicts(page_number, protected, before, after, mask_index):
    entries = [(location, g, owner) for location, glyphs in protected.items()
               for g, owner in glyphs]
    initial = match_glyph_locations([entry[0] for entry in entries], before)
    expected_indices = sorted(initial)
    remaining = match_glyph_locations([before[initial[i]] for i in expected_indices], after)
    missing = defaultdict(list)
    for position, i in enumerate(expected_indices):
        if position not in remaining:
            location, glyph, owner = entries[i]
            missing[location].append((glyph, owner))
    conflicts = []
    for location, glyphs in missing.items():
        # MuPDF can remove text using font-wide boxes. The raw boxes help
        # identify replacement masks that may have triggered the removal.
        related = sorted({bid for g, _ in glyphs
                          for _, bid in mask_index.intersections(g['bbox'], 0)})
        conflicts.append({
            'page': page_number, 'code': 'preserved_glyph_removed',
            'block': glyphs[0][1], 'preserved_blocks': sorted({bid for _, bid in glyphs}),
            'character': chr(location[0]), 'origin': [round(v, 2) for v in location[1:]],
            'missing_count': len(glyphs), 'related_replacement_blocks': related,
            'detail': 'Right-pane redaction removed preserved text; inspect the nearby replacements before rebuilding.',
        })
    return conflicts


def peak_rss_bytes():
    """Peak resident memory of the current process, when available."""
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in (
                    'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
                    'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage',
                    'PagefileUsage', 'PeakPagefileUsage')]
        get_process = ctypes.windll.kernel32.GetCurrentProcess
        get_process.restype = wintypes.HANDLE
        get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
        get_memory.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
        get_memory.restype = wintypes.BOOL
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if get_memory(get_process(), ctypes.byref(counters), counters.cb):
            return counters.PeakWorkingSetSize
        return None
    try:
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return peak if sys.platform == 'darwin' else peak * 1024
    except (ImportError, OSError, ValueError):
        return None


class BuildMetrics:
    def __init__(self, progress):
        self.progress = progress
        self.started = self.stage_started = time.perf_counter()
        self.cpu_started = self.stage_cpu_started = time.process_time()
        self.stage = None
        self.stages = {}
        self.completed_pages = 0
        self.total_pages = None
        self.source_page = None
        self.objects = {}

    def enter(self, stage):
        now, cpu = time.perf_counter(), time.process_time()
        if self.stage is not None:
            self.stages[self.stage] = {
                'wall_seconds': round(now-self.stage_started, 3),
                'cpu_seconds': round(cpu-self.stage_cpu_started, 3),
            }
        self.stage, self.stage_started, self.stage_cpu_started = stage, now, cpu
        self.emit()

    def emit(self, error=None):
        if self.progress is not None:
            row = {'stage': self.stage, 'completed_pages': self.completed_pages,
                   'total_pages': self.total_pages, 'source_page': self.source_page,
                   'wall_seconds': round(time.perf_counter()-self.started, 3),
                   'cpu_seconds': round(time.process_time()-self.cpu_started, 3),
                   'peak_rss_bytes': peak_rss_bytes()}
            if error is not None:
                row.update(status='failed', error_type=type(error).__name__, error=str(error)[:300])
            self.progress(row)

    def report(self):
        return {'stages': self.stages, 'wall_seconds': round(time.perf_counter()-self.started, 3),
                'cpu_seconds': round(time.process_time()-self.cpu_started, 3),
                'peak_rss_bytes': peak_rss_bytes(), 'objects': self.objects.copy()}


def build(source,state_path,output,pages='all',overwrite=False,password=None, *,
          preview=False, state=None, progress=None, garbage=4, return_state=False):
    """Compose from a state file or an already parsed, disposable state object."""
    if garbage not in (2, 4):
        raise ValueError('garbage must be 2 or 4')
    metrics = BuildMetrics(progress)
    metrics.enter('state_validation')
    try:
        result = _build(source, state_path, output, pages, overwrite, password, preview,
                        state, garbage, return_state, metrics)
    except Exception as exc:
        metrics.emit(error=exc)
        raise
    metrics.enter('complete')
    result['build_metrics'] = metrics.report()
    return result


def _build(source, state_path, output, pages, overwrite, password, preview,
           state, garbage, return_state, metrics):
    source,state_path,output=map(lambda p:Path(p).resolve(),(source,state_path,output))
    destinations=[output,output.with_suffix('.state.json'),output.with_suffix('.font-runs.json')]
    if source in destinations or state_path in destinations:
        raise ValueError('Output must not overwrite source or authoring state')
    if any(p.exists() for p in destinations) and not overwrite:
        raise ValueError('Output exists; use --overwrite explicitly')
    if state is None:
        state=json.loads(state_path.read_text(encoding='utf-8'))
    validation_pages = set(selected_pages(pages, state['source']['page_count'])) if pages != 'all' else None
    errors=validate_state(state,source,password,False,pages=validation_pages)
    if errors:raise ValueError(json.dumps(errors,ensure_ascii=False))
    dependencies=[]
    for item in state['layout'].get('inputs',[]):
        dependency=resolve(state_path.parent,item['path']).resolve()
        if digest(dependency)!=item['sha256']:raise ValueError('External input fingerprint changed: '+item['path'])
        if dependency in destinations:raise ValueError('Output must not overwrite a declared dependency')
        dependencies.append({**item,'path':relative(dependency,output.parent)})
    src=open_source(source,password)
    out=fitz.open()
    reader = None
    try:
        available={p['source_page']:p for p in state['pages']}
        selected=sorted(available) if pages=='all' else selected_pages(pages,len(src))
        if any(n not in available for n in selected):
            raise ValueError('Selected page missing from state')
        state['pages']=[available[n] for n in selected]
        metrics.total_pages = len(selected)
        errors = [error for p in state['pages'] for error in validate_page(p,p,True)]
        if errors:
            raise ValueError(json.dumps({'code':'layout_preflight','findings':errors},ensure_ascii=False))
        metrics.enter('navigation_preflight')
        reader = interaction_reader(src, source, password)
        check_interactions(src, selected, state, preview=preview, reader=reader)
        metrics.enter('fonts')
        fonts=load_fonts(state,state_path)
        labels=dict(pagination_items(state))
        build_errors=[]
        runs=[]
        catalog = layer_catalog(reader)
        if catalog is not None:
            for i, ref in enumerate(catalog['/OCGs']):
                src.xref_set_key(ref.idnum, _LAYER_ID[1:], str(i))
        from vector_forms import VectorSharing
        vectors = VectorSharing()
        native_pages = set()
        # Capture source rotation before zeroing it. show_pdf_page does not account for
        # the source page Rotate entry; an explicit inverse rotation is required.
        metrics.enter('page_composition')
        for j,n in enumerate(selected):
            metrics.source_page = n
            pstate=available[n];pstate['output_page']=j+1
            original=src[n-1];w,h=original.rect.width,original.rect.height;rotation=original.rotation
            native = pstate.get('native_left') is True
            if native and not native_left_supported(original):
                raise ValueError(f'Native left cannot preserve the visible page box: source page {n}')
            if native:
                native_pages.add(n)
            effective_boxes=effective_glyph_boxes(original,pstate['glyphs'])
            if not native and catalog is None:
                vectors.mark(src, reader, original, n)
            original.set_rotation(0)
            page=out.new_page(width=2*w,height=h)
            page_fonts=set()
            if original.get_contents():
                page.show_pdf_page(fitz.Rect(w,0,2*w,h),src,n-1,rotate=-rotation)
            by_id={g['id']:g for g in pstate['glyphs']}
            pstate['redaction_regions']=[]
            deleted=set();masks=[];carriers=ligature_carriers(pstate['glyphs'])
            owners = {g['id']: b['id'] for b in pstate['blocks'] for g in selected_glyphs(b, by_id)}
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
                protected = defaultdict(list)
                for g in pstate['glyphs']:
                    if (g['id'] not in deleted and g['id'] not in carriers
                            and not g['hidden'] and g['text'].strip() and g['id'] in owners):
                        protected[glyph_location(ord(g['text']), g['origin'])].append((g, owners[g['id']]))
                before = right_visible_trace(page, w) if protected else None
                page.apply_redactions(images=0,graphics=0,text=0)
                if before:
                    after = right_visible_trace(page, w)
                    mask_index = CollisionIndex()
                    for ids, mask in merged:
                        for bid in {owners[gid] for gid in ids.split(',')}:
                            mask_index.add('replacement', bid, mask)
                    build_errors.extend(preserved_glyph_conflicts(n, protected, before, after, mask_index))
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
            text_shape = page.new_shape()
            for b in draw_blocks:
                b['status']='verbatim' if b['method']=='preserve' else 'translated'
                if b['method']=='preserve':
                    b['actual_bbox']=None;b['target_bbox']=None;continue
                if b['method']=='cover':
                    text_shape.commit()
                    cover=rect(b.get('cover_bbox') or b['source_bbox'])
                    protected=[g['id'] for g in pstate['glyphs'] if g['id'] not in deleted and not g['hidden'] and g['text'].strip() and cover.intersects(fitz.Rect(effective_boxes[g['id']]))]
                    if protected:build_errors.append({'page':n,'block':b['id'],'detail':'Cover intersects preserved native text: '+','.join(protected)})
                    page.draw_rect(cover+fitz.Rect(w,0,w,0),color=None,fill=tuple(b.get('cover_fill',(1,1,1))),overlay=True)
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
                            text_shape.insert_text(point,ch,fontname=font['alias'],fontsize=b['actual_font_size']*scale,
                                             rotate=b.get('rotation',0),color=tuple(b.get('cover_text_color',(0,0,0))) if b['method']=='cover' else tuple(b.get('color',(0,0,0))))
                            advance+=char_width
            text_shape.commit()
            if not native and original.get_contents():
                # Graft after redaction so MuPDF only rewrites the right-pane stream.
                page.show_pdf_page(fitz.Rect(0,0,w,h),src,n-1,rotate=-rotation,overlay=False)
            original.set_rotation(rotation)
            metrics.completed_pages = j+1
            metrics.emit()
        metrics.source_page = None
        metrics.enter('right_link_preflight')
        link_errors, right_links = check_right_links(src, reader, selected, state)
        if build_errors or link_errors:
            raise ValueError(json.dumps({'layout_conflicts':build_errors, 'link_conflicts':link_errors},ensure_ascii=False))
        out.set_metadata(src.metadata)
        metrics.enter('font_subsetting')
        out.subset_fonts()
        output.parent.mkdir(parents=True,exist_ok=True)
        metrics.enter('stream_compression')
        # Compress newly composed non-image streams without re-encoding original images/masks.
        for xref in range(1,out.xref_length()):
            if out.xref_is_stream(xref) and out.xref_get_key(xref,'Subtype')[1] != '/Image':
                out.update_stream(xref,out.xref_stream(xref),compress=True)
        with tempfile.TemporaryDirectory(prefix='.compose-', dir=output.parent) as staging:
            staged = Path(staging)
            composed_path = staged / 'composed.pdf'
            final_path = staged / 'candidate.pdf'
            metrics.objects['mupdf_before_save'] = out.xref_length()
            metrics.enter('mupdf_write')
            out.save(composed_path, garbage=garbage, deflate=False, no_new_id=True)
            out.close()
            metrics.enter('pypdf_migration')
            with composed_path.open('rb') as composed, final_path.open('wb') as final:
                metrics.objects.update(migrate_raw_links(
                    src, source, composed, final, selected, password, state,
                    reader=reader, native_pages=native_pages, metrics=metrics, right_links=right_links, vectors=vectors))
            metrics.enter('state_write')
            vector_report = vectors.report(final_path, selected)
            candidate_sha = digest(final_path)
            if state['layout'].get('runtime_launcher'):
                state['layout']['runtime_launcher']=relative(resolve(state_path.parent,state['layout']['runtime_launcher']),output.parent)
            state['source']['path']=relative(source,output.parent)
            state['output']={'path':output.name,'sha256':candidate_sha,'vector_forms':vector_report,
                             'assignments':relative(destinations[2],output.parent)}
            if preview:state['output']['preview']=True
            for reg in state['layout']['fonts']:
                reg['source']=relative(resolve(state_path.parent,reg['source']),output.parent)
            state['layout']['builder']={'path':relative(__file__,output.parent),'sha256':digest(__file__)}
            helper=Path(__file__).with_name('workflow.py')
            dependencies=[d for d in dependencies if resolve(output.parent,d['path']).resolve()!=helper.resolve()]
            state['layout']['inputs']=dependencies+[{'path':relative(helper,output.parent),'sha256':digest(helper)}]
            state['layout']['runtime']={'pymupdf':fitz.VersionBind}
            state['qc']={}
            state_tmp, runs_tmp = staged / 'state.json', staged / 'assignments.json'
            write_json(state_tmp,state)
            write_json(runs_tmp,{'schema_version':1,'output_sha256':candidate_sha,'runs':runs})
            state_tmp.replace(destinations[1])
            runs_tmp.replace(destinations[2])
            final_path.replace(output)
        result = {'output':str(output),'state':str(destinations[1]),'assignments':str(destinations[2]),'pages':selected,
                  'state_written_bytes':destinations[1].stat().st_size,
                  'vector_forms':vector_report,
                  'omitted_link_pages': [p['source_page'] for p in state['pages'] if p.get('omitted_links')]}
        if return_state:
            result['_state'] = state
        return result
    finally:
        if reader is not None:
            reader.close()
        src.close()
        if not out.is_closed:
            out.close()
