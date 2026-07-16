"""
Exhaustive token benchmark across architecture-description formats.

Same representative slice of the architecture, encoded in each format under
bench/formats/. 

Measures tokens using Hugging Face transformers tokenizers (e.g., Llama 3)
and ranks them against Veltro.

Run:  python bench/compare_formats_ollama.py
"""

import os
import glob
from transformers import AutoTokenizer

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

MODELS = ["meta-llama/Meta-Llama-3-8B"]

def read(path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()

def main():
    files = sorted(glob.glob(os.path.join(FORMATS_DIR, "slice.*")))
    
    for model_id in MODELS:
        print(f"\nCaricamento tokenizer: {model_id}...")
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        
        rows = []
        for path in files:
            ext = os.path.splitext(path)[1]
            label = LABEL.get(ext, ext)
            
            toks = len(tokenizer.encode(read(path)))
            rows.append((label, toks))
        
        rows.sort(key=lambda r: r[1])

        base = dict(rows).get("Veltro")
        
        print(f"\n=== tokenizer: {model_id} ===")
        print(f"{'rank':>4} {'format':14} {'tokens':>7} {'vs Veltro':>10}")
        
        for i, (label, toks) in enumerate(rows, 1):
            delta = "" if label == "Veltro" else f"{(toks / base - 1) * 100:+.0f}%"
            star = "  <--" if label == "Veltro" else ""
            print(f"{i:>4} {label:14} {toks:7} {delta:>10}{star}")

if __name__ == "__main__":
    main()