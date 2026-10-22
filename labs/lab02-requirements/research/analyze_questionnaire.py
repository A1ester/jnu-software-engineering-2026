"""Reproduce aggregate statistics from the respondent-confirmed local workbook.

Usage: python analyze_questionnaire.py LOCAL.xlsx --output-dir statistics
Only aggregate data are exported. IPs, submission metadata and individual
free-text responses remain in the local source workbook.
"""
from pathlib import Path
from collections import Counter
from datetime import datetime
import argparse
import csv
import hashlib
import json
import re
from statistics import median
import openpyxl

# One-based workbook columns and the original questionnaire option order.
SINGLE = {
    1: (7, ['大一','大二','大三','大四','研究生','其他']),
    4: (19, ['完全不相符','比较不相符','一般','比较相符','完全相符','无法判断或未接触']),
    6: (26, ['寻找报名入口','填写信息','确认是否报名成功','无明显耗时问题','没有报过名','其他']),
    7: (27, ['通过线上入口取消','私信组织者说明','直接缺席','未遇到这种情况','其他']),
    9: (29, ['加入候补并获知候补顺序','仅提示满员，停止报名','推荐其他活动','无所谓','其他']),
    13: (43, ['回顾参与经历','证明参加过活动','查看活动反馈','几乎不查看','其他']),
    16: (51, ['群消息','表格或共享文档','专门的任务管理工具','口头安排','未参与过筹备','其他']),
}
MULTI = {
    2: (8, ['参加过活动','担任过社团成员','参与过活动筹备','担任过社团负责人','以上均无'], [4]),
    3: (13, ['社团群或班级群','公众号或学校网页','朋友推荐','线下海报','其他','尚未关注'], [5]),
    5: (20, ['时间','社团','地点','主题','其他','不使用筛选'], [5]),
    10: (30, ['报名或候补结果','活动临近提醒','筹备任务截止提醒','其他','无需提醒'], [4]),
    12: (36, ['签到入口难找','排队时间长','误签或代签','签到记录不清楚','其他','未遇到问题','未参加过'], [5,6]),
    15: (45, ['申请进度不清楚','成员身份不明确','负责人交接不清楚','其他','目前无需求','不了解'], [4,5]),
    18: (53, ['任务负责人','截止时间','完成状态','其他','无明显遗漏','未参与过筹备'], [4,5]),
    19: (59, ['不知道是否可用','审批进度不清楚','时间或资源冲突','其他','未遇到困难','未接触过'], [4,5]),
    21: (66, ['联系方式','报名名单','个人签到记录','社团内部筹备任务','其他','无特别要求'], [5]),
}
OPEN = {8:28,11:35,14:44,17:52,20:65,22:72,23:73}
TOPICS = {
    '报名与退出': r'报名|取消|退出|候补|名额',
    '签到与参与记录': r'签到|签退|打卡|时长|证明|参与记录|历史记录',
    '场地物资与审批': r'场地|物资|审批|预约|审核|经费|报销',
    '信息与通知': r'信息|通知|提醒|消息|发布|公告|同步',
    '任务与协作': r'任务|分工|协作|进度|负责人|责任|看板',
    '界面与运行体验': r'界面|页面|移动|手机|适配|加载|稳定|性能|响应',
    '隐私与个人信息': r'隐私|个人信息|手机号|联系方式|绑定|授权',
    '照片与资料归档': r'照片|相册|云存储|归档',
    '社交游戏与积分': r'聊天|社交|游戏|积分|排行榜',
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    digest=hashlib.sha256(args.source.read_bytes()).hexdigest()
    book=openpyxl.load_workbook(args.source,read_only=True,data_only=True)
    sheet=book['清洗后数据']
    values=list(sheet.values()) if callable(sheet.values) else list(sheet.values)
    header,rows=values[0],values[1:]
    assert len(header)==73 and len(rows)==369
    assert len(set(r[0] for r in rows))==len(rows)
    n=len(rows)
    within,cross,malformed=[],[],[]
    for r in rows:
        for q,(start,labels,exclusive) in MULTI.items():
            v=r[start-1:start-1+len(labels)]
            if any(x not in (0,1) for x in v) or sum(x==1 for x in v)==0:
                malformed.append((r[0],q))
            if any(v[i]==1 for i in exclusive) and sum(x==1 for x in v)>1:
                within.append((r[0],q))
        for q,(col,labels) in SINGLE.items():
            if r[col-1] not in range(1,len(labels)+1): malformed.append((r[0],q))
        if ((r[7]==1 and r[41]==1) or (r[9]==1 and r[50]==5)
            or (r[9]==1 and r[57]==1)
            or (r[50]==5 and any(r[c-1]==1 for c in (53,54,55)))
            or (r[50] in (1,2,3,4) and r[57]==1)):
            cross.append(r[0])
    assert not within and not cross and not malformed, 'Source differs from the confirmed consistent version'
    groups={
        '全体':rows,
        '参加过活动': [r for r in rows if r[7]==1],
        '筹备或负责人经历': [r for r in rows if r[9]==1 or r[10]==1],
        '有场地物资接触经历': [r for r in rows if r[63]!=1],
    }
    def pct(k,denom): return round(k/denom*100,1) if denom else None
    results=[]
    for name,rs in groups.items():
        for q,(col,labels) in SINGLE.items():
            counts=Counter(r[col-1] for r in rs)
            for code,label in enumerate(labels,1):
                results.append(dict(question=f'Q{q:02}',group=name,option=label,count=counts[code],denominator=len(rs),percent=pct(counts[code],len(rs))))
        for q,(start,labels,_) in MULTI.items():
            for offset,label in enumerate(labels):
                count=sum(r[start-1+offset]==1 for r in rs)
                results.append(dict(question=f'Q{q:02}',group=name,option=label,count=count,denominator=len(rs),percent=pct(count,len(rs))))
    text_results=[]
    for q,col in OPEN.items():
        for name,rs in groups.items():
            filled=sum(r[col-1] is not None and bool(str(r[col-1]).strip()) for r in rs)
            text_results.append(dict(question=f'Q{q:02}',group=name,nonblank=filled,denominator=len(rs),percent=pct(filled,len(rs))))
    themes=[]
    for q in (22,23):
        col=OPEN[q]
        texts=[str(r[col-1] or '').strip() for r in rows]
        for topic,pattern in TOPICS.items():
            hits=sum(bool(re.search(pattern,t)) for t in texts)
            themes.append(dict(question=f'Q{q:02}',topic=topic,count=hits,denominator=n,percent=pct(hits,n),pattern=pattern))
    def count(q,label,group='全体'):
        return next(r['count'] for r in results if r['question']==f'Q{q:02}' and r['option']==label and r['group']==group)
    judged=[r for r in rows if r[18] in range(1,6)]
    durations=[int(re.search(r'\d+',str(r[2])).group()) for r in rows]
    dates=[datetime.fromisoformat(str(r[1]).replace('/','-')) for r in rows]
    rev=list(book['修正记录'].values)[1:]
    summary={
        'source_file':args.source.name,'source_sheet':'清洗后数据','sha256':digest,
        'respondent_confirmation':'全部修订均由原填写者逐项确认',
        'sample_size':n,'unique_response_ids':len(set(r[0] for r in rows)),
        'sampling':'微信群线上自愿招募的便利样本；学校分布未采集，不代表某校总体',
        'collection_start':min(dates).isoformat(),'collection_end':max(dates).isoformat(),
        'revision_records':len(rev),'revised_responses':len(set(r[1] for r in rev)),
        'quality':{'within_question_conflict_responses':len(set(x[0] for x in within)),
                   'cross_question_review_responses':len(set(cross)),
                   'malformed_responses':len(set(x[0] for x in malformed)),
                   'duplicate_full_response_groups':sum(c>1 for c in Counter(tuple(r[6:]) for r in rows).values()),
                   'duration_min_seconds':min(durations),'duration_median_seconds':median(durations),'duration_max_seconds':max(durations)},
        'groups':{k:len(v) for k,v in groups.items()},
        'information_scatter':{'judged_n':len(judged),'unable_n':n-len(judged),
            'agree_n':sum(r[18] in (4,5) for r in judged),'disagree_n':sum(r[18] in (1,2) for r in judged),
            'neutral_n':sum(r[18]==3 for r in judged),'mean_among_judged':round(sum(r[18] for r in judged)/len(judged),2)},
        'selected':{'waitlist_n':count(9,'加入候补并获知候补顺序'),
                    'no_reminder_n':count(10,'无需提醒'),
                    'signup_information_n':count(6,'填写信息'),
                    'signup_confirmation_n':count(6,'确认是否报名成功'),
                    'no_signup_experience_n':count(6,'没有报过名')},
    }
    book.close()
    assert hashlib.sha256(args.source.read_bytes()).hexdigest()==digest
    args.output_dir.mkdir(parents=True,exist_ok=True)
    for filename,records in [('questionnaire-statistics.csv',results),('open-response-coverage.csv',text_results),('open-response-themes.csv',themes)]:
        with (args.output_dir/filename).open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    (args.output_dir/'survey-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
