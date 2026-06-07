"""
Exhaustive token benchmark across architecture-description formats.

Same representative slice of the architecture, encoded in each format under
bench/formats/. 

Measures tokens with real LLM tokenizers (tiktoken) and ranks
them against Veltro.

Run:  python bench/compare_formats.py
"""

import os
import glob
import tiktoken

HERE = os.path.dirname(os.path.abspath(__file__))
FORMATS_DIR = os.path.join(HERE, "formats")

LABEL = {
    ".vel": "Veltro",
    ".puml": "PlantUML",
    ".mmd": "Mermaid",
    ".dot": "Graphviz DOT",
    ".d2": "D2",
    ".nomnoml": "Nomnoml",
    ".yuml": "yUML",
}

ENCODERS = ["cl100k_base", "o200k_base"]


def read(path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()


def main():
    
    files = sorted(glob.glob(os.path.join(FORMATS_DIR, "slice.*")))
    
    for enc_name in ENCODERS:
        enc = tiktoken.get_encoding(enc_name)
        rows = []
        
        for path in files:
            ext = os.path.splitext(path)[1]
            label = LABEL.get(ext, ext)
            toks = len(enc.encode(read(path)))
            rows.append((label, toks))
        
        rows.sort(key=lambda r: r[1])
        base = dict(rows).get("Veltro")
        print(f"\n=== tokenizer: {enc_name} ===")
        print(f"{'rank':>4} {'format':14} {'tokens':>7} {'vs Veltro':>10}")
        
        for i, (label, toks) in enumerate(rows, 1):
            delta = "" if label == "Veltro" else f"{(toks / base - 1) * 100:+.0f}%"
            star = "  <--" if label == "Veltro" else ""
            print(f"{i:>4} {label:14} {toks:7} {delta:>10}{star}")


if __name__ == "__main__":
    main()
