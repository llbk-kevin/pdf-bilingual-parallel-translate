#!/usr/bin/env python3
"""State-driven runner for preparing, building, reviewing and publishing PDFs."""
from __future__ import annotations
import argparse
import copy
import datetime
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
import subprocess
import uuid
import time
from pathlib import Path
import inplace as ip
import pdf_tools as pt
import workflow as wf
import edit_checks as ec
from resources import worker_request


def worker_count(args):
    return worker_request(getattr(args, 'workers', 'auto'))


def runtime_packages():
    from importlib.metadata import version
    return {p: version(p) for p in ('pypdf', 'pypdfium2', 'pymupdf', 'Pillow', 'fonttools', 'psutil')}


def check_runtime(state):
    expected = state['layout']['runtime_packages']
    current = runtime_packages()
    changed = {p: {'expected': v, 'actual': current.get(p)} for p, v in expected.items()
               if current.get(p) != v}
    if changed:
        raise ValueError(json.dumps({'code': 'frozen_runtime_changed', 'packages': changed,
                                     'action': 'Use the Python environment recorded at prepare.'}))


def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(path,value):ip.write_json(path,value)
def load(path):return wf.load(path)
def source_path(state,path):return wf.resolve(Path(path).parent,state['source']['path']).resolve()
def ref(path,base):return ip.relative(path,base)
def compact_inventory(state):
    keys=('id','source_group','source_line','source_text','source_bbox','method','translation','font_size','rotation','hidden_ocr')
    return {'pages':[{'page':p['source_page'],'width':p['geometry']['width'],'height':p['geometry']['height'],
                     'blocks':[{k:b[k] for k in keys if k in b} for b in p['blocks']]} for p in state['pages']]}


def adjacent_prose(a, b):
    if a.get('rotation',0) or b.get('rotation',0):
        return False
    ra,rb=ip.rect(a['source_bbox']),ip.rect(b['source_bbox'])
    size=max(1,min(a.get('font_size',ra.height),b.get('font_size',rb.height)))
    if abs((ra.y0+ra.y1-rb.y0-rb.y1)/2)<max(1,min(ra.height,rb.height)*.3):
        return -.5<=rb.x0-ra.x1<=max(3,size*.8)
    return (0<=rb.y0-ra.y0<=max(ra.height,rb.height)*1.6
            and rb.y0-ra.y1<=size*.8 and abs(ra.x0-rb.x0)<=size*1.5
            and min(ra.x1,rb.x1)>max(ra.x0,rb.x0))


def grouped_inventory(state):
    """Expose consecutive source runs, not inferred semantic paragraphs."""
    pages = []
    for page in state['pages']:
        groups = []
        previous = None
        for block in page['blocks']:
            number = block.get('source_group')
            key = (number, block.get('rotation',0), block['method'],
                   wf.canonical(block.get('table')))
            line = block.get('source_line')
            contiguous = (previous is not None and key == previous[0]
                          and number is not None and block['method'] != 'cover')
            if contiguous and isinstance(line,int) and isinstance(previous[1],int):
                contiguous = previous[1] <= line <= previous[1]+1
            if contiguous:
                contiguous = (adjacent_prose(prior_block, block)
                              and not ip.separated_blocks(page,[prior_block,block]))
            if not contiguous:
                groups.append({'id':block['id'], 'source_group':number,
                               'rotation':block.get('rotation',0), 'method':block['method'],
                               'block_ids':[], 'source_bbox':list(block['source_bbox']),
                               'source_text':'', 'blocks':[]})
            group = groups[-1]
            group['block_ids'].append(block['id'])
            group['blocks'].append({k:block[k] for k in
                ('id','source_text','source_bbox','source_line','method','rotation') if k in block})
            group['source_text'] = ' '.join(b['source_text'] for b in group['blocks'])
            group['source_bbox'] = ip.box(ip.rect(group['source_bbox']) | ip.rect(block['source_bbox']))
            previous = (key,line)
            prior_block = block
        pages.append({'page':page['source_page'],'groups':groups})
    return {'pages':pages}


def editing_materials(state):
    groups = grouped_inventory(state)
    pages = {p['source_page']:p for p in state['pages']}
    edits = []
    for page in groups['pages']:
        blocks = {b['id']:b for b in pages[page['page']]['blocks']}
        for group in page['groups']:
            if group['method'] != 'unresolved':
                continue
            first = blocks[group['block_ids'][0]]
            edit = {'page':page['page'],'id':first['id'],'method':'replace','translation':'',
                    'font_size':first.get('font_size',10),'font_size_min':None}
            if len(group['block_ids'])>1:
                edit['merge_ids'] = group['block_ids'][:]
            edits.append(edit)
    return groups, {'blocks':edits}


def save_editing_materials(directory, state):
    groups, template = editing_materials(state)
    save(directory/'groups.json',groups)
    save(directory/'edits-template.json',template)


def task_state(path):
    state = wf.require_state(load(path))
    layout = state['layout']
    missing = [key for key in ('runtime_launcher','runtime_packages','inputs','fonts') if key not in layout]
    if missing:
        raise ValueError(json.dumps({'code':'incomplete_current_task_state','fields':missing}))
    return state


def state_purpose(state, sp, expected):
    candidate=bool(state.get('output'))
    valid=(candidate if expected=='candidate' else
           not candidate and (expected!='main' or not state.get('package_preview')))
    if not valid:
        author=state.get('output',{}).get('authoring_state')
        target=str(wf.resolve(sp.parent,author).resolve()) if author else str(sp)
        raise ValueError(json.dumps({'code':'wrong_state_purpose','expected':expected,
                                     'state':str(sp),'authoring_state':target,
                                      'action_argv':runtime_prefix(state,sp)+[str(wf.resolve(sp.parent,state['layout']['runtime_launcher']).parent/'pipeline.py'),'status','--state',target],
                                     'detail':'Edit/build authoring state; verify/review/publish candidate state.'}))


def runtime_prefix(state, sp):
    return [sys.executable, '-I', '-X', 'utf8',
            str(wf.resolve(sp.parent,state['layout']['runtime_launcher']).resolve())]


def probe_runtime(state, sp):
    prefix = runtime_prefix(state, sp)
    command = prefix + ['--probe']
    result = subprocess.run(command,capture_output=True,text=True,encoding='utf-8',
                            **({'creationflags':subprocess.CREATE_NO_WINDOW} if sys.platform=='win32' else {}))
    if result.returncode:
        raise ValueError(json.dumps({'code':'frozen_runtime_probe_failed','argv':command,
                                     'returncode':result.returncode,'stderr':result.stderr[-4000:]}))
    if json.loads(result.stdout) != state['layout']['runtime_packages']:
        raise ValueError('Recovery command cannot load the frozen dependency versions')
    return prefix


FROZEN_FILES = ('pipeline.py','inplace.py','pdf_tools.py','workflow.py','runtime.py','resources.py','coordination.py','task_runtime.py','vector_forms.py','edit_checks.py')


def relocate_state(state, old, new, *, move_internal=False):
    """Resolve references before changing a state's directory."""
    entries = [(state['source'], 'path'), *((f, 'source') for f in state['layout']['fonts']),
               *((item, 'path') for item in state['layout'].get('inputs', []))]
    layout = state['layout']
    if layout.get('runtime_launcher'):
        entries.append((layout, 'runtime_launcher'))
    if layout.get('builder'):
        entries.append((layout['builder'], 'path'))
    for item, key in entries:
        target = wf.resolve(old, item[key]).resolve()
        if move_internal and target.is_relative_to(old):
            target = new / target.relative_to(old)
        item[key] = ref(target, new)


def freeze_runtime(state, sp, old_runtime_dir=None):
    here = Path(__file__).resolve().parent
    for name in FROZEN_FILES:
        shutil.copy2(here/name, sp.parent/name)
    req = here.parent/'requirements.txt'
    if not req.exists():
        req = here/'requirements.txt'
    if req.exists():
        shutil.copy2(req, sp.parent/'requirements.txt')
    layout = state['layout']
    layout['runtime_packages'] = runtime_packages()
    save(sp.parent/'runtime.json', {'paths':[str(Path(p).resolve()) for p in sys.path if p],
                                   'packages':layout['runtime_packages']})
    layout['runtime_launcher'] = 'runtime.py'
    roots = {sp.parent, old_runtime_dir}
    layout['inputs'] = [item for item in layout.get('inputs', [])
                        if not (wf.resolve(sp.parent,item['path']).resolve().parent in roots
                                and Path(item['path']).name in (*FROZEN_FILES, 'runtime.json'))]
    layout['inputs'].extend({'path':name, 'sha256':wf.digest(sp.parent/name)}
                            for name in (*FROZEN_FILES, 'runtime.json'))
    layout.pop('builder', None)
    return probe_runtime(state, sp)


def commit_recovery(stage, sp):
    """Publish managed files with state last; restore existing files on failure."""
    sp.parent.mkdir(parents=True, exist_ok=True)
    names = sorted(p.name for p in stage.iterdir() if p.is_file() and p.name != sp.name) + [sp.name]
    backup = stage/'rollback'
    backup.mkdir()
    changed = []
    try:
        for name in names:
            target = sp.parent/name
            if target.exists():
                shutil.copy2(target, backup/name)
            changed.append(name)
            (stage/name).replace(target)
    except BaseException:
        for name in reversed(changed):
            target = sp.parent/name
            if (backup/name).exists():
                shutil.copy2(backup/name, target)
            else:
                target.unlink(missing_ok=True)
        raise


def task_commands(state, sp):
    prefix = runtime_prefix(state, sp)
    runner = wf.resolve(sp.parent,state['layout']['runtime_launcher']).resolve().parent/'pipeline.py'
    work = sp.parent if state.get('package_preview') else sp.parent.parent/'work'
    selection = ranges(p['source_page'] for p in state['pages'])
    return {'source_render_argv':prefix+[str(runner.with_name('pdf_tools.py')), 'render',
                str(source_path(state,sp)), '--pages',selection,'--out',str(work/'source')],
            'status_argv':prefix+[str(runner),'status','--state',str(sp)],
            'inspect_argv':prefix+[str(runner),'inspect','--state',str(sp)],
            'apply_argv':prefix+[str(runner),'apply','--state',str(sp),'--edits',str(work/'edits.json')],
            'build_argv':prefix+[str(runner),'build','--state',str(sp),'--pages',selection]}


def preflight(state, sp, source, selected, *, stream_findings=None):
    risks=[]
    with ip.open_source(source) as doc, pt.checked_reader(source) as reader:
        for page in state['pages']:
            n=page['source_page']
            if not page['glyphs']:risks.append({'page':n,'code':'image_or_outline_page','action':'Inspect source image; add local covers without hiding artwork'})
            math_blocks=[b for b in page['blocks'] if sum(c in '=±∑√∫≤≥×÷' for c in b['source_text'])>=2]
            if len(math_blocks)>=2:
                risks.append({'page':n,'code':'formula_dense_region_hint','heuristic':True,
                              'blocks':[{'id':b['id'],'bbox':b['source_bbox']} for b in math_blocks],
                              'action':'Prefer preserving original notation; this cue does not require exhaustive formula review'})
            for b in page['blocks']:
                if wf.valid_rectangle(b['source_bbox'],allow_empty=True) and not wf.valid_rectangle(b['source_bbox']):
                    risks.append({'page':n,'block':b['id'],'code':'degenerate_source_span','method':b['method'],
                                  'action':'Preserve source glyphs; zero-area spans cannot be replacement/cover regions'})
                text=b['source_text']
                if any(ord(c)<32 and c not in '\n\r\t' for c in text):
                    risks.append({'page':n,'block':b['id'],'code':'unreliable_text_encoding','action':'Read source crop; preserve formula/identifier instead of guessing'})
                if b.get('hidden_ocr'):risks.append({'page':n,'block':b['id'],'code':'hidden_ocr','action':'Cover visible scan only after checking local bounds'})
        risks.extend(ip.check_interactions(doc, selected, state, collect=True, reader=reader,
                                          stream_findings=stream_findings))
        if not doc.get_ocgs() and not any(r['code'] in {'interaction_preflight','link_action','bookmark_action','bookmark_tree'} for r in risks):
            fidelity = ip.probe_left_pane(doc, source, selected, reader)
            risks.extend(fidelity)
            native = {r['page'] for r in fidelity if r['code'] == 'native_left_required'}
            for page in state['pages']:
                if page['source_page'] in native:
                    page['native_left'] = True
    fonts = ip.load_fonts(state, sp) if state['layout']['fonts'] else {}
    coverage = set().union(*(font['coverage'] for font in fonts.values())) if fonts else set()
    for page in state['pages']:
        missing = sorted({ord(ch) for block in page['blocks'] for ch in block['source_text']
                          if ch in '©½®™°µΩ' and ord(ch) not in coverage})
        if fonts and missing:
            risks.append({'page':page['source_page'], 'code':'source_symbol_font_hint',
                          'characters':[chr(c) for c in missing], 'action':'Preserve source symbols or register a fallback font with --font.'})
    return risks


