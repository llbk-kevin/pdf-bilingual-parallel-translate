"""Small deterministic helpers; no translation, implicit review or file renaming."""
import hashlib
import copy
import json
import math
import re
from html import unescape
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def resolve(base, value):
    p = Path(value)
    return p if p.is_absolute() else Path(base) / p


def plain(text):
    return unescape(re.sub(r'<[^>]+>', '', text))


def block_text(block):
    if block.get('kind') == 'table':
        return '\n'.join('\n'.join(row) for row in block['table']['translated_rows'])
    return block['translation']


def normalized_text(text):
    return ''.join(plain(text).split())


def safe_title(text):
    text = re.sub(r'\s+', ' ', text).strip()
    text = text.replace(':', ' - ')
    text = text.translate(str.maketrans('<>"/\\|?*', '＜＞＂／＼｜？＊'))
    text = re.sub(r'\s+', ' ', text).rstrip(' .')
    if not text or any(ord(c) < 32 for c in text):
        raise ValueError('Invalid or empty title')
    return text


TRANSLATION_SUFFIX = '_双语左右对照翻译'


def document_filename(source_title=None, chinese_title=None, document_id=None, *,
                      role, version=None, source_is_chinese=False, paper=False,
                      vendor=None, english_document_id=None):
    """Format agent-confirmed identity only; never infer roles, IDs or move files."""
    if role not in ('original', 'generated-translation', 'official-chinese'):
        raise ValueError('Explicit original, generated-translation or official-chinese role required')
    ti = isinstance(vendor, str) and vendor.casefold() == 'ti'
    def number(value):
        if value is None or not str(value).strip():
            return None
        text = str(value).strip()
        if ti:
            text = text.lower()
            if not re.fullmatch(r'[a-z]+\d+[a-z]*', text):
                raise ValueError('Invalid TI document number')
        return safe_title(text)
    def title(value):
        text = safe_title(value or '')
        while text.endswith(TRANSLATION_SUFFIX):
            text = text[:-len(TRANSLATION_SUFFIX)].rstrip()
        if not text:
            raise ValueError('Missing actual title')
        return text
    chinese = source_is_chinese or role == 'official-chinese'
    translated = title((source_title or chinese_title) if chinese else chinese_title)
    if version is not None and str(version).strip():
        revision = '（' + safe_title(str(version).strip().strip('（）()')) + '）'
        while translated.endswith(revision):
            translated = translated[:-len(revision)]
        translated += revision
    fields = []
    if not paper:
        if ti and role == 'official-chinese':
            fields.append(number(english_document_id))
        fields.append(number(document_id))
    if not chinese:
        fields.append(title(source_title))
    fields.append(translated)
    stem = '_'.join(x for x in fields if x)
    if role == 'generated-translation':
        stem += TRANSLATION_SUFFIX
    filename = stem + '.pdf'
    if len(filename.encode('utf-16-le')) // 2 > 255:
        raise ValueError('Filename too long; propose a shorter subtitle before renaming')
    if re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', stem.split('.')[0]):
        raise ValueError('Reserved Windows filename')
    return filename


def ti_filename(english_title=None, chinese_title=None, document_id=None, *,
                role, english_document_id=None, version=None):
    """TI wrapper; callers must now specify the actual file role explicitly."""
    return document_filename(english_title, chinese_title, document_id, role=role,
                             version=version, vendor='TI',
                             english_document_id=english_document_id)


def page_fingerprint(state, page_number):
    """Conservative semantic dependency hash; default context is the whole book."""
    page = next(p for p in state['pages'] if p['source_page'] == page_number)
    if page.get('context_reviewed') is True and 'context_pages' in page:
        nums = set(page['context_pages']) | {page_number}
    elif state.get('layout',{}).get('review_profile')=='practical':
        nums = {page_number, *page.get('context_pages',[])}
    else:
        nums = {p['source_page'] for p in state['pages']}
    return canonical({'source_sha256': state['source']['sha256'], 'layout': state['layout'],
                      'glossary': state['glossary'], 'issues': state['issues'],
                      'pages': [p for p in state['pages'] if p['source_page'] in nums]})


