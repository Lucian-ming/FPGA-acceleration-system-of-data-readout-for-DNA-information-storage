#!/usr/bin/env python3
"""生成独立生产 Stage1 oracle：逐符号滑窗评分，不复用RTL/tree状态或历史结果。"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

def make(num_lc, out):
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.RandomState(20261010)
    wm = rng.randint(0, 4, (num_lc, 957)).astype(np.uint8)
    records = []
    # 这些读段的满分峰必须存在，最后位置/最后区域不可被掩码删掉。
    for pos in (807, 806, 803, 800, 799, 15, 0):
        records.append(wm[-1, pos:pos+150].copy())
    for pos in (807, 16, 1):
        forward = wm[0, pos:pos+150].copy()
        records.extend((forward, forward[::-1] ^ 1))  # A/T、G/C互补
    while len(records) < 37:
        records.append(rng.randint(0, 4, 150).astype(np.uint8))
    records.extend([np.zeros(150, dtype=np.uint8) for _ in range(64-len(records))])
    # oracle枚举LC/pos，argmax返回第一个最大项，直接定义并列低序号契约。
    windows = np.stack([wm[:, p:p+150] for p in range(808)], axis=1)
    expected = []
    cache = {}
    for record in records:
        key = record.tobytes()
        if key not in cache:
            scores = (windows == record).sum(axis=2).reshape(-1)
            winner = int(scores.argmax())
            cache[key] = (winner//808*807 + winner%808, int(scores[winner]))
        pos, score = cache[key]
        cw = sum(int((record[k] >> 1) & 1) << k for k in range(150))
        cw |= sum(int(record[k] & 1) << (150+k) for k in range(150))
        expected.append((cw << 26) | (pos << 10) | score)
    if ((expected[0] >> 10) & 0xffff) != num_lc*807 or (expected[0] & 1023) != 150:
        raise ValueError('最后区域/807唯一满分定向向量失去鉴别力')
    (out/'wm.hex').write_text(''.join(f'{int(s):x}\n' for s in wm.reshape(-1)))
    (out/'reads.hex').write_text(''.join(f'{v >> 26:075x}\n' for v in expected))
    (out/'expect.hex').write_text(''.join(f'{v:082x}\n' for v in expected))
    # 第二轮全A水印：A读段150分且最低位置0，T/C/G读段0分且位置0。
    repeat_reads = []
    repeat_expect = []
    for i in range(64):
        symbol = i % 4
        cw = (((1 << 150)-1) if symbol & 2 else 0) | ((((1 << 150)-1) << 150) if symbol & 1 else 0)
        repeat_reads.append(cw)
        repeat_expect.append((cw << 26) | (150 if symbol == 0 else 0))
    (out/'repeat_reads.hex').write_text(''.join(f'{v:075x}\n' for v in repeat_reads))
    (out/'repeat_expect.hex').write_text(''.join(f'{v:082x}\n' for v in repeat_expect))
    manifest = {'seed': 20261010, 'READ_BPS':150,'NUM_LC':num_lc,'STRIDE':807,'REF_LEN':957,'BATCH':64,
                'oracle':'枚举符号相等计数，LC和pos从低到高，严格首次argmax',
                'real_records':37, 'padding_records':27,
                'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('*.hex')}}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(manifest,ensure_ascii=False))

if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--num-lc',type=int,default=50,choices=(6,50))
    ap.add_argument('--out-dir',type=Path,required=True)
    args=ap.parse_args();make(args.num_lc,args.out_dir)