def prepare(args):
    sp=Path(args.state).resolve()
    managed={sp.parent/name for name in (*FROZEN_FILES,'runtime.json','requirements.txt','inventory.json','groups.json','edits-template.json','preflight.json',sp.name)}
    if any(Path(value).resolve() in managed for value in [args.source, *(args.font or [])]):
        raise ValueError('Recovery files must not overwrite source or font inputs')
    if sp.exists() and not args.overwrite:
        raise ValueError('State exists; use --overwrite explicitly')
    with pt.checked_reader(args.source) as reader:
        selected = ip.selected_pages(args.pages, len(reader.pages))
        streams = list(ip.check_content_streams(reader, selected))
        if streams:
            raise ValueError(json.dumps({'code':'source_content_preflight','findings':streams},
                                        ensure_ascii=False))
    sp.parent.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.prepare-',dir=sp.parent.parent) as temporary:
        stage=Path(temporary); staged=stage/sp.name
        result=ip.extract(args.source,staged,args.pages,profile=args.profile or 'practical',workers=worker_count(args))
        state=load(staged); selected=result['pages']
        state['document'].update(delivery_scope='full' if len(selected)==state['source']['page_count'] else 'sample',selected_source_pages=selected)
        for i,value in enumerate(args.font or []):
            p=Path(value).resolve()
            state['layout']['fonts'].append({'name':'Body' if i==0 else 'Fallback'+str(i),'source':ref(p,stage),
                                            'sha256':wf.digest(p),'purpose':'User-selected translation font'})
        freeze_runtime(state,staged)
        risks=preflight(state,staged,args.source,selected,stream_findings=streams)
        relocate_state(state,stage,sp.parent,move_internal=True)
        save(staged,state);save(stage/'inventory.json',compact_inventory(state));save(stage/'preflight.json',{'risks':risks})
        save_editing_materials(stage,state)
        commit_recovery(stage,sp)
    prefix=runtime_prefix(state,sp)
    return {'state':str(sp),'runner':str(sp.parent/'pipeline.py'),'command_prefix':prefix,'inventory':str(sp.parent/'inventory.json'),
            'groups':str(sp.parent/'groups.json'),'edits_template':str(sp.parent/'edits-template.json'),
            'state_written_bytes':sp.stat().st_size, 'extract_workers':result['extract_workers'], 'resources':result['resources'],
            'preflight':str(sp.parent/'preflight.json'),'pages':selected,'profile':state['layout']['review_profile'],
            'risk_counts':counts(risks), 'compatibility_blockers':counts(r for r in risks if r['code'] in
                {'interaction_preflight','link_action','bookmark_action','bookmark_tree','link_destination_outside_scope','source_pane_probe_failed'}),
            'commands':task_commands(state,sp),
            'next':'Resolve compatibility blockers in preflight.json before translation; then apply coherent groups.'}


def refreeze(args):
    old=Path(args.state).resolve(); state=task_state(old)
    if state.get('output') or state.get('package_preview'):
        raise ValueError('Refreeze requires the main authoring state')
    out=Path(args.out).resolve()
    if out.exists():
        raise ValueError('Refreeze requires a new recovery directory')
    source=source_path(state,old)
    if wf.digest(source) != state['source']['sha256']:
        raise ValueError('Source fingerprint changed')
    previous=copy.deepcopy(state['layout'])
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.refreeze-',dir=out.parent) as temporary:
        stage=Path(temporary);sp=stage/'state.json'
        relocate_state(state,old.parent,stage)
        freeze_runtime(state,sp,old.parent)
        state['qc']={};state.pop('imported_packages',None)
        with ip.open_source(source) as doc:
            for page in state['pages']:
                page['source_separators']=ip.source_separators(doc[page['source_page']-1])
        selected=[p['source_page'] for p in state['pages']]
        risks=preflight(state,sp,source,selected)
        errors=ip.validate_state(state,source)
        if errors:raise ValueError(json.dumps(errors,ensure_ascii=False))
        relocate_state(state,stage,out,move_internal=True)
        save(sp,state);save(stage/'inventory.json',compact_inventory(state));save(stage/'preflight.json',{'risks':risks})
        save_editing_materials(stage,state)
        stage.rename(out)
    sp=out/'state.json'
    return {'state':str(sp),'runner':str(out/'pipeline.py'),'command_prefix':runtime_prefix(state,sp),
            'inventory':str(out/'inventory.json'),'preflight':str(out/'preflight.json'),
            'groups':str(out/'groups.json'),'edits_template':str(out/'edits-template.json'),
            'commands':task_commands(state,sp),'dependency_changes':{'previous':wf.canonical(previous),'current':wf.canonical(state['layout'])},
            'next':'Re-export affected packages from this state; validate existing edits against their new baselines.'}


def counts(items):
    out={}
    for item in items:
        code=item.get('code','other');out[code]=out.get(code,0)+1
    return out


def pixel_edits(changes,state,sp,edits_path):
    """Map original source-render pixels using recorded DPI, never guessed UI scale."""
    if 'source_render_index' not in changes:return changes
    index_path=wf.resolve(Path(edits_path).resolve().parent,changes['source_render_index']).resolve()
    index=load(index_path)
    if index.get('output_sha256')!=state['source']['sha256'] or index.get('source_sha256'):
        raise ValueError('source_render_index must describe the original source PDF, not a bilingual candidate')
    dpi=index.get('dpi')
    if not isinstance(dpi,(int,float)) or not math.isfinite(dpi) or dpi<=0:
        raise ValueError('Source render index requires valid DPI')
    pages={p['source_page']:p for p in state['pages']}
    rows={r['output_page']:r for r in index['pages']}
    result=copy.deepcopy(changes);verified={}
    from PIL import Image
    for edit in result.get('blocks',[]):
        n=edit.get('page');page=pages.get(n);row=rows.get(n)
        if page is None or row is None:raise ValueError('Pixel edit page is absent from source render/state')
        if n not in verified:
            image_path=wf.resolve(index_path.parent,row['image'])
            if wf.digest(image_path)!=row['image_sha256']:raise ValueError('Source render image fingerprint changed')
            with Image.open(image_path) as im:size=list(im.size)
            if size!=row['pixels']:raise ValueError('Source render dimensions changed')
            w,h=page['geometry']['width'],page['geometry']['height']
            if abs(size[0]-w*dpi/72)>1.01 or abs(size[1]-h*dpi/72)>1.01:
                raise ValueError('Source render DPI does not match visible source geometry')
            verified[n]=True
        for field in ('source_bbox','cover_bbox','allowed_bbox'):
            if field not in edit:continue
            values=edit[field]
            if not isinstance(values,list) or len(values)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in values):
                raise ValueError('Pixel boxes require four finite numbers')
            x0,y0,x1,y1=values
            if not (0<=x0<x1<=row['pixels'][0] and 0<=y0<y1<=row['pixels'][1]):
                raise ValueError('Pixel box outside original unscaled render: page '+str(n))
            edit[field]=[round(v*72/dpi,6) for v in values]
    return result


def apply_package(state, sp, edits_path, changed, location, changes, *, validate=True):

    top_keys={'blocks','inventory_reviewed_pages','context_pages','link_overrides','link_overrides_patch','glossary','source_render_index'}
    if 'issues' in changes:
        raise ValueError('Record delivery notes separately in the task work/delivery-notes.json')
    if not isinstance(changes,dict) or not changes or set(changes)-top_keys:
        raise ValueError('Edit JSON must be a nonempty object using blocks, inventory_reviewed_pages, context_pages, link_overrides, link_overrides_patch or glossary; unknown top-level keys are not accepted')
    changes=pixel_edits(changes,state,sp,edits_path)
    allowed={'translation','method','reason','font_size','font_size_min','font_size_step','leading','allowed_bbox',
             'cover_bbox','cover_fill','cover_text_color','expansion_reason','kind','figure_id','rotation','font','color','source_text','source_bbox','table'}
    pages={p['source_page']:p for p in state['pages']}
    for edit in changes.get('blocks',[]):
        n=edit.get('page');page=pages.get(n)
        location.update(page=n, block=edit.get('id'))
        if page is None:raise ValueError(f'Edit must specify an inventoried source page: {n}, block {edit.get("id")}')
        bid=edit['id'];existing=next((b for b in page['blocks'] if b['id']==bid),None)
        if edit.get('split'):
            if set(edit)-{'page','id','split'} or existing is None or not existing.get('merged_from'):
                raise ValueError('split requires an existing merged block and no other edits')
            with ip.open_source(source_path(state,sp)) as doc:
                _, originals=ip.text_inventory(doc[n-1],n)
            owned=set(existing['glyph_ids'])
            parts=[b for b in originals if set(b['glyph_ids'])<=owned]
            if (len(parts)<2 or {g for b in parts for g in b['glyph_ids']}!=owned
                    or any(b['id'] in {v['id'] for v in page['blocks'] if v is not existing} for b in parts)):
                raise ValueError('Merged block cannot be restored to complete source spans')
            page.setdefault('split_notes',[]).append({'id':bid,'translation':existing.get('translation',''),
                                                     'restored_ids':[b['id'] for b in parts]})
            pos=page['blocks'].index(existing)
            page['blocks'][pos:pos+1]=parts
            changed.add(n)
            continue
        merge=edit.get('merge_ids')
        if merge:
            parts=[next((b for b in page['blocks'] if b['id']==x),None) for x in merge]
            missing = [source_id for source_id, part in zip(merge, parts) if part is None]
            if missing or len(set(merge)) != len(merge):
                raise ValueError(json.dumps({
                    'code': 'invalid_merge_ids', 'page': n, 'block': bid, 'missing_ids': missing,
                    'duplicate_ids':sorted({x for x in merge if merge.count(x)>1}),
                    'current_owner_hints':{x:[b['id'] for b in page['blocks'] if x in b.get('merged_from',[])] for x in missing},
                    'detail': 'Merge requires unique current source IDs. After a successful merge, edit the merged ID without merge_ids.',
                }, ensure_ascii=False))
            if existing is not None and bid not in merge:raise ValueError('Merged ID collides with another block')
            if ip.separated_blocks(page,parts):
                raise ValueError(json.dumps({'code':'merge_crosses_separator','page':n,'block':bid,
                                             'detail':'Keep text on opposite sides of a source separator separate.'}))
            pos=min(page['blocks'].index(b) for b in parts)
            existing=copy.deepcopy(parts[0]);existing['id']=bid
            existing['glyph_ids']=[g for b in parts for g in b['glyph_ids']]
            existing['glyph_ranges']=[[0,len(existing['glyph_ids'])]]
            existing['merged_from']=sorted({x for b in parts for x in [b['id'],*b.get('merged_from',[])]})
            r=ip.rect(parts[0]['source_bbox'])
            for b in parts[1:]:r|=ip.rect(b['source_bbox'])
            existing.update(source_bbox=ip.box(r),allowed_bbox=ip.box(r),source_text=' '.join(b['source_text'] for b in parts))
            page['blocks']=[b for b in page['blocks'] if b['id'] not in merge];page['blocks'].insert(pos,existing)
        elif existing is None:
            if edit.get('method')!='cover':raise ValueError('New blocks must be explicit image/outline covers')
            existing={'id':bid,'glyph_ids':[],'glyph_ranges':[],'kind':'text','rotation':0,'font_size':8,
                      'actual_bbox':None,'expansion_reason':''}
            page['blocks'].append(existing)
        for key in edit:
            if key not in allowed|{'id','page','merge_ids'}:raise ValueError('Unsupported edit key: '+key)
        existing.update({k:v for k,v in edit.items() if k in allowed})
        if existing.get('method')=='preserve':existing['translation']=existing['source_text']
        existing['status']='verbatim' if existing.get('method')=='preserve' else 'pending' if existing.get('method')=='unresolved' else 'translated'
        for k in ('actual_bbox','target_bbox'):existing[k]=None
        for k in ('actual_glyph_boxes','actual_font_size','layout_lines'):existing.pop(k,None)
        changed.add(n)
    location.clear()
    for n in changes.get('inventory_reviewed_pages',[]):
        pages[n]['inventory_reviewed']=True;pages[n]['visual_text_review']='reviewed';changed.add(n)
    for n,values in changes.get('context_pages',{}).items():
        pages[int(n)]['context_pages']=values;pages[int(n)]['context_reviewed']=True;changed.add(int(n))
    if set(changes.get('link_overrides',{})) & set(changes.get('link_overrides_patch',{})):
        raise ValueError('Use either full link_overrides or link_overrides_patch for a page')
    for n,values in changes.get('link_overrides',{}).items():
        pages[int(n)]['link_overrides']=values;changed.add(int(n))
    for n,values in changes.get('link_overrides_patch',{}).items():
        page=pages[int(n)];merged={v['source_link']:v for v in page.get('link_overrides',[])}
        for value in values:
            key=value.get('source_link')
            if type(key) is not int or key<0:raise ValueError('Link patch requires nonnegative integer source_link')
            merged[key]=value
        page['link_overrides']=[merged[k] for k in sorted(merged)];changed.add(int(n))
    if 'glossary' in changes:state['glossary']=changes['glossary']
    for n in changed:
        page = pages[n]
        page['expected_blocks']=[b['id'] for b in page['blocks']];page['reading_order']=page['expected_blocks'][:]
        if page['blocks']:page['kind']='translated'
    errors = ip.validate_state(state, source_path(state, sp), pages=changed) if validate else []
    if errors:
        raise ValueError(json.dumps(errors, ensure_ascii=False))



