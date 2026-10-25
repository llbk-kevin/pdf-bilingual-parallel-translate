#!/usr/bin/env python3
"""Small state-driven runner: prepare, apply, build, verify, review, publish."""
from __future__ import annotations
import argparse
import copy
import datetime
import json
import math
import os
import shutil
import sys
import time
from pathlib import Path
import inplace as ip
import pdf_tools as pt
import workflow as wf


def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(path,value):ip.write_json(path,value)
def load(path):return wf.load(path)
def source_path(state,path):return wf.resolve(Path(path).parent,state['source']['path']).resolve()
def ref(path,base):return ip.relative(path,base)
def compact_inventory(state):
    keys=('id','source_group','source_line','source_text','source_bbox','method','translation','font_size','rotation','hidden_ocr')
    return {'pages':[{'page':p['source_page'],'width':p['geometry']['width'],'height':p['geometry']['height'],
                     'blocks':[{k:b[k] for k in keys if k in b} for b in p['blocks']]} for p in state['pages']]}


def prepare(args):
    sp=Path(args.state).resolve()
    result=ip.extract(args.source,sp,args.pages,args.overwrite)
    state=load(sp);state['layout']['review_profile']=args.profile or 'practical'
    selected=result['pages']
    state['document'].update(delivery_scope='full' if len(selected)==state['source']['page_count'] else 'sample',
                             selected_source_pages=selected)
    # Freeze a runnable recovery package. Use this copy for subsequent commands.
    here=Path(__file__).parent
    for name in ('pipeline.py','inplace.py','pdf_tools.py','workflow.py'):
        dst=sp.parent/name
        if dst.resolve()!=(here/name).resolve():shutil.copy2(here/name,dst)
    req=here.parent/'requirements.txt'
    if req.exists() and req.resolve()!=(sp.parent/'requirements.txt').resolve():shutil.copy2(req,sp.parent/'requirements.txt')
    for i,value in enumerate(args.font or []):
        p=Path(value).resolve()
        state['layout']['fonts'].append({'name':'Body' if i==0 else 'Fallback'+str(i),'source':ref(p,sp.parent),
                                        'sha256':wf.digest(p),'purpose':'User-selected translation font'})
    risks=[]
    with ip.open_source(args.source) as doc:
        for page in state['pages']:
            n=page['source_page'];pdf_page=doc[n-1]
            if not page['glyphs']:risks.append({'page':n,'code':'image_or_outline_page','action':'Inspect source image; add local covers without hiding artwork'})
            math_blocks=[b for b in page['blocks'] if sum(c in '=±∑√∫≤≥×÷' for c in b['source_text'])>=2]
            if len(math_blocks)>=2:
                risks.append({'page':n,'code':'formula_dense_region_hint','heuristic':True,
                              'blocks':[{'id':b['id'],'bbox':b['source_bbox']} for b in math_blocks],
                              'action':'Prefer preserving original notation; this cue does not require exhaustive formula review'})
            for b in page['blocks']:
                text=b['source_text']
                if any(ord(c)<32 and c not in '\n\r\t' for c in text):
                    risks.append({'page':n,'block':b['id'],'code':'unreliable_text_encoding','action':'Read source crop; preserve formula/identifier instead of guessing'})
                if b.get('hidden_ocr'):risks.append({'page':n,'block':b['id'],'code':'hidden_ocr','action':'Cover visible scan only after checking local bounds'})
            try:ip.check_interactions(doc,[n],state)
            except (ValueError,KeyError,TypeError) as exc:risks.append({'page':n,'code':'interaction_preflight','detail':str(exc)})
    save(sp,state);save(sp.parent/'inventory.json',compact_inventory(state));save(sp.parent/'preflight.json',{'risks':risks})
    return {'state':str(sp),'runner':str(sp.parent/'pipeline.py'),'inventory':str(sp.parent/'inventory.json'),
            'preflight':str(sp.parent/'preflight.json'),'pages':selected,'profile':state['layout']['review_profile'],
            'risk_counts':counts(risks),'next':'Translate coherent groups using apply --edits; inspect source scans before adding covers.'}


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


