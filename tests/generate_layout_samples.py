"""Generate small visual fixtures. Supply a licensed local Chinese TrueType font; never commit outputs."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import example_build as builder
import pdf_tools as tools
from workflow import digest, check_fonts
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit


def generate(out, font, face_index=0):
    out, font = Path(out).resolve(), Path(font).resolve()
    out.mkdir(parents=True, exist_ok=True)
    width, height = 420, 560
    numbered = [
        ('Visitor Handbook', '访客手册', 'A short guide to the reading room.', '阅览室使用简明指南。', None),
        ('Opening hours', '开放时间',
         'The reading room opens at 9 a.m. and closes at 6 p.m. on weekdays. Visitors may use the reference collection on site. Please return shared materials before leaving.',
         '阅览室工作日上午 9 点开放，下午 6 点关闭。访客可在室内使用参考资料。离开前请归还共用资料。', 'iv'),
        ('Group visits', '团体参观',
         'Groups of more than six people should book in advance. The booking is confirmed only after staff send a reply. A request alone does not reserve a place.',
         '超过六人的团体应提前预约。只有在工作人员回复后，预约才得到确认。仅提交申请并不意味着已保留名额。', 'A-3')]
    unnumbered = [
        ('Community Space Guide', '公共空间指南', 'Information for first-time visitors.', '首次到访者须知。', None),
        ('Shared spaces', '共用空间',
         'Room A has 12 seats and Room B has 8 seats. Reservations last 45 minutes. Do not leave belongings unattended.',
         'A 室设有 12 个座位，B 室设有 8 个座位。每次预约时长为 45 分钟。请勿将个人物品留在无人照看的地方。', None),
        ('', '', '', '', None)]
    dense_en = ('The walking route starts at the entrance and passes the garden before reaching the reading room. '
                'Visitors should keep to the marked path. The shaded area in Figure 1 is a quiet zone, not a waiting area. '
                'During rain, use the covered route and allow extra time. The short route takes about 12 minutes; '
                'the accessible route takes about 18 minutes. These times are estimates, not guaranteed limits. '
                'Children must remain with an accompanying adult. Do not enter the garden when a closure notice is displayed.')
    dense_zh = ('步行路线从入口开始，经过花园后到达阅览室。访客应沿标记的路径行走。图 1 中的阴影区域是安静区，'
                '不是等候区。下雨时请使用有遮蔽的路线，并预留更多时间。较短路线约需 12 分钟，无障碍路线约需 '
                '18 分钟。这些时间是估计值，并非保证的上限。儿童必须由同行成人陪同。张贴关闭告示时，请勿进入花园。')
    scenarios = [('numbered', numbered, 'preserve-source'), ('unnumbered', unnumbered, 'physical-total'),
                 ('dense', [('Walking route', '步行路线', dense_en, dense_zh.replace('。', '。\n').rstrip(), None)], 'physical-total')]
    results = []
    for name, rows, strategy in scenarios:
        folder = out/name; folder.mkdir(exist_ok=True)
        source = folder/'source.pdf'; state_path=folder/'state.json'
        c = canvas.Canvas(str(source), pagesize=(width,height), invariant=1, pageCompression=1)
        state = {'schema_version':2,'document':{'source_kind':'english-original'},'source':{},
                 'layout':{'body_size_pt':11.5,'pagination_strategy':strategy,
                           'fonts':[{'name':'Chinese','source':str(font),'sha256':digest(font),
                                     'purpose':'Local visual fixture text','face_index':face_index}]},
                 'glossary':[],'issues':[],'qc':{},'pages':[]}
        def block(n, suffix, kind, source_text, translation, sb, tb, **extras):
            return {'id':f'p{n:03d}-{suffix}','kind':kind,'source_text':source_text,'translation':translation,
                    'source_bbox':sb,'target_bbox':tb,'status':'translated',**extras}
        for n,(title,zh_title,body,zh_body,label) in enumerate(rows,1):
            blocks=[]
            if title:
                c.setFont('Helvetica-Bold',17);c.drawString(30,height-55,title)
                blocks.append(block(n,'title','heading',title,zh_title,[30,35,390,60],[450,35,810,65],font_size=17))
                c.setFont('Helvetica',10.5)
                source_lines=simpleSplit(body,'Helvetica',10.5,360)
                for i,line in enumerate(source_lines):c.drawString(30,height-90-15*i,line)
                source_bottom=96+15*(len(source_lines)-1)
                body_box=[450,78,810,max(138,source_bottom+20)]
                extras={}
                if name=='dense':
                    # Explicit local expansion into unoccupied figure space, not a generic fitting engine.
                    body_box=[444,78,816,235]
                    extras={'reflow_reason':'Uses nearby side-margin whitespace while preserving semantic position.'}
                blocks.append(block(n,'body','paragraph',body,zh_body,[30,78,390,source_bottom],body_box,**extras))
            if name=='dense':
                c.setStrokeColorRGB(.25,.35,.3);c.rect(35,235,350,75)
                c.setFillColorRGB(.87,.91,.88);c.rect(190,240,110,65,fill=1,stroke=0)
                c.setFillColorRGB(0,0,0);c.setFont('Helvetica',10)
                c.drawString(48,270,'Entrance');c.drawString(206,270,'Quiet zone');c.drawString(320,270,'Room')
                c.drawString(35,215,'Figure 1. Route overview')
                blocks.append(block(n,'caption','caption','Figure 1. Route overview','图 1. 路线概览',
                                    [35,330,385,350],[450,330,810,352],figure_id='1',font_size=10))
                blocks.append(block(n,'labels','figure-label','Entrance; Quiet zone; Room',
                                    '左侧：入口；中部阴影区：安静区；右侧：阅览室。',
                                    [35,250,385,310],[450,270,810,316],figure_id='1',font_size=10,
                                    reflow_reason='Label notes use space beneath expanded prose, retaining figure anchors.'))
                en_cells=[['Route','Minutes','Condition'],['Short','12','Estimated'],['Accessible','18','Estimated']]
                zh_cells=[['路线','分钟','条件'],['较短路线','12','估计值，并非保证上限'],['无障碍路线','18','估计值，并非保证上限']]
                c.setFont('Helvetica',10)
                for r,cellrow in enumerate(en_cells):
                    for col,txt in enumerate(cellrow):c.drawString(35+[0,125,195][col],height-385-24*r,txt)
                for yy in (365,389,413,437):c.line(30,height-yy,390,height-yy)
                for xx in (30,155,225,390):c.line(xx,height-365,xx,height-437)
                blocks.append(block(n,'table','table','Route / Minutes / Condition; Short 12 Estimated; Accessible 18 Estimated',
                                    '路线、预计用时及条件',[30,365,390,437],[450,365,810,437],font_size=8.5,leading=11.5,
                                    table={'source_rows':en_cells,'translated_rows':zh_cells,'col_proportions':[1.6,1.2,1.2]},
                                    reflow_reason='Only the dense table uses 8.5 pt; prose keeps 11.5 pt.'))
            if label:
                c.setFont('Helvetica',8);c.drawRightString(width/2+20,20,label)
            text = (label or '') if strategy=='preserve-source' else f'{n}/{len(rows)}'
            number_box=[width+width/2-20,height-31,width+width/2+20,height-16] if label else [2*width-80,10,2*width-25,27]
            page={'source_page':n,'output_page':n,'source_rect':[0,0,width,height],
                  'kind':'translated' if blocks else 'no-translation-needed',
                  'inventory_reviewed':True,'expected_blocks':[b['id']for b in blocks],
                  'reading_order':[b['id']for b in blocks],'context_reviewed':True,'context_pages':[n],
                  'blocks':blocks,'pagination':{'id':f'p{n:03d}-number','source_label':label,
                                               'text':text,'target_bbox':number_box,'font_size':8}}
            if not blocks:page['reason']='Blank source page; only the generated page label is added.'
            state['pages'].append(page);c.showPage()
        c.save();state['source']={'path':str(source),'sha256':digest(source)}
        state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        result=builder.build(source,state_path,folder/'bilingual.pdf')
        built_state=json.loads(Path(result['state']).read_text(encoding='utf-8'))
        audit=tools.audit(source,result['output'],built_state,dpi=120)
        tools.write_json(audit,folder/'audit.json')
        fonts=check_fonts(result['state'],result['assignments']);tools.write_json(fonts,folder/'fonts.json')
        check=tools.check_state(result['state']);tools.write_json(check,folder/'state-check.json')
        assert audit['mechanical_pass'] and fonts['mechanical_pass'] and check['valid'], (audit,fonts,check)
        assert tools.main(['render',result['output'],'--source',str(source),'--state',result['state'],
                           '--out',str(folder/'renders'),'--dpi','120'])==0
        repeat=builder.build(source,state_path,folder/'repeat.pdf')
        assert result['sha256']==repeat['sha256']
        results.append({'scenario':name,'pages':len(rows),'output':result['output'],
                        'sha256':result['sha256'],'mechanical_pass':True,
                        'repeated_build_identical':True,'visual_review_completed':False})
    tools.write_json({'samples':results},out/'index.json')
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True);parser.add_argument('--font',required=True)
    parser.add_argument('--face-index',type=int,default=0)
    args=parser.parse_args()
    print(json.dumps(generate(args.out,args.font,args.face_index),ensure_ascii=False,indent=2))