def package_dependencies(state):
    layout = copy.deepcopy(state['layout'])
    layout.pop('runtime_launcher',None)
    if 'builder' in layout:layout['builder'].pop('path',None)
    layout['fonts']=[{k:v for k,v in f.items() if k!='source'} for f in layout['fonts']]
    layout['inputs']=[{'name':Path(f['path']).name,'sha256':f['sha256']} for f in layout['inputs']]
    return wf.canonical([state['source']['sha256'], layout, state['glossary']])


PAGE_AUTHOR_FIELDS=('kind','reason','blocks','expected_blocks','reading_order','context_pages',
                    'context_reviewed','link_overrides','pagination','split_notes')
DRAW_FIELDS=('actual_bbox','target_bbox','actual_glyph_boxes','actual_font_size','layout_lines')


def page_authoring(page):
    result=copy.deepcopy({k:page[k] for k in PAGE_AUTHOR_FIELDS if k in page})
    for block in result['blocks']:
        for key in DRAW_FIELDS:block.pop(key,None)
    return result


def page_baseline(page):
    return wf.canonical([page['source_page'],page['geometry'],page['glyphs'],page_authoring(page)])


def check_package_inputs(state, path, digests):
    check_runtime(state)
    for item, key in [(state['source'], 'path'), *((f, 'source') for f in state['layout']['fonts']),
                      *((f, 'path') for f in state['layout']['inputs'])]:
        asset = wf.resolve(path.parent, item[key]).resolve()
        if asset not in digests:
            digests[asset] = wf.digest(asset)
        if digests[asset] != item['sha256']:
            raise ValueError('Package dependency bytes changed: '+item[key])


def merge_package(directory, main, source_hash, dependencies, journal, assigned, digests):
    meta = load(directory/'package.json')
    package_path = directory/'state.json'
    package_state = task_state(package_path)
    if not package_state.get('package_preview') or package_state.get('output'):
        raise ValueError('Import the package authoring state, not its candidate')
    scope=meta['pages'];pages={p['source_page']:p for p in package_state['pages']}
    if (len(pages)!=len(package_state['pages']) or len(set(scope))!=len(scope) or set(pages)!=set(scope) or not set(scope)<=main.keys()
            or meta['id']!=wf.canonical([meta['dependencies'],meta['baseline']])
            or set(meta['baseline'])!={str(n) for n in scope}):
        raise ValueError('Invalid package assignment or baseline')
    overlap = assigned.intersection(scope)
    if overlap:
        raise ValueError(json.dumps({'code':'overlapping_packages','pages':sorted(overlap)}))
    assigned.update(scope)
    if (meta['source_sha256'] != source_hash or dependencies != meta['dependencies']
            or package_dependencies(package_state) != dependencies):
        raise ValueError('Package source/shared dependencies changed; export the affected pages again')
    check_package_inputs(package_state, package_path, digests)
    errors = ip.validate_state(package_state, source_path(package_state, package_path))
    if errors:
        raise ValueError(json.dumps({'code':'invalid_package_pages','findings':errors},ensure_ascii=False))
    signature=wf.canonical({str(n):page_authoring(pages[n]) for n in scope})
    if any(r['package']==meta['id'] and r['result']==signature for r in journal):
        stale = [n for n in scope if page_baseline(main[n]) != page_baseline(pages[n])]
        if stale:
            raise ValueError(json.dumps({'code':'package_baseline_changed','pages':stale}))
        return set()
    stale=[n for n in scope if page_baseline(main[n])!=meta['baseline'][str(n)]]
    if stale:raise ValueError(json.dumps({'code':'package_baseline_changed','pages':stale}))
    for n in scope:
        destination=main[n]
        for key in PAGE_AUTHOR_FIELDS:destination.pop(key,None)
        destination.update(page_authoring(pages[n]))
        for block in destination['blocks']:
            block.update(actual_bbox=None,target_bbox=None)
        destination.update(inventory_reviewed=False,visual_text_review='pending')
    journal.append({'package':meta['id'],'result':signature,'pages':scope,'imported_at':now()})
    return set(scope)


def import_package(args):
    sp = Path(args.state).resolve()
    state = task_state(sp)
    state_purpose(state, sp, 'main')
    directories = [args.package] if isinstance(args.package, (str, Path)) else args.package
    main = {p['source_page']:p for p in state['pages']}
    journal = state.setdefault('imported_packages',[])
    dependencies = package_dependencies(state)
    digests, assigned, changed = {}, set(), set()
    check_package_inputs(state, sp, digests)
    for path in directories:
        directory = Path(path).resolve()
        try:
            changed.update(merge_package(directory, main, state['source']['sha256'], dependencies,
                                         journal, assigned, digests))
        except (ValueError, TypeError, KeyError, OSError) as exc:
            try:
                detail = json.loads(str(exc))
            except ValueError:
                detail = str(exc)
            raise ValueError(json.dumps({'code':'package_import_failed','package':str(directory),
                                         'detail':detail},ensure_ascii=False)) from exc
    if not changed:
        return {'state':str(sp),'changed_pages':[],'state_written_bytes':0,'next':'Package results already imported.'}
    errors = pt.check_state(sp, state=state)['errors']
    if errors:
        raise ValueError(json.dumps({'code':'merged_state_invalid','findings':errors},ensure_ascii=False))
    return save_edits(state, sp, changed)


