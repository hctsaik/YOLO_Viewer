#!/usr/bin/env python3
"""U-Net 唯讀稽核:三層同名對齊、AC↔測試雙向覆蓋缺口、總測試數。
只報客觀事實,絕不用「檔案存在」推斷「完成」。用法:python verify/unet_status.py
"""
import os, re, glob, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def stem(p, prefix=""):
    n = re.sub(r"^\d+_", "", os.path.splitext(os.path.basename(p))[0])
    return n[len(prefix):] if prefix and n.startswith(prefix) else n

designs = {stem(p): p for p in glob.glob(os.path.join(ROOT, "3_Architect_Design", "*.md"))}
tests   = {stem(p, "test_"): p for p in glob.glob(os.path.join(ROOT, "4_PM_Feedback", "test_*.py"))}
impls   = {stem(p): p for p in glob.glob(os.path.join(ROOT, "5_PG_Develop", "*.py"))
           if not os.path.basename(p).startswith("__")}
mods = sorted(set(designs) | set(tests) | set(impls))

print("== 三層對齊 ==")
print("%-20s 設計 驗收 實作" % "module")
for m in mods:
    f = lambda d: "v" if m in d else "X"
    print("%-20s  %s    %s    %s" % (m, f(designs), f(tests), f(impls)))

AC = re.compile(r"AC[-_ ]?\w+")
print("\n== AC <-> 測試 雙向覆蓋(只驗掛名,不驗行為正確)==")
for m in mods:
    d_ac = set(AC.findall(open(designs[m], encoding="utf-8").read())) if m in designs else set()
    t_ac = set(AC.findall(open(tests[m], encoding="utf-8").read())) if m in tests else set()
    miss = d_ac - t_ac; orphan = t_ac - d_ac
    if miss or orphan:
        print("  %s: 無對應測試的 AC=%s; 找不到 AC 的測試標註=%s"
              % (m, sorted(miss) or "-", sorted(orphan) or "-"))

try:
    co = subprocess.run([sys.executable, "-m", "pytest", "--co", "-q", "4_PM_Feedback"],
                        cwd=ROOT, capture_output=True, text=True)
    print("\n== 總測試數(pytest 收集)==", sum(1 for l in co.stdout.splitlines() if "::" in l))
except Exception as e:
    print("無法收集測試數:", e)

print("\n注意:本稽核不判斷『完成』。請用上表核對 ROADMAP 模組表是否漂移(模組數 / 測試數)。")