def apply_edits(args):
    sp=Path(args.state).resolve();state=load(sp);changes=load(args.edits)
    top_keys={'blocks','inventory_reviewed_pages','context_pages','link_overrides','link_overrides_patch','glossary','issues','source_render_index'}
    if not isinstance(changes,dict) or not changes or set(changes)-top_keys:
        raise ValueError('Edit JSON must be a nonempty object using blocks, inventory_reviewed_pages, context_pages, link_overrides, link_overrides_patch, glossary or issues; unknown top-level keys are not accepted')
    changes=pixel_edits(changes,state,sp,args.edits)
    allowed={'translation','method','reason','font_size','font_size_min','font_size_step','leading','allowed_bbox',
             'cover_bbox','cover_fill','cover_text_color','expansion_reason','kind','figure_id','rotation','font','color','source_text','source_bbox','table'}
    pages={p['source_page']:p for p in state['pages']}
    changed=set()
    for edit in changes.get('blocks',[]):
        n=edit.get('page');page=pages.get(n)
        if page is None:raise ValueError('Edit must specify an inventoried source page')
        bid=edit['id'];existing=next((b for b in page['blocks'] if b['id']==bid),None)
        merge=edit.get('merge_ids')
        if merge:
            parts=[next((b for b in page['blocks'] if b['id']==x),None) for x in merge]
            if any(b is None for b in parts) or len(set(merge))!=len(merge):raise ValueError('Invalid merge_ids')
            if existing is not None and bid not in merge:raise ValueError('Merged ID collides with another block')
            pos=min(page['blocks'].index(b) for b in parts)
            existing=copy.deepcopy(parts[0]);existing['id']=bid
            existing['glyph_ids']=[g for b in parts for g in b['glyph_ids']]
            existing['glyph_ranges']=[[0,len(existing['glyph_ids'])]]
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
    for n in changes.get('inventory_reviewed_pages',[]):
        pages[n]['inventory_reviewed']=True;pages[n]['visual_text_review']='reviewed';changed.add(n)
    for n,values in changes.get('context_pages',{}).items():
        pages[int(n)]['context_pages']=values;pages[int(n)]['context_reviewed']=True
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
    if 'issues' in changes:state['issues']=changes['issues']
    for page in state['pages']:
        page['expected_blocks']=[b['id'] for b in page['blocks']];page['reading_order']=page['expected_blocks'][:]
        if page['blocks']:page['kind']='translated'
    state['qc']={};state.pop('output',None)
    errors=ip.validate_state(state,source_path(state,sp))
    if errors:raise ValueError(json.dumps(errors,ensure_ascii=False))
    save(sp,state);save(sp.parent/'inventory.json',compact_inventory(state))
    preview=[sys.executable,str(Path(__file__).resolve()),'build','--state',str(sp)]
    if changed:preview+=['--pages',','.join(map(str,sorted(changed)))]
    return {'state':str(sp),'changed_pages':sorted(changed),'preview_argv':preview,
            'next':'Use preview_argv for local adjustments; omit --pages for final full selection. After rebuilding, verify --previous-state OLD_ACCEPTED.state.json to retain unchanged reviews.'}


def build(args):
    sp=Path(args.state).resolve();state=load(sp);source=source_path(state,sp)
    if args.source and Path(args.source).resolve()!=source:
        supplied=Path(args.source).resolve()
        raise ValueError(json.dumps({'code':'source_override_mismatch','expected':str(source),
                                    'supplied':str(supplied),'supplied_exists':supplied.is_file(),
                                    'action':'Omit --source to use the frozen authoring source; do not change state or repeat this command unchanged.'},ensure_ascii=False))
    if args.profile and args.profile!=state['layout'].get('review_profile','strict'):raise ValueError('Set profile at prepare; do not silently change an existing task')
    key=wf.canonical({'state':pt.content_hash(state),'source':wf.digest(source),'pages':args.pages,
                      'builder':wf.digest(Path(ip.__file__)),'helper':wf.digest(Path(wf.__file__))})
    output=Path(args.output).resolve() if args.output else sp.parent.parent/'work'/('candidate-'+key[:16]+'.pdf')
    manifest=output.with_suffix('.build.json')
    if manifest.exists():
        old=load(manifest)
        if (old.get('key')==key and all(Path(p).exists() and wf.digest(p)==h for p,h in old['files'].items())
            and Path(old['result']['state']).exists() and pt.content_hash(load(old['result']['state']))==old.get('state_content')):
            return {**old['result'],'cached':True,'next':'verify --state '+old['result']['state']}
    result=ip.build(source,sp,output,args.pages,args.overwrite)
    save(manifest,{'key':key,'result':result,'state_content':pt.content_hash(load(result['state'])),
                   'files':{result[k]:wf.digest(result[k]) for k in ('output','assignments')}})
    return {**result,'cached':False,'next':'verify --state '+result['state']}