def pagination_items(state):
    """Validate optional, agent-confirmed page labels; never infer numbering from a PDF."""
    strategy = state.get('layout', {}).get('pagination_strategy')
    pages = state.get('pages', [])
    if strategy is None:
        if any('pagination' in p for p in pages):
            raise ValueError('Page labels require layout.pagination_strategy')
        return []
    if strategy not in ('preserve-source', 'physical-total'):
        raise ValueError('Unknown pagination strategy')
    ids = {b['id'] for p in pages for b in p.get('blocks', [])}
    items = []
    for page in pages:
        label = page.get('pagination')
        n = page['source_page']
        if not isinstance(label, dict) or 'source_label' not in label or 'text' not in label:
            raise ValueError('Missing confirmed pagination record for page %s' % n)
        original, text = label['source_label'], label['text']
        if original is not None and (not isinstance(original, str) or not original.strip()):
            raise ValueError('Invalid source page label')
        if not isinstance(text, str):
            raise ValueError('Page label text must be a string')
        total = state.get('source',{}).get('page_count',len(pages)) if state.get('schema_version') == 3 else len(pages)
        expected = (original or '') if strategy == 'preserve-source' else '%s/%s' % (n, total)
        if text != expected or (strategy == 'physical-total' and original is not None):
            raise ValueError('Page label conflicts with confirmed numbering strategy')
        if not text or (state.get('schema_version') == 3 and strategy == 'preserve-source'):
            continue
        bid = label.get('id')
        box = label.get('target_bbox')
        size = label.get('font_size')
        if not isinstance(bid, str) or not bid or bid in ids:
            raise ValueError('Invalid or duplicate page-label ID')
        if (not isinstance(box, list) or len(box) != 4 or
                not all(type(v) in (int, float) and math.isfinite(v) for v in box) or
                box[2] <= box[0] or box[3] <= box[1]):
            raise ValueError('Invalid page-label target box')
        if type(size) not in (int, float) or not math.isfinite(size) or size <= 0:
            raise ValueError('Invalid page-label font size')
        ids.add(bid)
        items.append((n, {**label, 'kind': 'header', 'translation': text}))
    return items


def check_fonts(state_path, assignments_path):
    from fontTools.ttLib import TTFont
    state_path, assignments_path = Path(state_path), Path(assignments_path)
    state, assignments = load(state_path), load(assignments_path)
    errors, unverified = [], []
    fonts, font_records = {}, []
    for reg in state['layout']['fonts']:
        if reg.get('name') in fonts:
            errors.append({'code': 'duplicate_font_name', 'font': reg['name']})
            continue
        try:
            fp = resolve(state_path.parent, reg['source'])
            if digest(fp) != reg['sha256']:
                raise ValueError('Font fingerprint changed')
            font = TTFont(fp, fontNumber=reg.get('face_index', 0))
            cmap = font.getBestCmap() or {}
            fonts[reg['name']] = {u for u, g in cmap.items() if font.getGlyphID(g) != 0}
            font.close()
            font_records.append({'name': reg['name'], 'sha256': reg['sha256']})
        except Exception as exc:
            unverified.append({'font': reg.get('name'), 'reason': str(exc)})
    actual_output = digest(resolve(state_path.parent, state['output']['path']))
    if assignments.get('output_sha256') != actual_output:
        errors.append({'code': 'stale_font_assignments'})
    runs = assignments.get('runs', [])
    if not isinstance(runs, list) or (not runs and any(b.get('method') != 'preserve' for p in state['pages'] for b in p['blocks'])):
        errors.append({'code': 'missing_font_runs'})
        runs = []
    blocks = {b['id']: (p['source_page'], b) for p in state['pages'] for b in p['blocks']}
    try:
        blocks.update({b['id']: (n, b) for n, b in pagination_items(state)})
    except (KeyError, TypeError, ValueError) as exc:
        errors.append({'code': 'invalid_pagination', 'detail': str(exc)})
    texts = {}
    fallback_count = 0
    for run in runs:
        bid, name, txt = run.get('block'), run.get('font'), run.get('text')
        if bid not in blocks or run.get('page') != blocks[bid][0] or not isinstance(txt, str):
            errors.append({'code': 'invalid_font_run', 'block': bid})
            continue
        texts[bid] = texts.get(bid, '') + txt
        if run.get('fallback_from'):
            fallback_count += 1
        if name not in fonts:
            unverified.append({'block': bid, 'font': name, 'reason': 'No verified assigned font'})
            continue
        missing = sorted({ord(c) for c in txt if not c.isspace() and ord(c) not in fonts[name]})
        if missing:
            errors.append({'code': 'missing_assigned_glyph', 'page': run['page'],
                           'block': bid, 'font': name,
                           'codepoints': [f'U+{x:04X}' for x in missing]})
    for bid, (n, block) in blocks.items():
        if state.get('schema_version') == 3 and block.get('method') == 'preserve':
            continue
        if normalized_text(texts.get(bid, '')) != normalized_text(block_text(block)):
            errors.append({'code': 'font_run_text_mismatch', 'page': n, 'block': bid})
    return {'schema_version': 1, 'tool': 'pdf-bilingual-parallel-translate/check-fonts',
            'output_sha256': actual_output, 'assignments_sha256': digest(assignments_path),
            'fonts': font_records, 'fallback_runs': fallback_count, 'errors': errors,
            'unverified': unverified, 'mechanical_pass': not errors and not unverified,
            'note': 'Checks declared draw-time font assignment, not final PDF glyph appearance. '
                    'Unsupported fonts remain unverified; inspect the final rendered pages.'}


