#!/usr/bin/env bash
# 重新生成 data/MANIFEST.md。数据有任何变更都必须重跑，否则清单会悄悄过期。
set -euo pipefail
cd "$(dirname "$0")/.."
echo "请直接编辑并重跑生成命令；逐文件哈希用："
find data -type f ! -name 'MANIFEST*' | sort | xargs -I{} sha256sum {}