def rebase_record(record,base):
    value=copy.deepcopy(record)
    value['render_index']['path']=str(wf.resolve(base,value['render_index']['path']).resolve())
    if 'previous' in value:value['previous']=rebase_record(value['previous'],base)
    return value


def reuse_reviews(state,sp,index,index_path,previous_path):
    if not previous_path:return []
    previous_path=Path(previous_path).resolve();old=load(previous_path)
    if wf.validate_reviews(old,previous_path):return []
    by_page={r['page']:r for r in old.get('qc',{}).get('page_reviews',[])};records=[]
    for row in index['pages']:
        n=row['source_page'];original=by_page.get(n)
        if not original:continue
        if original.get('mode')=='reused':original=original['previous']
        if (original['settings_sha256']!=index['settings_sha256'] or
            original['pixel_sha256']!=row['pixel_sha256'] or original['page_content_sha256']!=row['page_content_sha256']):continue
        records.append({'page':n,'mode':'reused','output_sha256':index['output_sha256'],
                        'render_index':{'path':ref(index_path,sp.parent),'sha256':wf.digest(index_path)},
                        'settings_sha256':index['settings_sha256'],
                        **{k:row[k] for k in ('image_sha256','pixel_sha256','page_content_sha256')},
                        'reviewer':original['reviewer'],'reviewed_at':original['reviewed_at'],
                        'evidence':original['evidence'],'previous':rebase_record(original,previous_path.parent),
                        'reuse_reason':'Identical pixels, settings and declared page dependencies; original observation retained.'})
    return records


def verification_paths(sp,state):
    key=wf.canonical({'output':state['output']['sha256'],'content':pt.content_hash(state),
                      'auditor':wf.digest(Path(pt.__file__)),'helper':wf.digest(Path(wf.__file__)),'evidence_schema':'pipeline-v1'})
    return sp.parent/('checks-'+key[:16])


