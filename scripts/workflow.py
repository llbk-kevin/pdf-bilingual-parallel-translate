"""Small deterministic helpers; no translation, implicit review or file renaming."""
import hashlib
import copy
import json
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


def ti_filename(english_title=None, chinese_title=None, document_id=None,
                official_chinese=False, english_document_id=None):
    """IDs must have been identified from this document, never reference matches."""
    def number(v):
        if not v:
            return None
        v = v.strip().lower()
        if not re.fullmatch(r'[a-z]+\d+[a-z]*', v):
            raise ValueError('Invalid document number')
        return v
    if official_chinese:
        fields = [number(english_document_id), number(document_id), safe_title(chinese_title or '')]
    else:
        fields = [number(document_id), safe_title(english_title or ''), safe_title(chinese_title or '')]
    stem = '_'.join(x for x in fields if x)
    if not official_chinese:
        suffix = '_双语左右对照翻译'
        while stem.endswith(suffix):
            stem = stem[:-len(suffix)]
        stem += suffix
    if len(stem + '.pdf') > 255:
        raise ValueError('Filename too long; shorten the subtitle in the approved naming table')
    return stem + '.pdf'


def page_fingerprint(state, page_number):
    """Conservative semantic dependency hash; default context is the whole book."""
    page = next(p for p in state['pages'] if p['source_page'] == page_number)
    if page.get('context_reviewed') is True and 'context_pages' in page:
        nums = set(page['context_pages']) | {page_number}
    else:
        nums = {p['source_page'] for p in state['pages']}
    return canonical({'source_sha256': state['source']['sha256'], 'layout': state['layout'],
                      'glossary': state['glossary'], 'issues': state['issues'],
                      'pages': [p for p in state['pages'] if p['source_page'] in nums]})


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
    if not isinstance(runs, list) or not runs:
        errors.append({'code': 'missing_font_runs'})
        runs = []
    blocks = {b['id']: (p['source_page'], b) for p in state['pages'] for b in p['blocks']}
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
    """Retain an old review only for byte-identical PDFs and a path-only source move."""
    try:
        migration = state['migration']
        previous_path = resolve(Path(state_path).parent, migration['previous_state']['path'])
        if digest(previous_path) != migration['previous_state']['sha256']:
            return False
        previous = load(previous_path)
        if previous['qc']['content_sha256'] != content_hash(previous):
            return False
        if state['qc'] != previous['qc']:
            return False
        if state['source']['sha256'] != previous['source']['sha256'] or state['output']['sha256'] != previous['output']['sha256']:
            return False
        normalized = copy.deepcopy(state)
        normalized['source']['path'] = previous['source']['path']
        if content_hash(normalized) != content_hash(previous):
            return False
        if not migration.get('performed_at') or not migration.get('reason'):
            return False
        return migration['kind'] == 'path-only' and migration['old_source'] == previous['source']['path'] and migration['new_source'] == state['source']['path']
    except (KeyError, ValueError, TypeError, OSError):
        return False
