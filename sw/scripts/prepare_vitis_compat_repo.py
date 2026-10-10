#!/usr/bin/env python3
"""复制Vitis自带lwIP为本地兼容库，只移除YAML的UTF-8 BOM，不修改安装。"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--vitis-root',type=Path,required=True)
    ap.add_argument('--out-dir',type=Path,required=True)
    args=ap.parse_args()
    source_root=args.vitis_root.resolve()/'data/embeddedsw'
    matches=sorted((source_root/'ThirdParty/sw_services').glob('lwip220*'))
    matches=[p for p in matches if (p/'data/lwip220.yaml').is_file()]
    if len(matches)!=1:ap.error(f'要求唯一原厂lwip220库，实际{matches}')
    source=matches[0];out=args.out_dir.resolve()
    if out.exists():ap.error('out-dir必须不存在，禁止覆盖历史兼容库/证据')
    try:out.relative_to(args.vitis_root.resolve())
    except ValueError:pass
    else:ap.error('输出必须在Vitis安装目录之外')
    target=out/'ThirdParty/sw_services'/source.name
    shutil.copytree(source,target)
    for p in target.rglob('*'):
        if p.is_file():p.chmod(stat.S_IREAD|stat.S_IWRITE)
    metadata=target/'data/lwip220.yaml'
    before=metadata.read_bytes()
    had_bom=before.startswith(b'\xef\xbb\xbf')
    if had_bom:metadata.write_bytes(before[3:])
    manifest={'schema_version':1,'scope':'BOM-only metadata compatibility; library source unchanged',
              'source_root':str(source),'output_root':str(target),'removed_bom':had_bom,'files':{}}
    for old in sorted(source.rglob('*')):
        if not old.is_file():continue
        rel=old.relative_to(source);new=target/rel
        if rel.as_posix()!='data/lwip220.yaml' and new.read_bytes()!=old.read_bytes():
            raise RuntimeError(f'兼容复制改变了原厂源码：{rel}')
        manifest['files'][rel.as_posix()]={'original_sha256':sha(old),'compat_sha256':sha(new)}
    (out/'compat-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"VITIS_COMPAT_REPO_PASS files={len(manifest['files'])} removed_bom={had_bom} repo={out}")
    return 0

if __name__=='__main__':raise SystemExit(main())