def verify(args):
    sp=Path(args.state).resolve();state=load(sp);source=source_path(state,sp)
    output=wf.resolve(sp.parent,state['output']['path']).resolve();checkdir=verification_paths(sp,state)
    manifest=checkdir/'verification.json';cached=False
    if manifest.exists():
        old=load(manifest)
        cached=all(Path(p).exists() and wf.digest(p)==h for p,h in old.get('files',{}).items()) and bool(old.get('files'))
        if not cached:raise ValueError('Immutable verification evidence changed; investigate instead of overwriting')
    if not cached:
        draft=pt.check_state(sp)
        if not draft['valid']:return {'ok':False,'stage':'state','errors':draft['errors'],'next':'Correct authoring state; no rendering performed.'}
        checkdir.mkdir(parents=True,exist_ok=True)
        assignments=output.with_suffix('.font-runs.json')
        fonts=wf.check_fonts(sp,assignments);save(checkdir/'fonts.json',fonts)
        report=pt.audit(source,output,state,render_dir=checkdir/'renders');save(checkdir/'audit.json',report)
        files={str(p):wf.digest(p) for p in checkdir.rglob('*') if p.is_file()}
        save(manifest,{'files':files,'created_at':now()})
    report=load(checkdir/'audit.json');index_path=checkdir/'renders'/'index.json';index=load(index_path)
    records=state.get('qc',{}).get('page_reviews',[])
    if args.previous_state and not records:records=reuse_reviews(state,sp,index,index_path,args.previous_state)
    old_qc=state.get('qc',{})
    state['qc']={'content_sha256':pt.content_hash(state),'source_sha256':state['source']['sha256'],
                 'output_sha256':state['output']['sha256'],'audit_path':ref(checkdir/'audit.json',sp.parent),
                 'font_assignments':ref(output.with_suffix('.font-runs.json'),sp.parent),
                 'font_report':{'path':ref(checkdir/'fonts.json',sp.parent),'sha256':wf.digest(checkdir/'fonts.json')},
                 'page_reviews':records,'audit_dispositions':old_qc.get('audit_dispositions',[]),
                 'retained_notes':old_qc.get('retained_notes',[])}
    if records:
        state['qc'].update({k:old_qc[k] for k in ('translation_pages','visual_pages','reviewer','reviewed_at','structure','structure_notes') if k in old_qc})
    if args.previous_state and records:
        prior=load(args.previous_state);reused={r['page'] for r in records if r.get('mode')=='reused'}
        eligible={wf.canonical(f) for f in report['findings'] if f.get('page') in reused}
        known={d['finding_sha256'] for d in state['qc']['audit_dispositions']}
        for decision in prior.get('qc',{}).get('audit_dispositions',[]):
            h=decision['finding_sha256']
            if h in eligible and h not in known:
                state['qc']['audit_dispositions'].append(copy.deepcopy(decision));known.add(h)
        for note in prior.get('qc',{}).get('retained_notes',[]):
            if note.get('page') in reused and note not in state['qc']['retained_notes']:
                state['qc']['retained_notes'].append(copy.deepcopy(note))
    save(sp,state)
    fonts=load(checkdir/'fonts.json')
    hard=[f for f in report['findings'] if f['severity']=='error' and not
          (state['layout'].get('review_profile')=='practical' and f['code']=='right_graphics_changed_outside_recorded_regions')]
    reviewed={r['page'] for r in records}
    return {'ok':not hard and fonts['mechanical_pass'],'state':str(sp),'cached':cached,'profile':state['layout'].get('review_profile','strict'),
            'blocking_findings':hard,'font_pass':fonts['mechanical_pass'],
            'cover_review_needed':[{'page':p['source_page'],'blocks':[b['id'] for b in p['blocks'] if b['method']=='cover']} for p in state['pages'] if p['source_page'] not in reviewed and any(b['method']=='cover' for b in p['blocks'])],
            'finding_counts':counts(report['findings']),'audit':str(checkdir/'audit.json'),
            'render_index':str(index_path),'review_needed':[r['source_page'] for r in index['pages'] if r['source_page'] not in reviewed],
            'next':'Open listed full-page renders once; zoom only an actual readability concern. Submit observations via review --observations FILE.'}


