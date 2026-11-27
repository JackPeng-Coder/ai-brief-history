# -*- coding: utf-8 -*-
import os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
root = "content"
words = [" and ", " of ", " the ", " with ", " from ", " that ", " this ", " is ", " are ",
         "benchmark", "dataset", "landscape", "vendor", "funding", "parse", " sum ", "comprehensive",
         "conformity", "automat", "frontier", "governance", "alignment", "agentic", "scaling law"]
for fn in sorted(os.listdir(root)):
    if not fn.endswith(".md"):
        continue
    path = os.path.join(root, fn)
    for i, line in enumerate(open(path, encoding="utf-8"), 1):
        low = line.lower()
        for w in words:
            if w in low:
                print(f"{fn}:{i}: {line.strip()[:240]}")
                break