def validate_reviews(state, state_path):
    """Validate records against real render files. Does not manufacture reviews."""
    errors = []
    base = Path(state_path).parent
    records = state.get('qc', {}).get('page_reviews', [])
    expected = {p['source_page'] for p in state['pages']}
    if not isinstance(records, list) or len(records) != len(expected):
        return [{'code': 'incomplete_page_review_evidence'}]
    seen = set()
    def evidence(record):
        ref = record['render_index']
        index_path = resolve(base, ref['path'])
        if digest(index_path) != ref['sha256']:
            raise ValueError('Render index changed')
        index = load(index_path)
        row = next(x for x in index['pages'] if x.get('source_page', x['output_page']) == record['page'])
        if index['output_sha256'] != record['output_sha256']:
            raise ValueError('Review references another PDF')
        if canonical(index['settings']) != index['settings_sha256']:
            raise ValueError('Render settings fingerprint invalid')
        if index['settings_sha256'] != record['settings_sha256']:
            raise ValueError('Render settings changed')
        if digest(index_path.parent / row['image']) != row['image_sha256']:
            raise ValueError('Render image changed')
        from PIL import Image
        with Image.open(index_path.parent / row['image']) as image:
            actual_pixels = hashlib.sha256(image.convert('RGB').tobytes()).hexdigest()
        if actual_pixels != row['pixel_sha256']:
            raise ValueError('Pixel fingerprint does not match actual image')
        for k in ('image_sha256', 'pixel_sha256', 'page_content_sha256'):
            if not row.get(k) or row[k] != record[k]:
                raise ValueError('Review/image/content evidence mismatch: ' + k)
        if not record.get('reviewer') or not record.get('reviewed_at') or not record.get('evidence'):
            raise ValueError('Missing actual viewer/time/evidence attribution')
    for record in records:
        if not isinstance(record, dict):
            errors.append({'code': 'invalid_page_review_evidence', 'detail': 'Record must be an object'})
            continue
        try:
            n = record['page']
            if n not in expected or n in seen:
                raise ValueError('Invalid or duplicate review page')
            seen.add(n)
            evidence(record)
            if record['output_sha256'] != state['output']['sha256']:
                raise ValueError('Stale review output')
            if record['page_content_sha256'] != page_fingerprint(state, n):
                raise ValueError('Semantic context or layout changed')
            mode = record['mode']
            if mode == 'reused':
                previous = record['previous']
                evidence(previous)
                if previous['mode'] != 'viewed' or not record.get('reuse_reason'):
                    raise ValueError('Reuse requires an original viewed record and reason')
                for k in ('page', 'pixel_sha256', 'page_content_sha256', 'settings_sha256'):
                    if previous[k] != record[k]:
                        raise ValueError('Reused page differs: ' + k)
            elif mode != 'viewed':
                raise ValueError('Page was not actually viewed')
        except (KeyError, ValueError, TypeError, OSError, StopIteration) as exc:
            errors.append({'code': 'invalid_page_review_evidence', 'page': record.get('page'),
                           'detail': str(exc)})
    if seen != expected:
        errors.append({'code': 'incomplete_page_review_evidence'})
    return errors


def validate_relocation(state, state_path, content_hash):
    """Verify each path-only hop back to an unchanged original acceptance."""
    try:
        current = state
        base = Path(state_path).resolve().parent
        seen = {Path(state_path).resolve()}
        traversed = False
        while 'migration' in current:
            migration = current['migration']
            if (migration['kind'] != 'path-only' or not migration.get('performed_at') or
                    not migration.get('reason')):
                return False
            ref = migration['previous_state']
            previous_path = resolve(base, ref['path']).resolve()
            if previous_path in seen or digest(previous_path) != ref['sha256']:
                return False
            seen.add(previous_path)
            previous = load(previous_path)
            if (current['qc'] != previous['qc'] or
                    current['source']['sha256'] != previous['source']['sha256'] or
                    current['output']['sha256'] != previous['output']['sha256'] or
                    migration['old_source'] != previous['source']['path'] or
                    migration['new_source'] != current['source']['path']):
                return False
            normalized = copy.deepcopy(current)
            normalized['source']['path'] = previous['source']['path']
            if content_hash(normalized) != content_hash(previous):
                return False
            # A snapshot may retain references relative to its former authoring directory.
            # Resolve that explicitly without rewriting any historical snapshot bytes.
            base = (resolve(base, ref['base_path']).resolve() if 'base_path' in ref
                    else previous_path.parent)
            if not base.is_dir():
                return False
            current = previous
            traversed = True
        return traversed and current['qc']['content_sha256'] == content_hash(current)
    except (KeyError, ValueError, TypeError, OSError, RuntimeError):
        return False


def audit_accepted(report, state):
    """Keep raw audit findings; practical readers may explicitly retain right-pane differences."""
    profile=state.get('layout',{}).get('review_profile','strict')
    if profile not in ('strict','practical'):return False
    if profile=='strict':return bool(report.get('mechanical_pass'))
    retained={d.get('finding_sha256'):d for d in state.get('qc',{}).get('audit_dispositions',[])
              if isinstance(d,dict) and d.get('decision')=='retain' and str(d.get('note','')).strip()}
    for finding in report.get('findings',[]):
        if finding['severity']!='error':continue
        if finding['code']!='right_graphics_changed_outside_recorded_regions':return False
        if canonical(finding) not in retained:return False
    return True
