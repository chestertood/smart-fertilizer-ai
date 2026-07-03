"""Batch-convert PDFs to Markdown for the knowledge base.

Reads every .pdf in knowledge/_raw_pdf/ and writes a same-named .md into
knowledge/_raw/. Those raw .md files are a staging area — they still need
to be summarized/rewritten by hand (or via Claude) into the concise,
smart-farm-focused format used by files like knowledge/tropical/leafy_greens.md
before they're actually useful in the LLM prompt.

Usage:
    python scripts/pdf_to_md.py
    python scripts/pdf_to_md.py --src some/other/folder --out some/other/out
"""

import argparse
from pathlib import Path

import pymupdf4llm

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SRC = _PROJECT_ROOT / "knowledge" / "_raw_pdf"
_DEFAULT_OUT = _PROJECT_ROOT / "knowledge" / "_raw"


def convert_all(src_dir: Path, out_dir: Path) -> None:
    pdf_paths = sorted(src_dir.glob("*.pdf"))
    if not pdf_paths:
        print(f"No PDFs found in {src_dir}")
        print("Drop .pdf files there and re-run.")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    for pdf_path in pdf_paths:
        print(f"Converting {pdf_path.name} ...")
        try:
            md_text = pymupdf4llm.to_markdown(str(pdf_path))
        except Exception as exc:
            print(f"  FAILED: {exc}")
            continue
        out_path = out_dir / f"{pdf_path.stem}.md"
        out_path.write_text(md_text, encoding="utf-8")
        print(f"  -> {out_path.relative_to(_PROJECT_ROOT)} ({len(md_text)} chars)")

    print(f"\nDone. {len(pdf_paths)} file(s) processed.")
    print(f"Raw markdown is in {out_dir} — still needs summarizing into the")
    print("knowledge/tropical|temperate|general format before it's prompt-ready.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=_DEFAULT_SRC,
                         help="Folder of source PDFs (default: knowledge/_raw_pdf)")
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT,
                         help="Folder to write .md files (default: knowledge/_raw)")
    args = parser.parse_args()
    convert_all(args.src, args.out)


if __name__ == "__main__":
    main()
