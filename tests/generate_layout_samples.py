"""Generate v3 layout fixtures using a caller-supplied Chinese font."""
import argparse
import sys
from pathlib import Path

import pymupdf as fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import inplace
import pdf_tools
from workflow import check_fonts, digest, load


def generate(out, font, face_index=0):
    out, font = Path(out).resolve(), Path(font).resolve()
    scenarios = {
        'numbered': (('Cover title', 'Contents overview', 'Visitor information'), (None, 'iv', 'A-3')),
        'unnumbered': (('Cover title', 'Visitor information', None), None),
        'table': (('Walking route',), None),
    }
    results = []
    width, height = 420, 550
    for name, (titles, labels) in scenarios.items():
        folder = out / name
        folder.mkdir(parents=True, exist_ok=True)
        source, state_path = folder / 'source.pdf', folder / 'state.json'
        translations = {'Cover title': '封面', 'Contents overview': '目录',
                        'Visitor information': '访客须知', 'Walking route': '步行路线'}
        with fitz.open() as document:
            for index, title in enumerate(titles):
                page = document.new_page(width=width, height=height)
                if title:
                    page.insert_text((30, 55), title, fontsize=17)
                if labels and labels[index]:
                    page.insert_text((205, 525), labels[index], fontsize=9)
                if name == 'table':
                    for x in (30, 150, 230, 390):
                        page.draw_line((x, 120), (x, 180))
                    for y in (120, 150, 180):
                        page.draw_line((30, y), (390, y))
                    rows = [('Route', 'Minutes', 'Condition'), ('Short', '12', 'Estimated')]
                    for row, cells in enumerate(rows):
                        for x, cell in zip((36, 156, 236), cells):
                            page.insert_text((x, 139 + 30 * row), cell, fontsize=11)
                    translations.update(Route='路线', Minutes='分钟', Condition='条件',
                                        Short='较短路线', Estimated='估计值，并非保证上限')
            if source.exists():
                raise FileExistsError(source)
            document.save(source)
        inplace.extract(source, state_path)
        state = load(state_path)
        state['layout']['fonts'] = [
            {'name': 'Chinese', 'source': str(font), 'sha256': digest(font),
             'purpose': 'Local fixture', 'face_index': face_index}]
        state['layout']['pagination_strategy'] = 'preserve-source' if labels else 'physical-total'
        for page in state['pages']:
            n = page['source_page']
            page['inventory_reviewed'] = True
            source_label = labels[n - 1] if labels else None
            page['pagination'] = {'source_label': source_label,
                                  'text': (source_label or '') if labels else f'{n}/{len(titles)}'}
            if not labels:
                page['pagination'].update(id=f'p{n}-number', target_bbox=[760, 15, 815, 30], font_size=8)
            for block in page['blocks']:
                text = block['source_text']
                if text in translations:
                    block.update(method='replace', status='translated', translation=translations[text],
                                 font_size=11 if name != 'table' or text == 'Walking route' else 8.5)
                    if name == 'table' and text != 'Walking route':
                        x, y, _, _ = block['source_bbox']
                        right = 147 if x < 150 else 227 if x < 230 else 387
                        bottom = 149 if y < 150 else 179
                        block.update(kind='table-cell', allowed_bbox=[x, y, right, bottom],
                                     expansion_reason='Space in the same cell')
                else:
                    block.update(method='preserve', status='verbatim', translation=text,
                                 reason='Printed page label or numeric value')
        inplace.write_json(state_path, state)
        result = inplace.build(source, state_path, folder / 'bilingual.pdf')
        generated = load(result['state'])
        audit = pdf_tools.audit(source, result['output'], generated, dpi=120,
                                render_dir=folder / 'renders')
        fonts = check_fonts(result['state'], result['assignments'])
        check = pdf_tools.check_state(result['state'])
        for filename, report in [('audit.json', audit), ('fonts.json', fonts), ('state-check.json', check)]:
            pdf_tools.write_json(report, folder / filename)
        if not (audit['mechanical_pass'] and fonts['mechanical_pass'] and check['valid']):
            raise ValueError(f'{name}: check the audit, font and state reports in {folder}')
        repeated = inplace.build(source, state_path, folder / 'repeat.pdf')
        output_hash = digest(result['output'])
        if digest(repeated['output']) != output_hash:
            raise ValueError(f'{name}: repeated build changed bytes')
        results.append({'scenario': name, 'pages': len(titles), 'output': result['output'],
                        'sha256': output_hash, 'repeated_build_identical': True})
    pdf_tools.write_json({'samples': results}, out / 'index.json')
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--font', required=True)
    parser.add_argument('--face-index', type=int, default=0)
    args = parser.parse_args()
    generate(args.out, args.font, args.face_index)
