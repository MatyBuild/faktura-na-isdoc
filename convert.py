#!/usr/bin/env python3
"""
Faktura na ISDOC – konvertor faktur do formátu ISDOC 6.0.2

Použití:
    python convert.py faktura.pdf
    python convert.py faktura.pdf --output vystup.xml
    python convert.py faktura.pdf --json
    python convert.py *.pdf

Pipeline:
    1. PyMuPDF extrahuje text (strojové PDF → přeskočí OCR)
    2. Pokud confidence ≥ 0.85 → XML sestaví kód (bez API)
    3. Jinak OCR + Claude Sonnet → ISDOC XML
"""
import argparse
import json
import sys
from pathlib import Path

import ocr as ocr_module
import isdoc as isdoc_module
import pdf_extractor as pdf_extractor_module
import isdoc_builder as isdoc_builder_module

CONFIDENCE_THRESHOLD = 0.85


def convert_file(file_path: str, output_path: str | None = None,
                 as_json: bool = False, verbose: bool = False) -> int:
    """
    Convert a single invoice file to ISDOC XML.
    Returns 0 on success, 1 on error.
    """
    src = Path(file_path)
    if not src.exists():
        print(f"[CHYBA] Soubor nenalezen: {file_path}", file=sys.stderr)
        return 1

    print(f"Zpracovávám: {src.name}")

    xml: str | None = None
    method = ""

    # --- Fast path: code-based extraction for machine PDFs ---
    fast = pdf_extractor_module.try_extract(str(src))
    if fast and fast.is_machine_pdf and fast.confidence >= CONFIDENCE_THRESHOLD:
        if verbose:
            print(f"  → kódová extrakce (confidence {fast.confidence:.2f})")
        xml = isdoc_builder_module.build_isdoc(fast)
        method = f"kód (confidence {fast.confidence:.2f})"
    else:
        # --- Slow path: OCR + Claude ---
        if verbose:
            if fast and fast.is_machine_pdf:
                print(f"  → kódová extrakce nestačí (confidence {fast.confidence:.2f}), volám Claude")
            elif fast and not fast.is_machine_pdf:
                print("  → naskenované PDF, volám OCR + Claude")
            else:
                print("  → obrázek, volám OCR + Claude")

        try:
            text = ocr_module.extract_text(str(src))
        except ValueError as e:
            print(f"[CHYBA] {e}", file=sys.stderr)
            return 1

        try:
            xml = isdoc_module.extract_to_isdoc(text)
        except Exception as e:
            print(f"[CHYBA] Claude API selhalo: {e}", file=sys.stderr)
            return 1

        method = "OCR + Claude"

    # Validate XML
    try:
        doc = isdoc_module.isdoc_to_extracted(xml)
    except ValueError as e:
        print(f"[CHYBA] Neplatné ISDOC XML: {e}", file=sys.stderr)
        return 1

    # Determine output path
    if output_path:
        out = Path(output_path)
    else:
        out = src.with_suffix(".xml")

    if as_json:
        out = out.with_suffix(".json")
        out.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
        print(f"  ✓ JSON uložen: {out}  [{method}]")
    else:
        out.write_text(xml, encoding="utf-8")
        print(f"  ✓ ISDOC XML uložen: {out}  [{method}]")

    if verbose:
        print(f"     Dodavatel:  {doc.supplier_name or '–'}")
        print(f"     IČO:        {doc.registration_no or '–'}")
        print(f"     Číslo dok.: {doc.original_number or '–'}")
        print(f"     Vystaveno:  {doc.issued_on or '–'}")
        print(f"     Typ:        {doc.document_type.value}")
        print(f"     Položky:    {len(doc.lines)}")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Převod faktur (PDF/JPG/PNG) do formátu ISDOC 6.0.2"
    )
    parser.add_argument("files", nargs="+", help="Soubory k zpracování (PDF, JPG, PNG)")
    parser.add_argument("-o", "--output", help="Výstupní soubor (pouze pro 1 vstup)")
    parser.add_argument("--json", action="store_true",
                        help="Uložit jako JSON místo XML")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Podrobný výstup")
    args = parser.parse_args()

    if args.output and len(args.files) > 1:
        print("[CHYBA] --output lze použít pouze pro jeden vstupní soubor.", file=sys.stderr)
        sys.exit(1)

    errors = 0
    for f in args.files:
        rc = convert_file(
            f,
            output_path=args.output if len(args.files) == 1 else None,
            as_json=args.json,
            verbose=args.verbose,
        )
        errors += rc

    if errors:
        print(f"\n{errors} soubor(ů) skončilo chybou.")
        sys.exit(1)


if __name__ == "__main__":
    main()
