"""Disposable authoring diagnostics. These records never establish visual review."""
from __future__ import annotations
import copy
import datetime
from pathlib import Path
import inplace as ip
import workflow as wf


def summarize(findings):
    groups={}
    for item in findings:
        row=groups.setdefault(item['code'],{'count':0,'pages':set()})
        row['count']+=1
        if item.get('page') is not None:row['pages'].add(item['page'])
    return {k:{**v,'pages':sorted(v['pages'])} for k,v in groups.items()}


def dependency_key(state, sp):
    files=[wf.resolve(sp.parent,state['source']['path'])]
    files += [wf.resolve(sp.parent,f['source']) for f in state['layout']['fonts']]
    files += [wf.resolve(sp.parent,f['path']) for f in state['layout'].get('inputs',[])]
    files += [Path(__file__),Path(ip.__file__),Path(wf.__file__),Path(__file__).with_name('pipeline.py')]
    return wf.canonical([[(str(p.resolve()),wf.digest(p)) for p in files],
        state['layout'],state['glossary'],state['document'].get('final_source_pages',
        state['document'].get('selected_source_pages'))])


def page_key(page):
    value=copy.deepcopy(page)
    for key in ('inventory_reviewed','visual_text_review','build_findings','native_text_normalization'):
        value.pop(key,None)
    for block in value['blocks']:
        for key in ('actual_bbox','target_bbox','actual_glyph_boxes','actual_font_size','layout_lines'):
            block.pop(key,None)
    return wf.canonical(value)


def summary(state, sp, selected=None):
    path=sp.parent/'edit-checks.json'
    try:
        index=wf.load(path);dependency=dependency_key(state,sp)
    except (OSError,ValueError,KeyError,TypeError):
        index={};dependency=None
    if not isinstance(index,dict):index={}
    records=index.get('pages',{}) if index.get('dependencies')==dependency and dependency else {}
    blocked=[];unchecked=[];passed=[];reasons=[]
    for page in state['pages']:
        n=page['source_page']
        if selected is not None and n not in selected:continue
        record=records.get(str(n))
        if (not isinstance(record,dict) or record.get('page_key')!=page_key(page)
                or not isinstance(record.get('findings'),list) or not isinstance(record.get('checks'),dict)
                or set(record['checks'])!={'layout','preserved','links'}):
            unchecked.append(n);continue
        if record['findings']:
            blocked.append(n)
            reasons.append({'page':n,'reasons':sorted({f['code'] for f in record['findings']})})
        if 'unchecked' in record['checks'].values():unchecked.append(n)
        elif not record['findings']:passed.append(n)
    return {'preflight_blocked_pages':blocked,'preflight_unchecked_pages':unchecked,
            'preflight_passed_pages':passed,'preflight_blocked_by_page':reasons,
            'preflight_details':str(path)}


