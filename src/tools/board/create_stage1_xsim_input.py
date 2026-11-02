#!/usr/bin/env python3
"""将正式生产RTL/TB与LC50 oracle复制为带完整SHA的Windows XSim输入。"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HDL_NAMES=('dna_accelerator_core.v','dna_accelerator_core_s_axi_lite_ctrl.v',
           'fifo_sync_sdpram_b64.v','s2mm_pack64.v','srpe_batch_4way.v','srpe_batch_pway.v')
TB_NAMES=('tb_dna_stage1_p16_equivalence.v','tb_dna_stage1_p16_interface.v')
FIXTURE_NAMES=('wm.hex','reads.hex','expect.hex','repeat_reads.hex','repeat_expect.hex')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo-root',type=Path,default=Path(__file__).resolve().parents[2])
    ap.add_argument('--fixtures-dir',type=Path,required=True)
    ap.add_argument('--out-dir',type=Path,required=True)
    args=ap.parse_args()
    repo=args.repo_root.resolve();fixtures=args.fixtures_dir.resolve();out=args.out_dir.resolve()
    if out.exists():ap.error('out-dir必须不存在，禁止覆盖历史源码快照')
    meta=json.loads((fixtures/'manifest.json').read_text(encoding='utf-8-sig'))
    for key,value in {'READ_BPS':150,'NUM_LC':50,'STRIDE':807,'REF_LEN':957,'BATCH':64}.items():
        if meta.get(key)!=value:ap.error(f'oracle正式参数不符：{key}')
    for name in FIXTURE_NAMES:
        if meta.get('sha256',{}).get(name)!=sha(fixtures/name):ap.error(f'oracle文件哈希不符：{name}')
    hdl=repo/'hw/ip/dna_accelerator_core_1_0/hdl';tb=repo/'../sim/rtl/ip_tb'
    files=[(hdl/n,Path('hdl')/n) for n in HDL_NAMES]+[(tb/n,Path('tb')/n) for n in TB_NAMES]
    files += [(fixtures/n,Path('fixtures')/n) for n in FIXTURE_NAMES+('manifest.json',)]
    if any(not p.is_file() for p,_ in files):ap.error('生产RTL/TB输入缺文件')
    manifest={'schema_version':1,'scope':'SE150 LC50 P4/P16 production simulation input','files':{}}
    for src,rel in files:
        dst=out/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
        digest=sha(src)
        if sha(dst)!=digest:raise RuntimeError(f'复制输入哈希不符：{src}')
        manifest['files'][rel.as_posix()]=digest
    (out/'source_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(f'XSIM_PRODUCTION_INPUT_PASS files={len(files)} input={out}')
    return 0

if __name__=='__main__':raise SystemExit(main())
