#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""静态检查：NSObject 子类里的方法名和参数个数是否符合 PyObjC 的 selector 规则。

    python3 tests/test_pyobjc_names.py

PyObjC 会把 NSObject 子类里的方法自动注册成 Objective-C selector：
    - 名字中间有下划线、但不以下划线结尾（如 _update_idle）-> 普通 Python 方法，不检查
    - 否则下划线换成冒号，冒号数就是参数个数（如 setSize_ -> setSize:，1 个参数；
      _restart -> _restart，0 个参数）
参数个数对不上，导入 app.py 时就会抛 BadPrototypeError，App 直接起不来。
需要带参数的内部辅助方法，加 @objc.python_method。

这个检查只用 ast，不需要 macOS / PyObjC，任何机器上都能跑。
规则摘自 pyobjc-core 的 objc/_transform.py（default_selector + transformAttribute）。
"""
import ast
import glob
import keyword
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBJC_BASES = {"NSObject", "NSView", "NSWindow", "NSPanel"}


def default_selector(name):
    if name.endswith("__") and keyword.iskeyword(name[:-2]):
        name = name[:-2]
    if name.startswith("__") and name.endswith("__"):
        return None
    if "_" in name[1:] and not name.endswith("_"):
        return None
    sel = name.replace("_", ":")
    if sel.startswith(":"):
        sel = "_" + sel[1:]
    return sel


def problems():
    found = []
    for path in sorted(glob.glob(os.path.join(ROOT, "src", "**", "*.py"), recursive=True)):
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        objc_classes = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = {getattr(b, "id", getattr(b, "attr", None)) for b in node.bases}
            if not bases & (OBJC_BASES | objc_classes):
                continue
            objc_classes.add(node.name)
            for fn in node.body:
                if not isinstance(fn, ast.FunctionDef):
                    continue
                decos = [ast.dump(d) for d in fn.decorator_list]
                if any("python_method" in d or "staticmethod" in d or "classmethod" in d
                       for d in decos):
                    continue
                sel = default_selector(fn.name)
                if sel is None or fn.args.vararg:
                    continue
                argc = sel.count(":")
                pos = len(fn.args.args)
                pos_default = len(fn.args.defaults)
                if pos < argc + 1 or pos - pos_default > argc + 1:
                    found.append("%s:%d %s.%s —— selector %r 需要 %d 个参数，实际 %d 个"
                                 % (os.path.relpath(path, ROOT), fn.lineno, node.name,
                                    fn.name, sel, argc, pos - 1))
    return found


def main():
    print("== PyObjC 方法名 / 参数个数")
    bad = problems()
    for line in bad:
        print("  ❌ " + line)
    if bad:
        print("\n修法：内部辅助方法加 @objc.python_method，或改名让中间带下划线。")
        return 1
    print("  ✅ 所有 NSObject 子类的方法都符合 selector 规则")
    print("\nPyObjC 命名检查通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