def package(args):
    sp = Path(args.state).resolve()
    state = task_state(sp)
    if state.get('output') or state.get('package_preview'):
        raise ValueError('Export packages from the main authoring state')
    out = Path(args.out).resolve()
    pages = {p['source_page']: p for p in state['pages']}
    selection = ip.selected_pages(args.pages, state['source']['page_count'])
    if not set(selection) <= pages.keys() or selection != list(range(selection[0], selection[-1]+1)):
        raise ValueError('A package needs one contiguous range of inventoried source pages')
    if out.exists():
        raise ValueError('Use a new package directory')
    dependencies = package_dependencies(state)
    neighbors = sorted({selection[0]-1, selection[-1]+1} & pages.keys())
    compact = {p['page']: p for p in compact_inventory({'pages': [pages[n] for n in neighbors]})['pages']}
    baseline = {str(n): page_baseline(pages[n]) for n in selection}
    metadata = {'schema_version': 1, 'pages': selection, 'baseline': baseline,
                'dependencies': dependencies,
                'id': wf.canonical([dependencies, baseline]),
                'owner': getattr(args, 'owner', None),
                'source_sha256': state['source']['sha256']}
    metadata['adjacent_pages'] = neighbors
    state['document']['final_source_pages'] = state['document'].get('final_source_pages', state['document']['selected_source_pages'])
    state['pages'] = [pages[n] for n in selection]
    state['document'].update(delivery_scope='sample', selected_source_pages=selection)
    for j, page in enumerate(state['pages'], 1):
        page['output_page'] = j
    state['qc'] = {}
    state.pop('output', None)
    state.pop('imported_packages', None)
    state['package_preview'] = True
    for entry, key in [(state['source'], 'path'), *((f, 'source') for f in state['layout']['fonts']),
                       *((asset, 'path') for asset in state['layout'].get('inputs', []))]:
        entry[key] = ref(wf.resolve(sp.parent, entry[key]), out)
    state['layout']['runtime_launcher'] = ref(wf.resolve(sp.parent,state['layout']['runtime_launcher']),out)
    builder = state['layout'].get('builder')
    if builder:
        builder['path'] = ref(wf.resolve(sp.parent, builder['path']), out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.package-', dir=out.parent) as temporary:
        stage = Path(temporary)/'ready'
        save(stage/'package.json', metadata)
        save(stage/'state.json', state)
        save(stage/'inventory.json', compact_inventory(state))
        save_editing_materials(stage,state)
        save(stage/'context.json', {'read_only': list(compact.values())})
        stage.rename(out)
    return {'id': metadata['id'], 'pages': selection, 'state': str(out/'state.json'),
            'inventory': str(out/'inventory.json'), 'context': str(out/'context.json'),
            'groups':str(out/'groups.json'),'edits_template':str(out/'edits-template.json'),
            'package': str(out/'package.json'), 'command_prefix':runtime_prefix(state,out/'state.json'),
            'commands':{**task_commands(state,out/'state.json'),
                        'import_argv':runtime_prefix(task_state(sp),sp)+[str(Path(__file__).resolve()),
                            'import-package','--state',str(sp),'--package',str(out)]}}


def edit_pages(changes):
    return ({b['page'] for b in changes.get('blocks', [])}
            | set(changes.get('inventory_reviewed_pages', []))
            | {int(n) for key in ('context_pages', 'link_overrides', 'link_overrides_patch')
               for n in changes.get(key, {})})


def package_status(state, directory, built, reviewed, published):
    meta = load(directory/'package.json')
    local = load(directory/'state.json')
    saved = sorted(p['source_page'] for p in local['pages']
                   if not any(b['method']=='unresolved' for b in p['blocks']))
    applied = [n for item in state.get('imported_packages', []) if item['package'] == meta['id']
               for n in item['pages']]
    scope = set(meta['pages'])
    return {'id': meta['id'], 'owner': meta.get('owner'), 'pages': ranges(scope),
            'saved_edits': ranges(saved), 'applied_edits': ranges(applied),
            'built_pages': ranges(scope & built), 'reviewed_pages': ranges(scope & reviewed),
            'published_pages': ranges(scope & published), 'adjacent_pages': meta['adjacent_pages']}


def apply_edits(args):
    sp = Path(args.state).resolve()
    state = task_state(sp); state_purpose(state,sp,'author')
    paths = [args.edits] if isinstance(args.edits, (str, Path)) else args.edits
    changed=set();structure_errors=[];failed_targets=set();origins=[]
    for edits_path in paths:
        try:
            changes=pixel_edits(load(edits_path),state,sp,edits_path)
            origins.extend((str(edits_path),edit) for edit in changes.get('blocks',[]))
            changes.pop('source_render_index',None)
            touched,errors=ec.structure_check(state,changes,apply_package,sp,edits_path,failed_targets)
            changed.update(touched);structure_errors.extend(errors)
        except (ValueError,KeyError,TypeError,OSError) as exc:
            structure_errors.append({'edit_file':str(edits_path),'detail':str(exc)})
    if changed:
        for finding in ip.validate_state(state,source_path(state,sp),pages=changed):
            matching=[(path,edit['id']) for path,edit in origins if edit.get('page')==finding.get('page')
                      and edit.get('id') and edit['id'] in finding.get('detail','')]
            if len(matching)==1:finding.update(edit_file=matching[0][0],block=matching[0][1])
            else:finding['edit_files']=sorted({path for path,edit in origins if edit.get('page')==finding.get('page')})
            structure_errors.append(finding)
    if structure_errors:
        raise ValueError(json.dumps({'code':'invalid_edit_batch','edit_errors':structure_errors},ensure_ascii=False))
    return save_edits(state,sp,changed)


def save_edits(state,sp,changed):
    state['qc'] = {}
    state.pop('output', None)
    # The state is authoritative. Stage both files before committing the state.
    with tempfile.TemporaryDirectory(prefix='.apply-', dir=sp.parent) as staging:
        inventory = Path(staging) / 'inventory.json'
        save(inventory, compact_inventory(state))
        save(sp, state)
        inventory.replace(sp.parent / inventory.name)
    # Translation stays saved even when layout still needs work.
    layout_report,preflight=ec.run(state,sp,changed)
    layout_path = sp.parent / 'apply-layout.json'
    save(layout_path, layout_report)
    pending_pages = {p['source_page'] for p in state['pages'] if any(b['method']=='unresolved' for b in p['blocks'])}
    blocked = {}
    for n in changed & pending_pages:
        blocked[n] = {'pending_translation'}
    for finding in layout_report['findings']:
        affected = {finding['page']} if finding.get('page') in changed else changed
        for n in affected:
            blocked.setdefault(n,set()).add(finding.get('code','layout_check_failed'))
    for n in changed & set(preflight['preflight_unchecked_pages']):
        if n not in blocked:blocked[n]={'preflight_unchecked'}
    ready_pages = changed - set(blocked)
    preview = runtime_prefix(state, sp) + [str(wf.resolve(sp.parent,state['layout']['runtime_launcher']).parent/'pipeline.py'),'build','--state',str(sp),'--pages',ranges(ready_pages)] if ready_pages else None
    unresolved = [
        {'page': page['source_page'], 'blocks': [b['id'] for b in page['blocks'] if b['method'] == 'unresolved']}
        for page in state['pages']
    ]
    unresolved = [row for row in unresolved if row['blocks']]
    return {'state':str(sp),'changed_pages':sorted(changed),'preview_argv':preview,**preflight,
            'layout_check':{'counts':layout_report['counts'],'groups':layout_report['groups'],'details':str(layout_path)},
            'state_written_bytes':sp.stat().st_size,
             'preview_skipped_pages':sorted(blocked),
             'preview_blocked_by_page':[{'page':n,'reasons':sorted(blocked[n])} for n in sorted(blocked)],
             'unresolved_count':sum(len(row['blocks']) for row in unresolved),
            'unresolved_by_page':unresolved,
            'next':('Fix pages '+ranges(blocked)+' using saved layout details or unresolved blocks. ' if blocked else '')
                    +('Preview ready pages '+ranges(ready_pages)+' using the returned action. ' if ready_pages else 'No preview is ready. ')
                    +('Resolve full-document preflight pages '+ranges(set(preflight['preflight_blocked_pages'])|set(preflight['preflight_unchecked_pages']))
                      if preflight['preflight_blocked_pages'] or preflight['preflight_unchecked_pages'] else 'Build the full selection when all pages are ready')
                    +'; reuse reviews with verify --previous-state.'}


def ranges(numbers):
    parts = []
    for number in sorted(set(numbers)):
        if parts and parts[-1][1] == number - 1:
            parts[-1][1] = number
        else:
            parts.append([number, number])
    return ','.join(str(a) if a == b else f'{a}-{b}' for a, b in parts)


def candidate_progress(sp, state, selected):
    output = state.get('output')
    if not output:
        return set(), set(), set(), False, None
    path = wf.resolve(sp.parent, output['path'])
    if not path.is_file() or wf.digest(path) != output['sha256']:
        return set(), set(), set(), False, 'candidate_missing_or_changed'
    built = {p['source_page'] for p in state['pages']} & selected
    qc = state.get('qc', {})
    if not qc.get('audit_path') or qc.get('output_sha256') != output['sha256']:
        return built, set(), set(), False, None
    audit_path = wf.resolve(sp.parent, qc['audit_path'])
    manifest = audit_path.parent/'verification.json'
    if not audit_path.is_file() or not manifest.is_file():
        return built, set(), set(), False, 'audit_missing'
    files = load(manifest).get('files', {})
    if files.get(str(audit_path.resolve())) != wf.digest(audit_path):
        return built, set(), set(), False, 'audit_changed'
    if qc.get('content_sha256') != pt.content_hash(state):
        return built, set(), set(), False, 'candidate_state_changed'
    viewed, _ = wf.checked_page_reviews(state, sp, pages=built)
    reviewed = set(viewed)
    report = load(audit_path)
    decisions = {d['finding_sha256'] for d in qc.get('audit_dispositions', [])}
    blockers = [f for f in report['findings'] if f['severity'] == 'error'
                and not (state['layout']['review_profile'] == 'practical'
                         and f['code'] in ('right_graphics_changed_outside_recorded_regions','preserved_duplicate_reduced')
                         and wf.canonical(f) in decisions)]
    reviewed -= {f.get('page') for f in blockers}
    record_path = sp.parent/'publication.json'
    published = set()
    if record_path.is_file() and not blockers and not output.get('preview'):
        record = load(record_path)
        if (record.get('output') == str(path.resolve()) and record.get('state') == str(sp)
                and record.get('output_sha256', output['sha256']) == output['sha256']):
            published = reviewed
    reason = 'audit_blocker' if any(
        f.get('page') is None or f['code'] not in ('right_graphics_changed_outside_recorded_regions','preserved_duplicate_reduced')
        or state['layout']['review_profile'] == 'strict' for f in blockers) else None
    font_ref = qc.get('font_report')
    if font_ref:
        font_path = wf.resolve(sp.parent, font_ref['path'])
        if (not font_path.is_file() or wf.digest(font_path) != font_ref['sha256']
                or not load(font_path)['mechanical_pass']):
            reason = 'font_check_failed_or_changed'
    return built, reviewed, published, True, reason


def status(args):
    sp = Path(args.state).resolve()
    state = task_state(sp)
    selected = set(ip.selected_pages(args.pages, state['source']['page_count']))
    pages = {p['source_page']: p for p in state['pages'] if p['source_page'] in selected}
    pending = [n for n, p in pages.items() if any(b['method'] == 'unresolved' for b in p['blocks'])]
    inventory = [n for n, p in pages.items() if not p.get('inventory_reviewed')]
    output = state.get('output', {})
    built, reviewed, published, verified, reason = candidate_progress(sp, state, set(pages))
    needs_review = set(pages) - reviewed
    preflight=ec.summary(state,sp,set(pages)) if not output else {}
    action = ('apply --edits FILE' if pending else 'build --state AUTHORING_STATE' if not output else
              'verify' if not verified else 'review --observations FILE' if needs_review or inventory else
              'build --state AUTHORING_STATE' if output.get('preview') else
              'publish --output FILE (checks final readiness)')
    blockers = [{'state': str(sp), 'reason': reason}] if reason else []
    if not output and (preflight['preflight_blocked_pages'] or preflight['preflight_unchecked_pages']):
        action='Inspect preflight_details; apply corrections or recheck affected pages before full build'
        blockers += preflight['preflight_blocked_by_page']
    for candidate in getattr(args, 'candidate', []) or []:
        other_path = Path(candidate).resolve()
        other = wf.require_state(load(other_path))
        if other['source']['sha256'] != state['source']['sha256']:
            raise ValueError('Status candidate must come from the same source')
        # These counts describe the supplied candidate snapshots.
        b, r, p, _, reason = candidate_progress(other_path, other, set(pages))
        built.update(b)
        reviewed.update(r)
        published.update(p)
        if reason:
            blockers.append({'state': str(other_path), 'reason': reason})
    details = [package_status(state, Path(p).resolve(), built, reviewed, published)
               for p in getattr(args, 'packages', []) or []]
    return {'state': str(sp), 'pages': ranges(pages), 'translation_pending': ranges(pending),**preflight,
            'packages': details, 'built_pages': ranges(built), 'reviewed_pages': ranges(reviewed),
            'published_pages': ranges(published), 'blockers': blockers,
            'inventory_review_needed': ranges(inventory), 'review_needed': ranges(needs_review),
            'next': 'Inspect blockers before continuing' if blockers else action}


def build(args):
    sp=Path(args.state).resolve();state=task_state(sp);state_purpose(state,sp,'author');source=source_path(state,sp)
    check_runtime(state)
    garbage = getattr(args, 'garbage', None) or 4
    key=wf.canonical({'state':pt.content_hash(state),'source':wf.digest(source),'pages':args.pages,'garbage':garbage,
                      'builder':wf.digest(Path(ip.__file__)),'helper':wf.digest(Path(wf.__file__)),
                       'package_preview':state.get('package_preview', False)})
    work = sp.parent if state.get('package_preview') else sp.parent.parent/'work'
    output = Path(args.output).resolve() if args.output else work/('candidate-'+key[:16]+'.pdf')
    job_path = output.with_suffix('.job.json')
    manifest=output.with_suffix('.build.json')
    dependencies = [source, sp, *(wf.resolve(sp.parent, f['source']).resolve()
                                  for f in state['layout']['fonts'])]
    dependencies.extend(wf.resolve(sp.parent, d['path']).resolve() for d in state['layout'].get('inputs', []))
    if any(p.resolve() in dependencies for p in (job_path, manifest)):
        raise ValueError('Build diagnostics must not overwrite an input')
    if manifest.exists():
        old=load(manifest)
        if (old.get('key')==key and all(Path(p).exists() and wf.digest(p)==h for p,h in old['files'].items())
            and Path(old['result']['state']).exists() and pt.content_hash(load(old['result']['state']))==old.get('state_content')):
            return {**old['result'],'job':str(job_path) if job_path.is_file() else None,
                    'state_written_bytes':0,'cached':True,'next':'verify --state '+old['result']['state']}
    declared = {p['source_page'] for p in state['pages']}
    selected = declared if args.pages == 'all' else set(ip.selected_pages(args.pages, state['source']['page_count']))
    if output.exists() and not args.overwrite:
        raise FileExistsError(f'Candidate exists with different inputs: {output}')
    job = {'pid': os.getpid(), 'key': key, 'source': str(source), 'output': str(output),
           'state': str(sp), 'pages': sorted(selected),
           'started_at': now(), 'status': 'running'}
    def progress(event):
        job.update(event, updated_at=now())
        save(job_path, job)
    try:
        result = ip.build(source, sp, output, args.pages, args.overwrite,
                          preview=selected != declared or state.get('package_preview', False),
                          state=state, return_state=True, progress=progress, garbage=garbage)
        built_state = result.pop('_state')
    except BaseException as exc:
        progress({'status': 'failed', 'exit_reason': type(exc).__name__, 'error': str(exc)[:1200]})
        if isinstance(exc, ValueError):
            try:
                detail = json.loads(str(exc))
            except ValueError:
                detail = None
            if isinstance(detail, dict):
                detail.update(stage=job.get('stage'), job=str(job_path))
                raise ValueError(json.dumps(detail, ensure_ascii=False)) from exc
        raise
    save(manifest,{'key':key,'result':result,'state_content':pt.content_hash(built_state),
                   'files':{result[k]:wf.digest(result[k]) for k in ('output','assignments')}})
    progress({'status': 'complete', 'exit_reason': None})
    return {**result,'job':str(job_path),'cached':False,'next':'verify --state '+result['state']}


def rebase_record(record,base):
    value=copy.deepcopy(record)
    value['render_index']['path']=str(wf.resolve(base,value['render_index']['path']).resolve())
    if 'previous' in value:value['previous']=rebase_record(value['previous'],base)
    return value


def reuse_reviews(sp, index, index_path, index_hash, previous_path, old, current):
    by_page, _ = wf.checked_page_reviews(old, previous_path)
    records = []
    for row in index['pages']:
        n=row['source_page'];original=by_page.get(n)
        if not original or n in current:continue
        if original.get('mode')=='reused':original=original['previous']
        if (original['settings_sha256']!=index['settings_sha256'] or
            original['pixel_sha256']!=row['pixel_sha256'] or original['page_content_sha256']!=row['page_content_sha256']):continue
        records.append({'page':n,'mode':'reused','output_sha256':index['output_sha256'],
                        'render_index':{'path':ref(index_path,sp.parent),'sha256':index_hash},
                        'settings_sha256':index['settings_sha256'],
                        **{k:row[k] for k in ('image_sha256','pixel_sha256','page_content_sha256')},
                        'reviewer':original['reviewer'],'reviewed_at':original['reviewed_at'],
                        'evidence':original['evidence'],'previous':rebase_record(original,previous_path.parent),
                        'covers_checked':original.get('covers_checked', []),
                        'reuse_reason':'Identical pixels, settings and declared page dependencies; original observation retained.'})
    return records


def pages_needing_review(state, report, index, records):
    pending = {r['source_page'] for r in index['pages']} - records.keys()
    if state['layout']['review_profile'] == 'practical':
        decisions = {d['finding_sha256'] for d in state['qc']['audit_dispositions']}
        pending.update(f['page'] for f in report['findings']
                       if f['code'] in ('right_graphics_changed_outside_recorded_regions','preserved_duplicate_reduced')
                       and wf.canonical(f) not in decisions)
    return sorted(pending)


def verification_assignments(sp, state):
    return wf.resolve(sp.parent,state['output']['assignments'])



def verification_paths(sp, state):
    check_runtime(state)
    output = wf.resolve(sp.parent, state['output']['path'])
    source = source_path(state, sp)
    if wf.digest(source) != state['source']['sha256']:
        raise ValueError('Source fingerprint changed')
    if wf.digest(output) != state['output']['sha256']:
        raise ValueError('Candidate fingerprint changed')
    layout = state['layout']
    assets = [(font['source'], font['sha256']) for font in layout['fonts']]
    assets.extend((item['path'], item['sha256']) for item in layout.get('inputs', []))
    if layout.get('builder'):
        assets.append((layout['builder']['path'], layout['builder']['sha256']))
    for path, expected in assets:
        if wf.digest(wf.resolve(sp.parent, path)) != expected:
            raise ValueError(f'Verification dependency fingerprint changed: {path}')
    key = wf.canonical({
        'output': state['output']['sha256'], 'source': state['source']['sha256'],
        'content': pt.content_hash(state, mechanical=True),
        'assignments': wf.digest(verification_assignments(sp, state)),
        'tools': [wf.digest(module.__file__) for module in (pt, wf, ip)],
        'runtime': runtime_packages(),
        'renderer': str(pt.pdfium.PDFIUM_INFO), 'evidence_schema': 'pipeline-v2',
    })
    return sp.parent / ('checks-' + key[:16])


def read_delivery_notes(task):
    """Delivery metadata is independent of PDF construction and page evidence."""
    path = task/'work'/'delivery-notes.json'
    try:
        if not path.resolve().is_relative_to(task.resolve()):
            raise ValueError('Delivery notes must remain inside the task folder')
        if not path.exists():
            return [], []
        items = load(path)
        if not isinstance(items, list):
            raise ValueError('Expected a list of delivery notes')
    except (ValueError, OSError) as exc:
        return [], [{'code':'invalid_delivery_notes','file':str(path),'detail':str(exc)}]
    errors = []
    for i, item in enumerate(items, 1):
        error = {'file':str(path),'entry':i}
        if (not isinstance(item, dict) or not isinstance(item.get('description'), str)
                or not item['description'].strip() or item.get('status') not in ('open','resolved','retained')
                or not isinstance(item.get('note', ''), str)):
            errors.append({**error,'code':'invalid_delivery_note',
                           'detail':'Supply description and status (open, resolved or retained)'})
        elif item['status'] == 'open':
            errors.append({**error,'code':'unresolved_issue','detail':item['description']})
        elif item['status'] == 'retained' and not item.get('note','').strip():
            errors.append({**error,'code':'retained_issue_without_explanation','detail':item['description']})
    return items, errors


def candidate_task(sp, state):
    author = wf.resolve(sp.parent, state['output']['authoring_state']).resolve()
    return next((p.parent for p in author.parents if p.name == 'work' or re.fullmatch(r'recovery(?:-v[0-9]+)?',p.name)),
                author.parent.parent)


def candidate_note_errors(sp, state):
    if state['output'].get('preview'):
        return []
    errors = read_delivery_notes(candidate_task(sp, state))[1]
    for issue in state.get('issues', []):
        if not isinstance(issue, dict) or issue.get('status') not in ('resolved', 'retained'):
            errors.append({'code':'unresolved_issue','detail':issue})
        elif issue['status'] == 'retained' and not issue.get('note'):
            errors.append({'code':'retained_issue_without_explanation','detail':issue})
    return errors


def review_handoff(sp, state, source, output, index, index_path, index_hash, pending, requested, report):
    checkdir = index_path.parent.parent
    by_source = {row['source_page']:row for row in index['pages']}
    assignments = []
    if requested:
        assigned = set()
        for selection in requested:
            scope = set(ip.selected_pages(selection, state['source']['page_count']))
            if scope & assigned or scope - by_source.keys():
                raise ValueError('Review page ranges must be distinct and belong to the candidate: '+selection)
            assigned.update(scope)
            pages = sorted(scope & set(pending))
            if pages:
                assignments.append((min(scope), max(scope), pages))
        if set(pending) - assigned:
            raise ValueError('Review page ranges omit pending source pages: '+ranges(set(pending)-assigned))
    elif pending:
        assignments.append((min(pending), max(pending), pending))

    path = checkdir/'review-handoff.json'
    pages = {p['source_page']:p for p in state['pages']}
    findings = {}
    for finding in report['findings']:
        if finding['code'] in ('right_graphics_changed_outside_recorded_regions','preserved_duplicate_reduced'):
            findings.setdefault(finding.get('page'), []).append(
                {'id':wf.canonical(finding),'code':finding['code'],'detail':finding,'note':''})
    binding = {'output_sha256':index['output_sha256'],'render_index_sha256':index_hash}
    prefix = runtime_prefix(state,sp)
    argv = prefix + [str(wf.resolve(sp.parent,state['layout']['runtime_launcher']).parent/'pipeline.py'),
                     'review','--state',str(sp)] if assignments else []
    handoffs = []
    for first, last, assigned in assignments:
        suffix = f'{first:04d}-{last:04d}'
        template = checkdir/f'observations-template-{suffix}.json'
        destination = checkdir/f'observations-{suffix}.json'
        rows = []
        for n in assigned:
            row = by_source[n]
            checks = ['Source inventory, Chinese readability, formulas/values and table correspondence']
            if any(b['method']=='cover' for b in pages[n]['blocks']):
                checks.append('Every cover: labels, lines, arrows and values')
            rows.append({'page':n,'output_page':row['output_page'],'image':str(index_path.parent/row['image']),
                         'checks':checks,'decision':None,'evidence':'','notes':[],'findings':findings.get(n,[])})
        save(template, {**binding,'reviewer':'','pages':rows})
        handoffs.append({'pages':assigned,'template':str(template),'observations':str(destination)})
        argv.extend(['--observations',str(destination)])

    # Keep the simple one-file result for ordinary reviews.
    template = handoffs[0]['template'] if len(handoffs)==1 else None
    save(path, {'state':str(sp),'source':str(source),'output':str(output),'render_index':str(index_path),
                'command_prefix':prefix,'runner':str(Path(__file__).resolve()),**binding,
                'review_needed':pending,'inventory_review_needed':ranges(p['source_page'] for p in state['pages'] if not p.get('inventory_reviewed')),
                'observations_template':template,'assignments':handoffs,'review_argv':argv})
    return {'review_handoff':str(path),'observations_template':template,'review_argv':argv}


def verify(args):
    sp=Path(args.state).resolve();state=task_state(sp);state_purpose(state,sp,'candidate');source=source_path(state,sp)
    paths = args.previous_state or []
    if isinstance(paths, (str, Path)):
        paths = [paths]
    output=wf.resolve(sp.parent,state['output']['path']).resolve();checkdir=verification_paths(sp,state)
    content_sha = pt.content_hash(state)
    assignments = verification_assignments(sp, state)
    manifest=checkdir/'verification.json';cached=False
    if manifest.exists():
        old=load(manifest)
        cached=all(Path(p).exists() and wf.digest(p)==h for p,h in old.get('files',{}).items()) and bool(old.get('files'))
        if not cached:raise ValueError('Immutable verification evidence changed; investigate instead of overwriting')
    if not cached:
        if state.get('qc', {}).get('content_sha256') != content_sha:
            state['qc'] = {}
        draft=pt.check_state(sp, state=state)
        if not draft['valid']:return {'ok':False,'stage':'state','errors':draft['errors'],'next':'Correct authoring state; no rendering performed.'}
        with tempfile.TemporaryDirectory(prefix='.verify-', dir=sp.parent) as staging:
            staged = Path(staging) / 'checks'
            fonts = wf.check_fonts(sp, assignments, state=state)
            save(staged / 'fonts.json', fonts)
            task = next((p.parent for p in sp.parents if p.name in ('work', 'recovery')), sp.parent)
            report = pt.audit(source, output, state, render_dir=staged / 'renders',
                              cache=task/'work'/'render-cache', workers=worker_count(args))
            save(staged / 'audit.json', report)
            files = {str(checkdir / p.relative_to(staged)): wf.digest(p)
                     for p in staged.rglob('*') if p.is_file()}
            save(staged / manifest.name, {'files': files, 'created_at': now()})
            staged.rename(checkdir)
    report=load(checkdir/'audit.json');index_path=checkdir/'renders'/'index.json';index=load(index_path)
    index_hash = wf.digest(index_path)
    current, _ = wf.checked_page_reviews(state, sp)
    current = {n: record for n, record in current.items()
               if record['render_index']['sha256'] == index_hash}
    reused = []
    prior_for_page = {}
    claimed = dict(current)
    for path in paths:
        previous_path = Path(path).resolve()
        prior = wf.require_state(load(previous_path))
        records = reuse_reviews(sp, index, index_path, index_hash, previous_path, prior, claimed)
        reused.extend(records)
        claimed.update({r['page']: r for r in records})
        prior_for_page.update({r['page']: prior.get('qc', {}) for r in records})
        # Transfer inventory acknowledgement only from the same state that supplied
        # an eligible review; a later source cannot override an already claimed page.
        prior_pages = {p['source_page']: p for p in prior['pages']}
        current_pages = {p['source_page']: p for p in state['pages']}
        for record in records:
            old_page = prior_pages[record['page']]
            page = current_pages[record['page']]
            if old_page.get('inventory_reviewed') is True and not page.get('inventory_reviewed'):
                page['inventory_reviewed'] = True
                if old_page.get('visual_text_review') == 'reviewed':
                    page['visual_text_review'] = 'reviewed'
        del prior
    records = sorted([*current.values(), *reused], key=lambda record: record['page'])
    current_findings = {wf.canonical(f) for f in report['findings'] if f.get('page') in current}
    old_qc=state.get('qc',{})
    state['qc']={'content_sha256':pt.content_hash(state),'source_sha256':state['source']['sha256'],
                 'output_sha256':state['output']['sha256'],'audit_path':ref(checkdir/'audit.json',sp.parent),
                 'font_assignments':ref(assignments,sp.parent),
                 'font_report':{'path':ref(checkdir/'fonts.json',sp.parent),'sha256':wf.digest(checkdir/'fonts.json')},
                 'page_reviews':records,
                  'repair_requests':old_qc.get('repair_requests',[]),
                 'audit_dispositions':[d for d in old_qc.get('audit_dispositions',[])
                                       if d['finding_sha256'] in current_findings],
                 'retained_notes':[note for note in old_qc.get('retained_notes',[])
                                   if note.get('page') in current]}
    if reused:
        reused_pages = {record['page'] for record in reused}
        eligible = {wf.canonical(f): f['page'] for f in report['findings'] if f.get('page') in reused_pages}
        for n, prior_qc in prior_for_page.items():
            state['qc']['audit_dispositions'].extend(
                copy.deepcopy(d) for d in prior_qc.get('audit_dispositions', [])
                if eligible.get(d['finding_sha256']) == n)
            state['qc']['retained_notes'].extend(
                copy.deepcopy(note) for note in prior_qc.get('retained_notes', [])
                if note.get('page') == n)
    if 'review_scope' in old_qc and records:
        state['qc']['review_scope'] = old_qc['review_scope']
    if records:
        review_pages = [r['page'] for r in records]
        latest = max(records, key=lambda r: r['reviewed_at'])
        state['qc'].update(translation_pages=review_pages, visual_pages=review_pages,
                           reviewer=old_qc.get('reviewer', latest['reviewer']) if current else latest['reviewer'],
                           reviewed_at=old_qc.get('reviewed_at', latest['reviewed_at']) if current else latest['reviewed_at'],
                           structure='passed' if wf.audit_accepted(report, state) else 'pending',
                           structure_notes=old_qc.get('structure_notes')
                           or next((qc['structure_notes'] for qc in prior_for_page.values() if qc.get('structure_notes')), None))
    state_written_bytes = 0
    if state['qc'] != old_qc:
        save(sp, state)
        state_written_bytes = sp.stat().st_size
    fonts=load(checkdir/'fonts.json')
    hard=[f for f in report['findings'] if f['severity']=='error' and not
          (state['layout']['review_profile']=='practical' and f['code'] in ('right_graphics_changed_outside_recorded_regions','preserved_duplicate_reduced'))]
    pending = pages_needing_review(state, report, index, {r['page']: r for r in records})
    note_errors = candidate_note_errors(sp, state)
    handoff = {} if hard or not fonts['mechanical_pass'] else review_handoff(
        sp, state, source, output, index, index_path, index_hash, pending,
        getattr(args,'review_pages',None), report)
    return {**handoff,
            'ok':not hard and fonts['mechanical_pass'] and not note_errors,
            'publication_blockers':note_errors,'state':str(sp),'cached':cached,'profile':state['layout']['review_profile'],
            'blocking_findings':hard,'font_pass':fonts['mechanical_pass'],
            'cover_review_needed':[{'page':p['source_page'],'blocks':[b['id'] for b in p['blocks'] if b['method']=='cover']} for p in state['pages'] if p['source_page'] in pending and any(b['method']=='cover' for b in p['blocks'])],
            'finding_counts':counts(report['findings']),'audit':str(checkdir/'audit.json'),
            'output':str(output), 'output_sha256':index['output_sha256'],
            'render_index':str(index_path), 'render_index_sha256':index_hash,
            'reused_pages':[r['page'] for r in records if r['mode']=='reused'],
            'review_needed':pending,
            'inventory_review_needed':ranges(p['source_page'] for p in state['pages'] if not p.get('inventory_reviewed')),
            'rendered_pages':0 if cached else report.get('rendered_pages', len(index['pages'])),
            'source_rendered_pages':0 if cached else report.get('source_rendered_pages', len(index['pages'])),
            'mechanical_reused_pages':len(index['pages']) if cached else report.get('mechanical_reused_pages', 0),
            'render_workers':report['workers'], 'resources':report['resources'],
            'state_written_bytes':state_written_bytes,
            'next':('Resolve the listed mechanical blockers before delivery.' if hard or not fonts['mechanical_pass'] else
                    'Open the listed pages and submit actual observations via review.' if pending else
                    'Resolve delivery notes and verify the same candidate again.' if note_errors else
                    'Use a complete candidate for delivery.' if state['output'].get('preview') else
                    'Candidate checks and page observations are complete; publish checks final readiness.')}


def observation_error(path, message, page=None, *, code='invalid_observation'):
    return ValueError(json.dumps({'code':code,'file':str(path),'page':page,'detail':message},ensure_ascii=False))


def observation_batch(paths, index, index_hash, checkdir):
    if isinstance(paths, (str, Path)):
        paths = [paths]
    rows = {row['source_page']:row for row in index['pages']}
    claimed, batch, structure_notes = {}, [], []
    for path in paths:
        try:
            data = load(path)
        except (OSError, ValueError) as exc:
            raise observation_error(path, str(exc)) from exc
        if not isinstance(data,dict):
            raise observation_error(path, 'Expected an observations object')
        reviewer = data.get('reviewer')
        if not isinstance(reviewer,str) or not reviewer.strip():
            raise observation_error(path, 'Actual reviewer required')
        if any(k not in data for k in ('output_sha256','render_index_sha256')):
            raise observation_error(path, 'Observation file must include both generated fingerprints',
                                    code='observation_fields_missing')
        if (data.get('output_sha256') != index['output_sha256']
                or data.get('render_index_sha256') != index_hash):
            raise observation_error(path, 'Observation fingerprints do not match this candidate and render index',
                                    code='observation_fingerprint_mismatch')
        if data.get('structure_notes'):
            structure_notes.append(str(data['structure_notes']))
        observations = data.get('pages')
        if not isinstance(observations,list) or not observations:
            raise observation_error(path, 'Supply at least one viewed page')
        observation_path = Path(path).resolve()
        assigned = None
        if observation_path.parent == checkdir and re.fullmatch(r'observations-[0-9]+-[0-9]+\.json', observation_path.name):
            template_path = checkdir/observation_path.name.replace('observations-', 'observations-template-', 1)
            if not template_path.is_file():
                raise observation_error(path, 'No generated template for this assigned file')
            template = load(template_path)
            if template.get('output_sha256') != index['output_sha256'] or template.get('render_index_sha256') != index_hash:
                raise observation_error(path, 'Assigned template belongs to another candidate')
            assigned = {row['page'] for row in template['pages']}
        for observation in observations:
            n = observation.get('page') if isinstance(observation,dict) else None
            if type(n) is not int or n not in rows:
                raise observation_error(path, 'Observations must address a physical source page in the candidate', n)
            if n in claimed:
                raise observation_error(path, 'Duplicate observation page, also in '+str(claimed[n]), n)
            if assigned is not None and n not in assigned:
                raise observation_error(path, 'Page is outside this reviewer file assignment', n)
            if 'output_page' in observation:
                target = observation['output_page']
                if type(target) is not int or rows[n]['output_page'] != target:
                    raise observation_error(path, 'Candidate page does not match this physical source page', n)
            claimed[n] = path
            batch.append((path, reviewer.strip(), observation))
    return batch, structure_notes


def review(args):
    sp=Path(args.state).resolve();state=task_state(sp);state_purpose(state,sp,'candidate')
    # Use the evidence bound by verify, not a path recomputed from today's runner.
    checkdir=wf.resolve(sp.parent,state['qc']['audit_path']).resolve().parent
    index_path = checkdir/'renders'/'index.json'
    index_hash = wf.digest(index_path)
    output = wf.resolve(sp.parent, state['output']['path'])
    if wf.digest(output) != state['output']['sha256']:
        raise ValueError('Candidate fingerprint changed')
    manifest = load(checkdir/'verification.json')
    if manifest['files'].get(str(index_path)) != index_hash:
        raise ValueError('Bound render index changed after verify')
    index = load(index_path)
    if (index['output_sha256'] != state['output']['sha256']
            or index['source_sha256'] != state['source']['sha256']
            or any(row['page_content_sha256'] != wf.page_fingerprint(state, row['source_page'])
                   for row in index['pages'])):
        raise ValueError('Review evidence belongs to another source, output or state')
    audit_path = checkdir / 'audit.json'
    if manifest['files'].get(str(audit_path)) != wf.digest(audit_path):
        raise ValueError('Bound audit changed after verify')
    audit=load(audit_path);qc=state['qc']
    batch, structure_notes = observation_batch(args.observations, index, index_hash, checkdir)
    page_numbers = {row['page'] for _, _, row in batch}
    records, _ = wf.checked_page_reviews(state, sp)
    rows = {row['source_page']:row for row in index['pages']}
    pages = {p['source_page']:p for p in state['pages']}
    dispositions={d['finding_sha256']:d for d in qc.get('audit_dispositions',[])}
    repairs={r['page']:r for r in qc.get('repair_requests',[]) if r.get('output_sha256')==state['output']['sha256']}
    notes=[n for n in qc.get('retained_notes',[]) if n.get('page') not in page_numbers]
    for path, reviewer, observation in batch:
        n=observation['page'];evidence=observation.get('evidence')
        if not isinstance(evidence,str) or not evidence.strip():
            raise observation_error(path, 'Actual image-view event or observation reference required', n)
        decision=observation.get('decision')
        if decision not in ('pass','repair'):
            raise observation_error(path, 'Each viewed page requires decision pass/repair', n)
        if any(k in observation for k in ('blocking','inventory_reviewed','covers_checked','retain_right_difference','retained')):
            raise observation_error(path, 'Use the generated decision/findings/notes template', n)
        supplied_notes = observation.get('notes',[])
        if not isinstance(supplied_notes,list) or any(not isinstance(v,str) or not v.strip() for v in supplied_notes):
            raise observation_error(path, 'Notes must be a list of non-empty text entries', n)
        current={wf.canonical(f):f for f in audit['findings'] if f.get('page')==n}
        for key in current:dispositions.pop(key,None)
        if decision=='repair':
            if not supplied_notes:
                raise observation_error(path, 'Repair requires a note identifying the location and reason', n)
            records.pop(n,None)
            repairs[n]={'page':n,'reviewer':reviewer,'reviewed_at':observation.get('viewed_at') or now(),
                        'evidence':evidence,'notes':supplied_notes,'output_sha256':state['output']['sha256']}
            continue
        expected={key for key,f in current.items() if f['code'] in ('right_graphics_changed_outside_recorded_regions','preserved_duplicate_reduced')}
        submitted=observation.get('findings',[])
        if (not isinstance(submitted,list) or any(not isinstance(v,dict) or not isinstance(v.get('id'),str)
                or not isinstance(v.get('note'),str) or not v['note'].strip() for v in submitted)
                or len(submitted)!=len(expected) or {v['id'] for v in submitted}!=expected):
            raise observation_error(path, 'Explain each current retainable finding in the generated template', n)
        if expected and state['layout']['review_profile']=='strict':
            raise observation_error(path, 'Strict mode cannot retain mechanical differences', n)
        for value in submitted:dispositions[value['id']]={'finding_sha256':value['id'],'decision':'retain','note':value['note']}
        page=pages[n]
        covers=[b['id'] for b in page['blocks'] if b['method']=='cover']
        page.update(inventory_reviewed=True, visual_text_review='reviewed')
        row=rows[n]
        records[n]={'page':n,'mode':'viewed','output_sha256':index['output_sha256'],
                    'render_index':{'path':ref(index_path,sp.parent),'sha256':index_hash},
                    'settings_sha256':index['settings_sha256'],
                    **{k:row[k] for k in ('image_sha256','pixel_sha256','page_content_sha256')},
                    'reviewer':reviewer,'reviewed_at':observation.get('viewed_at') or now(),'evidence':evidence,'covers_checked':covers}
        repairs.pop(n,None)
        for note in supplied_notes:notes.append({'page':n,'note':note})
    qc.update(page_reviews=sorted(records.values(),key=lambda r:r['page']),audit_dispositions=list(dispositions.values()),
              repair_requests=list(repairs.values()),retained_notes=notes,
              translation_pages=sorted(records),visual_pages=sorted(records),
              reviewer=', '.join(sorted({viewer for _,viewer,_ in batch})),reviewed_at=now(),
              structure_notes='\n'.join(structure_notes) or 'Basic page readability reviewed; diagnostic warnings retained in the audit. See retained notes and explicit difference dispositions.',
              review_scope='basic-readability' if state['layout']['review_profile']=='practical' else 'strict')
    qc['structure']='passed' if wf.audit_accepted(audit,state) else 'pending'
    saved_pages = sorted(page_numbers)
    # Check the newly submitted evidence before committing any page records.
    submitted_state = {**state, 'qc': {'page_reviews': [records[n] for n in saved_pages if n in records]}}
    _, errors = wf.checked_page_reviews(submitted_state, sp)
    if errors:
        raise ValueError(json.dumps(errors, ensure_ascii=False))
    qc['content_sha256'] = pt.content_hash(state)
    pending = pages_needing_review(state, audit, index, records)
    missing_inventory = ranges(p['source_page'] for p in state['pages'] if not p.get('inventory_reviewed'))
    if pending or missing_inventory:
        # An unfinished handoff can be recorded without scanning the whole book.
        errors = []
        if pending:
            errors.append({'code': 'incomplete_page_review_evidence', 'pages': ranges(pending)})
        if missing_inventory:
            errors.append({'code': 'inventory_not_reviewed', 'pages': missing_inventory})
        result = {'ready_for_delivery': False, 'errors': errors}
    else:
        result = pt.check_state(sp, True, state=state)
    note_errors = candidate_note_errors(sp, state)
    if note_errors:
        result['ready_for_delivery'] = False
        result['errors'].extend(note_errors)
    save(sp, state)
    save(checkdir / 'final-check.json', result)
    save(checkdir/'review-summary.json',{'passed':sorted(records),'repair':list(repairs.values()),'retained':notes})
    return {'state':str(sp),'observations_saved':True,'saved_pages':saved_pages,
             'repair_pages':sorted(repairs),
            'state_written_bytes':sp.stat().st_size,'reviewed_pages':sorted(records),'review_needed':pending,'inventory_review_needed':missing_inventory,
             'ready':result['ready_for_delivery'],'errors':result['errors'],'publication_blockers':note_errors,
             'next':('Publish accepted sample/full PDF.' if result['ready_for_delivery'] else
                    'Resolve delivery notes and verify the same candidate again.' if note_errors and not pending and not missing_inventory else
                    'Observations saved; final delivery is not ready. Review remaining pages or rebuild full selection, then verify --previous-state '+str(sp)+' to reuse eligible evidence. Do not repeat saved page viewing without a changed dependency.')}


def publication_paths(sp, task_dir=None):
    """Keep publication metadata and optional rebuilding within the task."""
    if task_dir:
        root=Path(task_dir).resolve()
    elif sp.parent.name=='work' or re.fullmatch(r'recovery(?:-v[0-9]+)?',sp.parent.name):
        root=sp.parent.parent.resolve()
    else:
        raise ValueError('Cannot infer working folder; publish requires --task-dir for this state location')
    if not sp.is_relative_to(root):
        raise ValueError('Publication state must remain inside --task-dir')
    note=(root/'交付说明.md').resolve()
    rebuild=(root/'work'/'rebuild'/'accepted.rebuilt.pdf').resolve()
    record=(sp.parent/'publication.json').resolve()
    ancestor=rebuild.parent
    while not ancestor.exists():ancestor=ancestor.parent
    if not ancestor.is_dir():raise ValueError('Rebuild parent is not a directory: '+str(ancestor))
    if any(not p.is_relative_to(root) for p in (note,rebuild,record)):
        raise ValueError('Publication support files must remain inside the working folder')
    return root,note,rebuild,record


def preflight_publication(targets,overwrite):
    """Detect conflicts and unwritable directories before copying any PDF."""
    for path in targets:
        if path.exists() and (not path.is_file() or not overwrite):
            raise ValueError('Publication target exists; choose another path or explicit --overwrite: '+str(path))
        ancestor=path.parent
        while not ancestor.exists():ancestor=ancestor.parent
        if not ancestor.is_dir():raise ValueError('Publication parent is not a directory: '+str(ancestor))
        if path.exists() and not os.access(path,os.W_OK):
            raise ValueError('Publication target is not writable: '+str(path))
    for parent in {p.parent for p in targets}:
        parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryFile(dir=parent):pass


def publish(args):
    sp=Path(args.state).resolve();state=task_state(sp);state_purpose(state,sp,'candidate')
    task_dir,note,rebuild,record=publication_paths(sp,getattr(args,'task_dir',None))
    # Resolve against the original task even when the coordinator selects a different publication folder.
    input_task = candidate_task(sp, state)
    delivery_notes, note_errors = read_delivery_notes(input_task)
    if note_errors:
        raise ValueError(json.dumps({'code':'delivery_notes_block_publication','findings':note_errors},ensure_ascii=False))
    result=pt.check_state(sp,True,state=state)
    if not result['ready_for_delivery']:raise ValueError(json.dumps(result['errors'],ensure_ascii=False))
    destination=Path(args.output).resolve();source=source_path(state,sp)
    candidate=wf.resolve(sp.parent,state['output']['path']).resolve()
    recovery_state=record.with_name('accepted.author.json')
    notes_input = (input_task/'work'/'delivery-notes.json').resolve()
    if destination in (source,sp,note,record,rebuild,recovery_state,notes_input):raise ValueError('Publication must not overwrite source, state or support paths')
    if len({source,sp,note,record,rebuild})!=5:raise ValueError('Publication support paths collide with an input')
    audit_path = wf.resolve(sp.parent, state['qc']['audit_path']).resolve()
    manifest = load(audit_path.parent / 'verification.json')
    if manifest['files'].get(str(audit_path)) != wf.digest(audit_path):
        raise ValueError('Bound audit changed after verify')
    report = load(audit_path)
    runner=wf.resolve(sp.parent,state['layout']['builder']['path']).resolve().with_name('pipeline.py')
    recovery_prefix = probe_runtime(state, sp)
    preflight_publication([note,record,recovery_state]+([destination] if destination!=candidate else []),args.overwrite)
    # Recover the accepted decisions, not a later revision of the live author file.
    author=copy.deepcopy(state)
    author.pop('output',None);author['qc']={}
    author.pop('imported_packages',None)
    author['pages']=[{**{k:p[k] for k in ('source_page','output_page','source_rect','geometry','glyphs','source_separators')},
                     **page_authoring(p),'inventory_reviewed':False,'visual_text_review':'pending'} for p in author['pages']]
    relocate_state(author,sp.parent,recovery_state.parent)
    save(recovery_state,author)
    if destination!=candidate:shutil.copyfile(candidate,destination)
    if wf.digest(destination)!=state['output']['sha256']:raise ValueError('Publication fingerprint changed')
    state['output']['path']=ref(destination,sp.parent);save(sp,state)
    final=result
    scope=state['document'].get('delivery_scope','full')
    lines=['# 双语 PDF 交付说明','',f'- 模式：{state["layout"]["review_profile"]}。范围：{scope}。',
           f'- 原文：{source}',f'- 成品：{destination}',f'- 状态：{sp}',
           f'- 原文 SHA-256：{state["source"]["sha256"]}',
           f'- 成品 SHA-256：{state["output"]["sha256"]}',
           f'- 源页：{[p["source_page"] for p in state["pages"]]}',
           f'- 原文 {report["source"]["bytes"]} bytes；输出 {report["output"]["bytes"]} bytes；增长 {report["size_delta_bytes"]} bytes（{100*report["size_delta_bytes"]/max(1,report["source"]["bytes"]):.2f}%）。',
           '- 样本体积与完整源文件比较。' if scope=='sample' else '',
           '- 资源增量：'+json.dumps(report['classified_delta_bytes'],ensure_ascii=False),
           '- 原始审计通过：'+str(report['mechanical_pass'])+'；阅读验收通过：'+str(wf.audit_accepted(report,state)),
           '', '## 保留事项']
    lines += ['- '+str(x) for x in state['qc'].get('retained_notes',[])]
    lines += ['- '+str(x) for x in state.get('issues',[])]
    for item in delivery_notes:
        explanation = item.get('note','').strip()
        lines.append('- '+item['description'].strip()+('：'+explanation if explanation else ''))
    for item in state['layout'].get('null_bookmarks', []):
        lines.append(f'- 原书签目标为空，保留标题 {item["title"]}')
    for p in state['pages']:
        if p.get('null_links'):
            lines.append(f'- 源页 {p["source_page"]} 有 {len(p["null_links"])} 条空目标链接，保留外观。')
        for x in p.get('omitted_links',[]):lines.append(f'- 源页 {p["source_page"]}：'+x['reason'])
    recovery_argv=recovery_prefix+[str(runner),'build','--state',str(recovery_state),'--output',str(rebuild)]
    lines += ['', '## 恢复','需要重建时，使用冻结入口、发布时保存的作者快照和所引用的源文件、字体及依赖。',
              '将以下参数数组传给子进程 API，或逐项引用为命令行参数。',
              '```json',json.dumps(recovery_argv,ensure_ascii=False),'```',
              '重建 PDF 及配套 JSON 写入工作目录 work/rebuild/；已有同名文件时请在该目录另选输出名。',
              '已核对恢复所需的源文件、字形、字体、构建器及输入指纹。',
              '请保留工作目录；删除它会丢失可编辑状态和审核证据。']
    note.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    save(record,{'source':str(source),'output':str(destination),'state':str(sp),'output_sha256':state['output']['sha256'],'check':final,'notes':str(note),'task_dir':str(task_dir),'recovery_argv':recovery_argv,'recovery_state_sha256':wf.digest(recovery_state)})
    return {'output':str(destination),'notes':str(note),'state':str(sp),'ready':True,'scope':scope,'task_dir':str(task_dir),'recovery_argv':recovery_argv,
            'state_written_bytes':sp.stat().st_size}


def inspect_state(args):
    """Read bounded state details in this short-lived Python process."""
    if args.detail != 'summary' and args.pages in (None, 'all'):
        raise ValueError('Block/group/glyph inspection requires explicit --pages')
    if args.detail == 'glyphs' and not args.block:
        raise ValueError('Glyph inspection requires --block')
    if not 1 <= args.limit <= 200 or args.offset < 0:
        raise ValueError('Inspection limit must be 1..200 and offset nonnegative')
    state = task_state(Path(args.state).resolve())
    available = {page['source_page']: page for page in state['pages']}
    selected = sorted(available) if args.pages in (None, 'all') else [
        i+1 for i in pt.parse_pages(args.pages, state['source']['page_count'])]
    if any(n not in available for n in selected):
        raise ValueError('Inspection pages must be present in the state')
    pages = [available[n] for n in selected]
    result = {'state':str(Path(args.state).resolve()), 'source_sha256':state['source']['sha256'],
              'detail':args.detail, 'pages':ranges(selected)}
    if args.detail == 'summary':
        methods = {}
        for page in pages:
            for block in page['blocks']:
                methods[block['method']] = methods.get(block['method'], 0) + 1
        result.update(page_count=len(pages), methods=methods,
                      inventory_pending=ranges(page['source_page'] for page in pages if not page.get('inventory_reviewed')))
        return result
    requested = set(args.block or [])
    blocks = [(page, block) for page in pages for block in page['blocks']
              if not requested or block['id'] in requested]
    missing = requested - {block['id'] for _, block in blocks}
    if missing:
        raise ValueError('Unknown blocks in selected pages: '+', '.join(sorted(missing)))
    items = []
    glyph_maps = {}
    def glyph_map(page):
        number = page['source_page']
        if number not in glyph_maps:
            glyph_maps[number] = {g['id']:g for g in page['glyphs']}
        return glyph_maps[number]
    if args.detail == 'groups':
        items = [{'page':page['page'], **group} for page in grouped_inventory({'pages':pages})['pages']
                 for group in page['groups']
                 if not requested or requested.intersection(group['block_ids'])]
        total_items = len(items)
        items = items[args.offset:args.offset+args.limit]
    elif args.detail == 'blocks':
        keys = ('id','source_text','translation','method','reason','source_bbox','allowed_bbox',
                'cover_bbox','font_size','font_size_min','source_group','glyph_ids')
        total_items = len(blocks)
        for page, block in blocks[args.offset:args.offset+args.limit]:
            item = {'page':page['source_page'], **{k:block[k] for k in keys if k in block}}
            item.pop('glyph_ids', None)
            item['glyph_count'] = len(ip.selected_glyphs(block, glyph_map(page)))
            for key in ('source_text','translation','reason'):
                if isinstance(item.get(key),str) and len(item[key]) > 4000:
                    item[key] = item[key][:4000]
                    item[key+'_truncated'] = True
            items.append(item)
    else:
        for page, block in blocks:
            glyphs = ip.selected_glyphs(block, glyph_map(page))
            for glyph in glyphs:
                items.append({'page':page['source_page'],'block':block['id'], **glyph})
        total_items = len(items)
        items = items[args.offset:args.offset+args.limit]
    result.update(total_items=total_items, offset=args.offset, items=items)
    selected_ids={item['id'] for item in items if 'id' in item}
    if args.detail in ('groups','blocks'):
        result['split_references']=[{'page':p['source_page'],**note} for p in pages
            for note in p.get('split_notes',[]) if selected_ids.intersection(note['restored_ids'])]
    if args.offset+args.limit < total_items:
        result['next_offset'] = args.offset+args.limit
    # A pathological glyph object must not bypass the bounded transport contract.
    if len(json.dumps(result,ensure_ascii=False).encode('utf-8')) > 256*1024:
        raise ValueError('Inspection response too large; use a smaller --limit or inspect individual blocks with --detail blocks --block ID')
    return result


def command_summary(command,args,result):
    """One model-facing summary; detailed checks stay in their existing reports."""
    if command=='inspect':return result
    state_path=Path(result.get('state',args.state)).resolve()
    state=task_state(state_path)
    prefix=runtime_prefix(state,state_path)+[str(wf.resolve(state_path.parent,state['layout']['runtime_launcher']).parent/'pipeline.py')]
    actions=[]
    def action(label,argv):actions.append({'action':label,'argv':argv})
    changes=result.get('changed_pages',result.get('pages',[]))
    repair=result.get('repair_pages',[])
    if command in ('prepare','package','refreeze'):
        commands=result['commands']
        if commands.get('source_render_argv'):action('render source for viewing',commands['source_render_argv'])
        action('inspect',commands['inspect_argv'])
        action('apply edits.json',commands['apply_argv'])
        if command=='package':action('coordinator imports completed package',commands['import_argv'])
    elif command in ('apply','import-package'):
        if result.get('preview_argv'):action('preview ready pages',result['preview_argv'])
        repair=sorted(set(result.get('preflight_blocked_pages',[]))|set(result.get('preflight_unchecked_pages',[]))|
                      {r['page'] for r in result.get('unresolved_by_page',[])})
        if repair:
            action('inspect pages needing edits',prefix+['inspect','--state',str(state_path),'--pages',ranges(repair),'--detail','groups'])
        elif result.get('changed_pages'):
            action('build complete selection',prefix+['build','--state',str(state_path)])
    elif command=='build':
        action('verify candidate',prefix+['verify','--state',str(state_path)])
    elif command in ('verify','review'):
        if result.get('review_argv'):
            action('record filled observations',result['review_argv'])
        if repair or result.get('blocking_findings'):
            author=wf.resolve(state_path.parent,state['output']['authoring_state']).resolve()
            action('inspect authoring state for repair',prefix+['inspect','--state',str(author)])
        if result.get('ready') or (command=='verify' and result.get('ok') and not result.get('review_needed') and not state['output'].get('preview')):
            output=source_path(state,state_path)
            target=output.with_name(output.stem+'_双语左右对照翻译.pdf')
            publish_args=prefix+['publish','--state',str(state_path),'--output',str(target)]
            if target.resolve()==wf.resolve(state_path.parent,state['output']['path']).resolve() and target.is_file():
                action('refresh published delivery notes',publish_args+['--overwrite'])
            else:
                action('publish candidate',publish_args)
    elif command=='status':
        repair=sorted(set(result.get('preflight_blocked_pages',[]))|set(result.get('preflight_unchecked_pages',[]))|
                      set(ip.selected_pages(result['translation_pending'],state['source']['page_count']) if result.get('translation_pending') else []))
        if state.get('output'):action('verify selected candidate',prefix+['verify','--state',str(state_path)])
        else:action('inspect authoring state',prefix+['inspect','--state',str(state_path)]+(['--pages',ranges(repair),'--detail','groups'] if repair else []))
    elif command=='publish':
        action('optional recovery rebuild',result['recovery_argv'])
    artifacts={k:result[k] for k in ('state','output','notes','inventory','groups','edits_template','package',
               'review_handoff','observations_template','render_index','preflight','audit','job') if result.get(k)}
    details=result.get('preflight_details') or result.get('audit') or result.get('preflight')
    summary={'ok':bool(result.get('observations_saved')) or (not result.get('errors') and result.get('ok',True)),
            'saved':bool(result.get('state_written_bytes',0) or result.get('observations_saved')),
            'summary':result.get('next','Completed'), 'pages':result.get('saved_pages',changes),'repair_pages':repair,
            'review_pages':result.get('review_needed',[]),'artifacts':artifacts,'actions':actions,'details':details}
    if command=='status':
        summary['progress']={k:result[k] for k in ('translation_pending','built_pages','reviewed_pages','published_pages','packages')}
    reasons=result.get('preview_blocked_by_page') or result.get('preflight_blocked_by_page') or result.get('blocking_findings') or result.get('publication_blockers') or result.get('errors')
    if reasons:summary['reasons']=reasons[:8]
    return summary


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);subs=parser.add_subparsers(dest='command',required=True)
    for name in ('prepare','refreeze','apply','build','verify','review','publish','status','package','import-package','inspect'):
        p=subs.add_parser(name);p.add_argument('--state',required=True)
        if name in ('prepare','build','publish'):p.add_argument('--overwrite',action='store_true')
        if name in ('prepare','build'):
            p.add_argument('--pages',default='all')
        if name=='prepare':
            p.add_argument('--source',required=True);p.add_argument('--profile',choices=('practical','strict'),default='practical')
        if name=='prepare':p.add_argument('--font',action='append')
        if name in ('build','publish'):p.add_argument('--output',required=name=='publish')
        if name=='build':p.add_argument('--garbage',type=int,choices=(2,4),help=argparse.SUPPRESS)
        if name=='apply':
            p.add_argument('--edits',action='append',required=True)
        if name=='import-package':p.add_argument('--package',action='append',required=True,help='Assigned package directory; repeat to import together')
        if name=='status':
            p.add_argument('--pages',default='all')
            p.add_argument('--packages',action='append',help='Assigned package directories containing current authoring state')
            p.add_argument('--candidate',action='append',help='Candidate state snapshots to include in progress')
        if name=='inspect':
            p.add_argument('--pages',default='all')
            p.add_argument('--block',action='append')
            p.add_argument('--detail',choices=('summary','blocks','glyphs','groups'),default='summary')
            p.add_argument('--limit',type=int,default=20)
            p.add_argument('--offset',type=int,default=0)
        if name=='package':
            p.add_argument('--pages',required=True)
            p.add_argument('--out',required=True)
            p.add_argument('--owner',help='Actual subagent identifier for handoff')
        if name=='refreeze':p.add_argument('--out',required=True,help='New recovery directory; old package is untouched')
        if name=='verify':
            p.add_argument('--previous-state',action='append')
            p.add_argument('--review-pages',action='append',help='One reviewer’s physical source pages; repeat for separate handoffs')
        if name in ('prepare', 'verify'):p.add_argument('--workers',type=worker_request,default='auto')
        if name=='review':p.add_argument('--observations',action='append',required=True,help='Filled observations file; repeat to register together')
        if name=='publish':p.add_argument('--task-dir',help='Working folder for delivery notes and optional rebuilding; inferred from work/ or recovery[-vN]/')
    args=parser.parse_args(argv);started=time.monotonic();success=False;result={};diagnostic=None
    try:
        result={'prepare':prepare,'refreeze':refreeze,'apply':apply_edits,'build':build,'verify':verify,'review':review,'publish':publish,'status':status,'package':package,'import-package':import_package,'inspect':inspect_state}[args.command](args)
        success=(result.get('observations_saved',False) if args.command=='review' else not result.get('errors') and result.get('ok',True))
        print(json.dumps(command_summary(args.command,args,result),ensure_ascii=False));return 0 if success else 2
    except Exception as exc:
        detail=str(exc)
        try:detail=json.loads(detail)
        except (ValueError,TypeError):pass
        if args.command in ('status','inspect'):
            print(json.dumps({'ok': False, 'error': detail}, ensure_ascii=False), file=sys.stderr)
            return 2
        directory=(Path(args.out).resolve().parent/'refreeze-diagnostics' if args.command=='refreeze'
                   else Path(args.state).resolve().parent)
        diagnostic=directory/'diagnostics'/('attempt-'+uuid.uuid4().hex+'.json')
        payload={'at':now(), 'command':args.command, 'detail':detail}
        if isinstance(detail,dict):payload['stage']=detail.get('stage')
        save(diagnostic,payload)
        log=directory/'last-error.json';save(log,{**payload,'diagnostic':str(diagnostic)})
        conflicts=(detail.get('layout_conflicts',[])+detail.get('link_conflicts',[])) if isinstance(detail,dict) else []
        affected = {x['page'] for x in conflicts}
        if isinstance(detail, dict):
            nested = detail.get('detail')
            if isinstance(nested, dict):
                affected.update(n for n in nested.get('pages',[]) if type(n) is int)
                affected.update(x['page'] for x in nested.get('findings',[]) if 'page' in x)
            affected.update(x['page'] for x in detail.get('findings', []) if 'page' in x)
            for item in detail.get('edit_errors',[]):
                if type(item.get('page')) is int:affected.add(item['page'])
                affected.update(x['page'] for x in item.get('validation_errors',[]) if type(x.get('page')) is int)
        if isinstance(detail,dict) and type(detail.get('page')) is int:
            affected.add(detail['page'])
        summary={'ok':False,'command':args.command,'report':str(log),'affected_pages':sorted(affected)}
        summary['error']=str(exc)[:1200] if not conflicts else 'Batch build conflicts: '+str(len(conflicts))
        if isinstance(detail,dict) and detail.get('code')=='invalid_edit_batch':
            summary['error']='Batch edit errors: '+str(len(detail['edit_errors']))
        if isinstance(detail,dict) and detail.get('action_argv'):
            summary['actions']=[{'action':'inspect correct state purpose','argv':detail['action_argv']}]
        message=json.dumps(summary,ensure_ascii=False)
        print(message);print(message,file=sys.stderr)
        return 2
    finally:
        event={'at':now(),'command':args.command,'seconds':round(time.monotonic()-started,3),'success':success,
               'state':str(Path(args.state).resolve()),'pages':getattr(args,'pages',None)}
        if diagnostic:event['diagnostic']=str(diagnostic)
        if args.command not in ('status','inspect'):
            event.update({k: result[k] for k in ('rendered_pages', 'source_rendered_pages', 'mechanical_reused_pages',
                                                 'state_written_bytes', 'cached', 'job', 'resources') if k in result})
            for k in ('render_workers', 'extract_workers'):
                if k in result:
                    event[k] = result[k]
            if 'reused_pages' in result:
                event['reused_pages'] = len(result['reused_pages'])
            if args.command in ('verify','review') and 'review_needed' in result:
                event['review_needed_pages'] = len(result['review_needed'])
            directory=(Path(args.out).resolve() if success else Path(args.out).resolve().parent/'refreeze-diagnostics') if args.command=='refreeze' else Path(args.state).resolve().parent
            p = directory / 'pipeline-events.jsonl'
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + '\n')

if __name__=='__main__':raise SystemExit(main())
