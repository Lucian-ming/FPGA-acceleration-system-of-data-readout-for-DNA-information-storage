#!/usr/bin/env python3
"""新板P4/P16同板性能矩阵：每档>=3次，精确补帧数，结果与整轮墙钟分别留证。"""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import json
import math
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'clients/python'))
from first import ClientConfig,run_client
from g3_artifacts import validate
from g3_caps import CAPS_ARCHITECTURE_BOUNDARY,query_board_caps

EXPECT_SHA='fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3'

def read_uart_cycles(path, offset):
    """只解析本轮新增的UART字节；不以墙钟推导硬件周期。"""
    if path is None:
        return None, 'UNMEASURED: 未提供外部实时UART日志；生产固件已有Stage2/3计数器'
    if not path.is_file() or path.stat().st_size < offset:
        return None, 'UNMEASURED: UART日志消失或被截断'
    with path.open('rb') as stream:
        stream.seek(offset)
        text=stream.read().decode('ascii',errors='replace')
    patterns={
        'stage2_voter': r'\[HW-CYCLES\] Stage2 Voter: total (\d+) cyc \([^\r\n]*?\), init (\d+), read (\d+), vote (\d+), write (\d+)',
        'stage3_decoder': r'\[HW-CYCLES\] Stage3 Decoder: total (\d+) cyc \([^\r\n]*?\), rd_busy (\d+), wr_busy (\d+), rd_wait (\d+)'
    }
    keys={'stage2_voter': ('total','init','read','vote','write'),
          'stage3_decoder': ('total','rd_busy','wr_busy','rd_wait')}
    values={}
    for stage,pattern in patterns.items():
        matches=re.findall(pattern,text)
        if len(matches)!=1:
            return None, f'UNMEASURED: 本轮{stage}记录数={len(matches)}，拒绝跨任务混用'
        values[stage]=dict(zip(keys[stage],map(int,matches[0])))
    values['stage1']=None
    return values, 'MEASURED: UART原始寄存器周期；Stage1尚无本脚本可采集的硬件周期'

def fit(rows):
    if len(rows)<2:raise ValueError('拟合至少需要两档成功结果')
    xs=[r['record_count'] for r in rows];ys=[r['t_result_median_s'] for r in rows]
    mx,my=statistics.mean(xs),statistics.mean(ys)
    sxx=sum((x-mx)**2 for x in xs)
    if not sxx:raise ValueError('拟合需要不同实际记录数')
    slope=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/sxx
    intercept=my-slope*mx
    sst=sum((y-my)**2 for y in ys)
    residual=sum((y-intercept-slope*x)**2 for x,y in zip(xs,ys))
    return {'intercept_s':intercept,'slope_s_per_record':slope,'r2':1-residual/sst if sst else None}