def review(args):
    sp=Path(args.state).resolve();state=load(sp);observations=load(args.observations)
    reviewer=observations.get('reviewer')
    if not reviewer:raise ValueError('Actual reviewer required')
    # Use the evidence bound by verify, not a path recomputed from today's runner.
    checkdir=wf.resolve(sp.parent,state['qc']['audit_path']).resolve().parent
    index_path=checkdir/'renders'/'index.json';index=load(index_path)
    if index.get('output_sha256')!=state['output']['sha256'] or index.get('source_sha256')!=state['source']['sha256']:
        raise ValueError('Review evidence belongs to another source/output')
    audit=load(checkdir/'audit.json');qc=state['qc'];records={r['page']:r for r in qc.get('page_reviews',[])}
    dispositions={d['finding_sha256']:d for d in qc.get('audit_dispositions',[])}
    for observation in observations['pages']:
        n=observation['page'];evidence=observation.get('evidence','').strip()
        if not evidence:raise ValueError('Actual image-view event or observation reference required')
        if observation.get('blocking'):raise ValueError('Do not record acceptance for a page with blocking problems')
        page=next(p for p in state['pages'] if p['source_page']==n)
        covers=[b['id'] for b in page['blocks'] if b['method']=='cover']
        if covers and observation.get('covers_checked') is not True:
            raise ValueError('Page '+str(n)+' has cover blocks: compare source and output for hidden diagrams/table values, then set covers_checked=true in actual observations')
        row=next(r for r in index['pages'] if r['source_page']==n)
        records[n]={'page':n,'mode':'viewed','output_sha256':index['output_sha256'],
                    'render_index':{'path':ref(index_path,sp.parent),'sha256':wf.digest(index_path)},
                    'settings_sha256':index['settings_sha256'],
                    **{k:row[k] for k in ('image_sha256','pixel_sha256','page_content_sha256')},
                    'reviewer':reviewer,'reviewed_at':observation.get('viewed_at') or now(),'evidence':evidence,'covers_checked':covers}
        note=observation.get('retain_right_difference')
        if note:
            for finding in audit['findings']:
                if finding.get('page')==n and finding['code']=='right_graphics_changed_outside_recorded_regions':
                    h=wf.canonical(finding);dispositions[h]={'finding_sha256':h,'decision':'retain','note':str(note)}
        for note in observation.get('retained',[]):
            item={'page':n,'note':note}
            if item not in qc['retained_notes']:qc['retained_notes'].append(item)
    qc.update(page_reviews=sorted(records.values(),key=lambda r:r['page']),audit_dispositions=list(dispositions.values()),
              translation_pages=sorted(records),visual_pages=sorted(records),reviewer=reviewer,reviewed_at=now(),
              structure_notes=observations.get('structure_notes') or 'Basic page readability reviewed; diagnostic warnings retained in the audit. See retained notes and explicit difference dispositions.',
              review_scope='basic-readability' if state['layout'].get('review_profile')=='practical' else 'strict')
    qc['structure']='passed' if wf.audit_accepted(audit,state) else 'pending'
    save(sp,state);result=pt.check_state(sp,True);save(checkdir/'final-check.json',result)
    saved_pages=sorted(o['page'] for o in observations['pages'])
    return {'state':str(sp),'observations_saved':True,'saved_pages':saved_pages,
            'reviewed_pages':sorted(records),'review_needed':[r['source_page'] for r in index['pages'] if r['source_page'] not in records],
            'ready':result['ready_for_delivery'],'errors':result['errors'],
            'next':('Publish accepted sample/full PDF.' if result['ready_for_delivery'] else
                    'Observations saved; final delivery is not ready. Review remaining pages or rebuild full selection, then verify --previous-state '+str(sp)+' to reuse eligible evidence. Do not repeat saved page viewing without a changed dependency.')}


