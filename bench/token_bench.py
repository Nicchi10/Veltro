"""
Token benchmark: PlantUML source vs Veltro .vel, on real architecture


Run:  python bench/token_bench.py

"""
import os
import tiktoken

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# (label, PlantUML source, Veltro source) all relative to the repo.
PAIRS = [
    (
        "z_Loom (consolidated)",
        os.path.join(HERE, "z_Loom.puml"),
        os.path.join(ROOT, "examples", "z_Loom.vel"),
    ),
]

ENCODERS = ["cl100k_base", "o200k_base"]


def read(path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()


def main():
    
    for enc_name in ENCODERS:
        enc = tiktoken.get_encoding(enc_name)
        print(f"\n=== tokenizer: {enc_name} ===")
        print(f"{'diagram':24} {'UML':>6} {'VEL':>6} {'saved':>7} {'%':>7}")
        
        for label, uml, vel in PAIRS:
            tu = len(enc.encode(read(uml)))
            tv = len(enc.encode(read(vel)))
            pct = 100 * (tu - tv) / tu if tu else 0
            print(f"{label:24} {tu:6} {tv:6} {tu - tv:7} {pct:6.1f}%")


if __name__ == "__main__":
    main()
