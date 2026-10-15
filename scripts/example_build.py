#!/usr/bin/env python3
"""Explicit legacy v1/v2 layout builder. Use inplace.py for the default v3 workflow."""
import argparse
import copy
import io
import json
import math
import os
import re
import platform
from importlib.metadata import version
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib import colors
from pypdf import PdfReader, PdfWriter
from workflow import digest, resolve, pagination_items


def build(source, state_path, output, overwrite=False, password=None):
    state_path, output, source = map(lambda x: Path(x).resolve(), (state_path, output, source))
    if output in (source, state_path):
        raise ValueError('Output must not overwrite original or authoring state')
    destinations = [output, output.with_suffix('.state.json'), output.with_suffix('.font-runs.json')]
    if any(p.exists() for p in destinations) and not overwrite:
        raise ValueError('Output exists; use --overwrite only for selected draft artifacts')
    s = copy.deepcopy(json.loads(state_path.read_text(encoding='utf-8')))
    if digest(source) != s['source']['sha256']:
        raise ValueError('Source fingerprint changed')
    if s.get('schema_version') == 3 or s.get('layout',{}).get('mode') == 'inplace':
        raise ValueError('Version 3 in-place state requires scripts/inplace.py; legacy fallback is not automatic')
    inputs = []
    for item in s['layout'].get('inputs', []):
        dependency = resolve(state_path.parent, item['path']).resolve()
        if digest(dependency) != item['sha256']:
            raise ValueError('External input fingerprint changed')
        inputs.append({**item, 'path': str(dependency)})
    font_map = {}
    for i, reg in enumerate(s['layout']['fonts']):
        if reg['name'] in font_map:
            raise ValueError('Duplicate font registry name')
        fp = resolve(state_path.parent, reg['source']).resolve()
        if digest(fp) != reg['sha256']:
            raise ValueError('Font fingerprint changed: ' + reg['name'])
        alias = 'SkillFont' + str(i)
        pdfmetrics.registerFont(TTFont(alias, str(fp), subfontIndex=reg.get('face_index', 0)))
        reg['source'] = str(fp)
        font_map[reg['name']] = alias
    if not font_map:
        raise ValueError('At least one font is required')
    labels = dict(pagination_items(s))
    primary = next(iter(font_map))
    runs = []
    current = {}
    def rich(text):
        out = []
        preferred = current.get('font', primary)
        if preferred not in font_map:
            raise ValueError('Unknown assigned font')
        candidates = [preferred] + [f for f in font_map if f != preferred]
        for part in re.split(r'(</?(?:sub|sup)>)', text):
            if re.fullmatch(r'</?(?:sub|sup)>', part):
                out.append(part)
                continue
            for ch in part:
                assigned = next((name for name in candidates if ch.isspace() or
                                 pdfmetrics.getFont(font_map[name]).face.charToGlyph.get(ord(ch), 0)), None)
                if assigned is None:
                    raise ValueError('Missing glyph U+%04X in %s' % (ord(ch), current['id']))
                item = {'page': current['page'], 'block': current['id'], 'font': assigned, 'text': ch}
                if assigned != preferred:
                    item['fallback_from'] = preferred
                if runs and all(runs[-1].get(k) == item.get(k) for k in ('page','block','font','fallback_from')):
                    runs[-1]['text'] += ch
                else:
                    runs.append(item)
                out.append('<br/>' if ch == '\n' else '<font name="%s">%s</font>' %
                           (font_map[assigned], escape(ch)))
        return ''.join(out)
    def paragraph(text, block):
        size = block.get('font_size', s['layout'].get('body_size_pt', 10))
        style = ParagraphStyle('block', fontName=font_map[primary], fontSize=size,
                               leading=block.get('leading', size*1.3), wordWrap='CJK',
                               alignment=block.get('alignment', 0))
        return Paragraph(rich(text), style)
    reader = PdfReader(source)
    if reader.is_encrypted and not reader.decrypt('') and (not password or not reader.decrypt(password)):
        raise ValueError('A valid user-provided password is required')
    writer = PdfWriter(clone_from=reader)
    if len(s['pages']) != len(reader.pages):
        raise ValueError('Page mapping does not cover original')
    buf = io.BytesIO()
    c = canvas.Canvas(buf, invariant=1, pageCompression=1)
    for page, original in zip(s['pages'], reader.pages):
        if original.rotation or list(original.cropbox) != list(original.mediabox) or list(original.mediabox)[:2] != [0,0]:
            raise ValueError('Example requires normalized unrotated, uncropped, zero-origin pages')
        w, h = float(original.mediabox.width), float(original.mediabox.height)
        if page['source_rect'] != [0,0,w,h]:
            raise ValueError('Source pane mapping must be 1:1')
        declared_pane = s['layout'].get('pane_width_pt', w)
        if (type(declared_pane) not in (int, float) or not math.isfinite(declared_pane)
                or abs(declared_pane-w) > 0.1):
            raise ValueError('Chinese pane width must equal source width on page %s' % page['source_page'])
        pane = w
        c.setPageSize((2*w, h))
        blocks = {b['id']: b for b in page['blocks']}
        order = page.get('reading_order', list(blocks))
        if len(order) != len(blocks) or set(order) != set(blocks):
            raise ValueError('Invalid reading order')
        for bid in order:
            b = blocks[bid]
            current.clear(); current.update(b, page=page['source_page'])
            if b.get('status') == 'pending':
                raise ValueError('Finish or explicitly skip pending block: ' + bid)
            x, y, x1, y1 = b['target_bbox']
            if x < w or x1 > w+pane or y < 0 or y1 > h:
                raise ValueError('Target box is outside Chinese pane: ' + bid)
            if b['kind'] == 'table':
                tab = b['table']
                data = [[paragraph(t, b) for t in row] for row in tab['translated_rows']]
                proportions = tab.get('col_proportions', [1]*len(data[0]))
                if len(proportions) != len(data[0]) or min(proportions) <= 0:
                    raise ValueError('Invalid table widths')
                widths = [v/sum(proportions)*(x1-x) for v in proportions]
                if min(widths) <= 6:
                    raise ValueError('Block overflow: table column narrower than padding: ' + bid)
                obj = Table(data, colWidths=widths)
                styles = [('GRID',(0,0),(-1,-1),.3,colors.grey),
                          ('VALIGN',(0,0),(-1,-1),'TOP'),
                          ('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3)]
                for a,c0,z,d in tab.get('spans', []):
                    styles.append(('SPAN',(a,c0),(z,d)))
                obj.setStyle(TableStyle(styles))
            else:
                obj = paragraph(b['translation'], b)
            drawn_w, drawn_h = obj.wrap(x1-x, h)
            if drawn_w > x1-x+.01 or drawn_h > y1-y+.01:
                raise ValueError('Block overflow: ' + bid)
            obj.drawOn(c, x, h-y-drawn_h)
            b['target_bbox'] = [x,y,x+drawn_w,y+drawn_h]
        if page['source_page'] in labels:
            label = labels[page['source_page']]
            current.clear(); current.update(label, page=page['source_page'])
            x, y, x1, y1 = label['target_bbox']
            if x < w or x1 > 2*w or y < 0 or y1 > h:
                raise ValueError('Page label is outside Chinese pane')
            obj = paragraph(label['translation'], {**label, 'alignment': 2})
            drawn_w, drawn_h = obj.wrap(x1-x, h)
            if drawn_w > x1-x+.01 or drawn_h > y1-y+.01:
                raise ValueError('Page label overflow')
            obj.drawOn(c, x, h-y-drawn_h)
            page['pagination']['target_bbox'] = [x,y,x+drawn_w,y+drawn_h]
        c.showPage()
    c.save(); buf.seek(0)
    overlay = PdfReader(buf)
    for page, added in zip(writer.pages, overlay.pages):
        page.mediabox.upper_right = added.mediabox.upper_right
        page.cropbox.upper_right = page.mediabox.upper_right
        page.merge_page(added, over=True)
        page.compress_content_streams()
    writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('wb' if overwrite else 'xb') as f:
        writer.write(f)
    s['source']['path'] = str(source)
    s['output'] = {'path': str(output), 'sha256': digest(output)}
    s['qc'] = {}
    s['layout']['runtime'] = {'python': platform.python_version(),
                              'pypdf': version('pypdf'), 'reportlab': version('reportlab')}
    s['layout']['builder'] = {'path': str(Path(__file__).resolve()), 'sha256': digest(__file__)}
    workflow_path = Path(__file__).with_name('workflow.py').resolve()
    s['layout']['inputs'] = [i for i in inputs if Path(i['path']) != workflow_path] + [
        {'path': str(workflow_path), 'sha256': digest(workflow_path)}]
    for p, data in [(destinations[1],s), (destinations[2],{'schema_version':1,
                    'output_sha256':s['output']['sha256'], 'runs':runs})]:
        p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'output':str(output),'state':str(destinations[1]),'assignments':str(destinations[2]),
            'sha256':s['output']['sha256']}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',required=True);ap.add_argument('--state',required=True)
    ap.add_argument('--output',required=True);ap.add_argument('--overwrite',action='store_true')
    ap.add_argument('--password-env')
    a = ap.parse_args()
    password = os.environ.get(a.password_env) if a.password_env else None
    if a.password_env and password is None:
        raise ValueError('Password environment variable is unavailable')
    print(json.dumps(build(a.source,a.state,a.output,a.overwrite,password),ensure_ascii=False))

if __name__ == '__main__':
    main()