def run(state, sp, changed):
    pages=copy.deepcopy([p for p in state['pages'] if p['source_page'] in changed])
    findings=[];counts={};checks={p['source_page']:{k:'unchecked' for k in ('layout','preserved','links')} for p in pages}
    stage='layout'
    try:
        fonts=ip.load_fonts(state,sp)
        cache,report=ip.layout_preflight(pages,fonts)
        findings.extend(report['findings']);counts=report['counts']
        bad={f['page'] for f in findings}
        for page in pages:checks[page['source_page']]['layout']='failed' if page['source_page'] in bad else 'passed'
        source=wf.resolve(sp.parent,state['source']['path'])
        with ip.open_source(source) as doc:
            stage='preserved'
            for page in pages:
                n=page['source_page']
                try:
                    rows=ip.source_collision_findings(doc[n-1],page,cache)
                    findings.extend(rows);checks[n]['preserved']='failed' if rows else 'passed'
                except (ValueError,RuntimeError) as exc:
                    findings.append({'page':n,'code':'preserved_check_failed','detail':str(exc)})
            ready=[p for p in pages if p['source_page'] not in bad and
                   not any(b['method']=='unresolved' for b in p['blocks'])]
            if ready:
                stage='link'
                reader=ip.interaction_reader(doc,source,None)
                try:
                    scoped={**state,'pages':ready}
                    rows,_=ip.check_right_links(doc,reader,[p['source_page'] for p in ready],scoped)
                    for row in rows:
                        row['code']='link_anchor_unresolved'
                        row['source_text']=doc[row['page']-1].get_textbox(ip.rect(row['source_bbox']))
                    findings.extend(rows)
                    failed={r['page'] for r in rows}
                    for page in ready:checks[page['source_page']]['links']='failed' if page['source_page'] in failed else 'passed'
                finally:
                    if getattr(reader,'stream',None) is not None:reader.stream.close()
    except Exception as exc:
        for page in pages:
            findings.append({'page':page['source_page'],'code':stage+'_check_failed',
                             'error_type':type(exc).__name__,'detail':str(exc)})
    originals={p['source_page']:p for p in state['pages']}
    for finding in findings:
        page=originals.get(finding.get('page'))
        block=next((b for b in page['blocks'] if b['id']==finding.get('block')),None) if page else None
        if block:
            finding.update(source_text=block['source_text'],translation=block.get('translation',''))
        if page and finding.get('source_link') is not None:
            # Link diagnostics from the resolver already contain the source region
            # and candidate IDs; the page's translations keep context bounded.
            finding['candidate_translations']=[{'id':b['id'],'translation':b.get('translation','')}
                for b in page['blocks'] if b['id'] in finding.get('detail','')]
    path=sp.parent/'edit-checks.json'
    try:index=wf.load(path)
    except (OSError,ValueError):index={}
    if not isinstance(index,dict):index={}
    try:dependency=dependency_key(state,sp)
    except (OSError,ValueError):dependency=None
    if index.get('dependencies')!=dependency:index={'dependencies':dependency,'pages':{}}
    index.setdefault('pages',{})
    for page in pages:
        n=page['source_page']
        index['pages'][str(n)]={'page_key':page_key(originals[n]),'checks':checks[n],
            'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'findings':[f for f in findings if f.get('page')==n]}
    ip.write_json(path,index)
    return {'counts':counts,'groups':summarize(findings),'findings':findings},summary(state,sp)


def structure_check(state, changes, apply_one, sp, edit_file, failed_targets):
    """Apply independently valid edits on a disposable state; report the batch."""
    errors=[];changed=set();seen={}
    for offset,edit in enumerate(changes.get('blocks',[])):
        n=edit.get('page');bid=edit.get('id');location={'page':n,'block':bid}
        previous=seen.get((n,bid))
        if previous is not None and not (previous.get('merge_ids') and not edit.get('merge_ids')):
            errors.append({**location,'code':'duplicate_edit_target','edit_file':str(edit_file),'edit_index':offset})
            continue
        seen[n,bid]=edit
        members=edit.get('merge_ids') or [bid]
        dependencies=sorted(x for x in members if (n,x) in failed_targets)
        if dependencies:
            errors.append({**location,'code':'edit_dependency_blocked','depends_on':dependencies,
                           'edit_file':str(edit_file),'edit_index':offset})
            failed_targets.add((n,bid));continue
        # apply_one validates glyph ownership/geometry too. Copy only the page
        # being changed, retaining the original immutable source facts elsewhere.
        trial={**state,'pages':[{**p,'blocks':[dict(b) for b in p['blocks']]} if p['source_page']==n else p for p in state['pages']]}
        touched=set()
        try:
            apply_one(trial,sp,edit_file,touched,location,{'blocks':[edit]},validate=False)
        except (ValueError,KeyError,TypeError,OSError) as exc:
            import json
            try:detail=json.loads(str(exc))
            except ValueError:detail={'detail':str(exc)}
            if isinstance(detail,list):detail={'validation_errors':detail}
            if not isinstance(detail,dict):detail={'detail':detail}
            errors.append({**location,**detail,'edit_file':str(edit_file),'edit_index':offset})
            failed_targets.add((n,bid))
        else:
            state['pages']=trial['pages'];changed.update(touched)
    remainder={k:v for k,v in changes.items() if k!='blocks'}
    if remainder:
        location={}
        try:apply_one(state,sp,edit_file,changed,location,remainder,validate=False)
        except (ValueError,KeyError,TypeError,OSError) as exc:
            errors.append({**location,'edit_file':str(edit_file),'detail':str(exc)})
    return changed,errors
