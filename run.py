#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""启动：python3 run.py（终端里能看到日志）"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.app import main

if __name__ == "__main__":
    main()
