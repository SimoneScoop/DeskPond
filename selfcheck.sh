#!/bin/bash
# 一键自检：核心逻辑、摸鱼流程、素材读取（装了游戏会顺便读真实文件）、PyObjC 命名、Windows 版（没装 PySide6 时跳过）
cd "$(dirname "$0")" || exit 1
fail=0
for t in tests/test_core.py tests/test_session.py tests/test_assets.py tests/test_ui_smoke.py tests/test_pyobjc_names.py tests/test_qt_smoke.py; do
  echo "────── $t"
  python3 "$t" || fail=1
done
echo
if [ $fail -eq 0 ]; then echo "全部通过 ✅"; else echo "有测试没过 ❌"; fi
exit $fail