def publish(args):
    sp=Path(args.state).resolve();state=load(sp);result=pt.check_state(sp,True)
    if not result['ready_for_delivery']:raise ValueError(json.dumps(result['errors'],ensure_ascii=False))
    destination=Path(args.output).resolve();source=source_path(state,sp)
    candidate=wf.resolve(sp.parent,state['output']['path']).resolve()
    if destination in (source,sp):raise ValueError('Publication must not overwrite source or state')
    if destination!=candidate:
        if destination.exists() and not args.overwrite:raise ValueError('Destination exists; choose a new filename or explicit --overwrite')
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(candidate,destination)
    if wf.digest(destination)!=state['output']['sha256']:raise ValueError('Publication fingerprint changed')
    state['output']['path']=ref(destination,sp.parent);save(sp,state)
    final=pt.check_state(sp,True)
    if not final['ready_for_delivery']:raise ValueError('Published state failed final consistency')
    report=load(wf.resolve(sp.parent,state['qc']['audit_path']))
    note=destination.with_suffix('.md');scope=state['document'].get('delivery_scope','full')
    lines=['# 双语 PDF 交付说明','',f'- 模式：{state["layout"].get("review_profile","strict")}；范围：{scope}。',
           f'- 原文：{source}',f'- 成品：{destination}',f'- 状态：{sp}',
           f'- 源页：{[p["source_page"] for p in state["pages"]]}',
           f'- 原文 {report["source"]["bytes"]} bytes；输出 {report["output"]["bytes"]} bytes；增长 {report["size_delta_bytes"]} bytes（{100*report["size_delta_bytes"]/max(1,report["source"]["bytes"]):.2f}%）。',
           '- 样本的原文大小为完整源文件大小，不代表同页资源增长率。' if scope=='sample' else '',
           '- 资源增量：'+json.dumps(report['classified_delta_bytes'],ensure_ascii=False),
           '- 原始审计通过：'+str(report['mechanical_pass'])+'；阅读验收通过：'+str(wf.audit_accepted(report,state)),
           '', '## 保留事项']
    lines += ['- '+str(x) for x in state['qc'].get('retained_notes',[])]
    lines += ['- '+str(x) for x in state.get('issues',[])]
    for p in state['pages']:
        for x in p.get('omitted_links',[]):lines.append(f'- 源页 {p["source_page"]}：'+x['reason'])
    runner=wf.resolve(sp.parent,state['layout']['builder']['path']).resolve().with_name('pipeline.py')
    recovery_argv=[sys.executable,'-X','utf8',str(runner),'build','--state',str(sp),'--output',str(destination.with_name(destination.stem+'.rebuilt.pdf'))]
    lines += ['', '## 恢复','以下参数使用已验收状态及其实际冻结入口，兼容带版本号的恢复目录。',
              '准备相同依赖与状态引用的字体；将参数数组传给子进程 API，或逐项引用为命令行参数：',
              '```json',json.dumps(recovery_argv,ensure_ascii=False),'```',
              '重建写入独立 .rebuilt.pdf，不覆盖已交付文件；已有同名重建文件时请另选输出路径。',
              '已核对恢复所需的源文件、字形、字体、构建器及输入指纹。',
              '请保留工作目录；删除它会丢失可编辑状态和审核证据。']
    note.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    save(sp.parent/'publication.json',{'source':str(source),'output':str(destination),'state':str(sp),'check':final,'recovery_argv':recovery_argv})
    return {'output':str(destination),'notes':str(note),'state':str(sp),'ready':True,'scope':scope,'recovery_argv':recovery_argv}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);subs=parser.add_subparsers(dest='command',required=True)
    for name in ('prepare','apply','build','verify','review','publish'):
        p=subs.add_parser(name);p.add_argument('--state',required=True);p.add_argument('--overwrite',action='store_true')
        if name in ('prepare','build'):
            p.add_argument('--source',required=name=='prepare');p.add_argument('--pages',default='all');p.add_argument('--profile',choices=('practical','strict'))
        if name=='prepare':p.add_argument('--font',action='append')
        if name in ('build','publish'):p.add_argument('--output',required=name=='publish')
        if name=='apply':p.add_argument('--edits',required=True)
        if name=='verify':p.add_argument('--previous-state')
        if name=='review':p.add_argument('--observations',required=True)
    args=parser.parse_args(argv);started=time.monotonic();success=False
    try:
        result={'prepare':prepare,'apply':apply_edits,'build':build,'verify':verify,'review':review,'publish':publish}[args.command](args)
        success=(result.get('observations_saved',False) if args.command=='review' else not result.get('errors') and result.get('ok',True))
        print(json.dumps(result,ensure_ascii=False));return 0 if success else 2
    except Exception as exc:
        detail=str(exc)
        try:detail=json.loads(detail)
        except (ValueError,TypeError):pass
        log=Path(args.state).resolve().parent/'last-error.json';save(log,{'command':args.command,'detail':detail})
        conflicts=(detail.get('layout_conflicts',[])+detail.get('link_conflicts',[])) if isinstance(detail,dict) else []
        summary={'ok':False,'command':args.command,'report':str(log),'affected_pages':sorted({x['page'] for x in conflicts})}
        summary['error']=str(exc)[:1200] if not conflicts else 'Batch build conflicts: '+str(len(conflicts))
        message=json.dumps(summary,ensure_ascii=False)
        print(message);print(message,file=sys.stderr)
        return 2
    finally:
        event={'at':now(),'command':args.command,'seconds':round(time.monotonic()-started,3),'success':success,
               'state':str(Path(args.state).resolve()),'pages':getattr(args,'pages',None)}
        p=Path(args.state).resolve().parent/'pipeline-events.jsonl';p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('a',encoding='utf-8') as f:f.write(json.dumps(event,ensure_ascii=False)+'\n')

if __name__=='__main__':raise SystemExit(main())