def count_reads(path):
    with path.open() as f:
        lines=sum(1 for _ in f)
    if lines%4:raise ValueError('FASTQ行数不是4的倍数')
    return lines//4

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--artifact-dir',type=Path,required=True)
    ap.add_argument('--out-dir',type=Path,required=True)
    ap.add_argument('--reads',type=Path,default=REPO/'../data/r083-data/sequencing-data/dna-40_5kb-mc-se150.fastq')
    ap.add_argument('--watermark',type=Path,default=REPO/'../data/r083-data/source-data/watermark-sequences/r0.83_watermark.txt')
    ap.add_argument('--limits',default='128,512,2048,8192,32768,full')
    ap.add_argument('--repeat',type=int,default=3)
    ap.add_argument('--ip',required=True,help='必须显式指定本轮实测板端 IP');ap.add_argument('--port',type=int,default=7)
    ap.add_argument('--timeout',type=float,default=1800)
    ap.add_argument('--uart-log',type=Path,help='由外部唯一串口采集进程持续追加的UART日志；本脚本不打开串口')
    ap.add_argument('--plan-only',action='store_true')
    args=ap.parse_args()
    if args.repeat<3:ap.error('正式性能每档至少3次')
    if args.timeout<=0:ap.error('timeout必须为正')
    if args.uart_log is not None and not args.uart_log.is_file():ap.error('uart-log必须是已启动采集的现有文件')
    selection=validate(args.artifact_dir);selection.pop('_ps7')
    total=count_reads(args.reads)
    limits=[total if n=='full' else int(n) for n in args.limits.split(',')]
    if any(n<=0 or n>total for n in limits):ap.error('limit越出真实输入文件规模')
    if len(limits)!=len(set(limits)):ap.error('重复档位')
    padded=[(n*2+63)//64*64 for n in limits]
    if len(padded)!=len(set(padded)):ap.error('多档输入补帧后记录数重复，无法独立拟合')
    plan={'artifact_selection':selection,'limits':limits,'repeats':args.repeat,
          'record_count':{str(n):((n*2+63)//64*64) for n in limits},
          'boundaries':{'t_result':'POST发送至8100B结果收齐，不含上传和LDPC',
                        'round_wall':'run_client开始至LDPC进程结束和图片hash完成，含输入处理/上传/结果/LDPC；不含烧录、DDR取证和轮间settle',
                        'hardware_cycles':'本轮追加UART中的Stage2/3寄存器周期；未采集为null，绝不用t_result乘时钟冒充'},
          'uart_log':str(args.uart_log) if args.uart_log is not None else None,
          'caps_architecture_boundary':CAPS_ARCHITECTURE_BOUNDARY,
          'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.reads,args.watermark)}}
    if args.plan_only:print(json.dumps(plan,ensure_ascii=False,indent=2));return 0
    caps=query_board_caps(args.ip,args.port)
    plan['caps_at_start']={name:getattr(caps,name) for name in
                           ('version','read_bps','num_lc','stride','max_symbols','max_reads','features')}
    if args.out_dir.exists() and any(args.out_dir.iterdir()):ap.error('out-dir已有证据，不覆盖')
    args.out_dir.mkdir(parents=True,exist_ok=True)
    (args.out_dir/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    summary=[];failed=False
    with (args.out_dir/'samples.jsonl').open('w') as samples:
        for limit in limits:
            times=[]
            for rep in range(1,args.repeat+1):
                prefix=args.out_dir/f'n{limit}_r{rep}'
                row={'source_reads':limit,'record_count':plan['record_count'][str(limit)],'repeat':rep,
                     'hardware_cycles':None,'hardware_cycles_note':'UNMEASURED: 本轮未完成UART周期采集',
                     'power_w':None,'status':'FAIL'}
                began=time.perf_counter()
                try:
                    uart_offset=args.uart_log.stat().st_size if args.uart_log is not None else 0
                    cfg=ClientConfig(ip=args.ip,port=args.port,watermark=args.watermark,reads=args.reads,
                                     out=prefix.with_suffix('.bits.txt'),send_limit=limit,read_bps=150,
                                     score_min=67,orient='both',post=True,result_timeout=args.timeout)
                    with prefix.with_suffix('.client.log').open('w') as log,contextlib.redirect_stdout(log):
                        stats=run_client(cfg)
                    if not math.isfinite(stats.t_result) or stats.t_result<=0:
                        row['rejected_timing']=repr(stats.t_result)
                        raise ValueError('客户端结果耗时必须为有限正数')
                    row.update(t_result_s=stats.t_result,client_wall_s=time.perf_counter()-began,
                               t_wm_s=stats.t_wm,t_reads_s=stats.t_batches,client_total_s=stats.t_total)
                    row['hardware_cycles'],row['hardware_cycles_note']=read_uart_cycles(args.uart_log,uart_offset)
                    ldpc_start=time.perf_counter()
                    with prefix.with_suffix('.ldpc.log').open('w') as log:
                        proc=subprocess.run([sys.executable,str(REPO/'tools/ldpc_decode.py'),'decode',
                            str(prefix.with_suffix('.bits.txt')),'-o',str(prefix.with_suffix('.decoded.txt')),
                            '--image',str(prefix.with_suffix('.jpg'))],stdout=log,stderr=subprocess.STDOUT)
                    row['ldpc_wall_s']=time.perf_counter()-ldpc_start
                    image=prefix.with_suffix('.jpg')
                    row['image_sha256']=hashlib.sha256(image.read_bytes()).hexdigest() if image.exists() else None
                    row['hash_match']=row['image_sha256']==EXPECT_SHA
                    # 小样本覆盖不足不作为功能失败，仍如实记录译码失败；全量必须正确。
                    row['correctness_required']=limit==total
                    row['functional_status']=('PASS' if proc.returncode==0 and row['hash_match'] else 'FAIL') if limit==total else 'NOT_REQUIRED_PARTIAL_INPUT'
                    row['status']='PASS' if limit!=total or row['functional_status']=='PASS' else 'FAIL'
                    row['ldpc_returncode']=proc.returncode
                    if row['status']=='PASS':times.append(row['t_result_s'])
                except Exception as error:
                    row['error']=f'{type(error).__name__}: {error}'
                row['round_wall_s']=time.perf_counter()-began
                failed=failed or row['status']=='FAIL'
                samples.write(json.dumps(row,ensure_ascii=False)+'\n');samples.flush()
                print(json.dumps(row,ensure_ascii=False),flush=True)
                time.sleep(1)
            if len(times)==args.repeat:
                summary.append({'source_reads':limit,'record_count':plan['record_count'][str(limit)],
                                'samples':len(times),'t_result_median_s':statistics.median(times),
                                'min_s':min(times),'max_s':max(times),'stdev_s':statistics.stdev(times)})
            else:failed=True
    result={'status':'FAIL' if failed else 'PASS','scope':'performance-samples; functional PASS requires full-input LDPC hash',
            'sizes':summary,'fit':fit(summary) if len(summary)>=2 else None}
    (args.out_dir/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2));return 1 if failed else 0

if __name__=='__main__':raise SystemExit(main())
