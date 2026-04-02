#!/usr/bin/env python3
"""
Faktura na ISDOC – konvertor faktur do formátu ISDOC 6.0.2

Použití:
    python convert.py faktura.pdf
    python convert.py faktura.pdf --output vystup.xml
    python convert.py faktura.pdf --json --provider openai
    python convert.py *.pdf

Pipeline:
    1. PyMuPDF extrahuje text (strojové PDF → přeskočí OCR)
    2. Pokud confidence ≥ 0.85 → XML sestaví kód (bez API)
    3. Jinak OCR + LLM (Claude nebo OpenAI) → ISDOC XML
"""
import argparse
import sys
from pathlib import Path

import ocr as ocr_module
import isdoc as isdoc_module
import pdf_extractor as pdf_extractor_module
import isdoc_builder as isdoc_builder_module
from models import DocumentType

CONFIDENCE_THRESHOLD = 0.85


def convert_file(file_path: str, output_path: str | None = None,
                 as_json: bool = False, verbose: bool = False,
                 provider: str | None = None) -> int:
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
        # --- Slow path: OCR + LLM ---
        from config import LLM_PROVIDER
        effective_provider = provider or LLM_PROVIDER
        provider_label = effective_provider.capitalize()

        if verbose:
            if fast and fast.is_machine_pdf:
                print(f"  → kódová extrakce nestačí (confidence {fast.confidence:.2f}), volám {provider_label}")
            elif fast and not fast.is_machine_pdf:
                print(f"  → naskenované PDF, volám OCR + {provider_label}")
            else:
                print(f"  → obrázek, volám OCR + {provider_label}")

        try:
            text = ocr_module.extract_text(str(src))
        except ValueError as e:
            print(f"[CHYBA] {e}", file=sys.stderr)
            return 1

        try:
            xml = isdoc_module.extract_to_isdoc(text, provider=provider)
        except Exception as e:
            print(f"[CHYBA] {provider_label} API selhalo: {e}", file=sys.stderr)
            return 1

        method = f"OCR + {provider_label}"

    # Validate XML
    try:
        doc = isdoc_module.isdoc_to_extracted(xml)
    except ValueError as e:
        print(f"[CHYBA] Neplatné ISDOC XML: {e}", file=sys.stderr)
        return 1

    # Determine output path
    out = Path(output_path) if output_path else src.with_suffix(".xml")

    # Paragon limit (§ 30 ZDPH): zjednodušený daňový doklad max 10 000 Kč
    if doc.document_type == DocumentType.uctenka:
        total = doc.amount_total or sum(
            abs(li.unit_price * li.quantity) * (1 + li.vat_rate / 100)
            for li in doc.lines
        )
        if total > 10_000:
            print(f"  POZOR: Paragon nad limit 10 000 Kč ({total:.0f} Kč). "
                  f"Dle § 30 ZDPH musí obsahovat údaje o odběrateli jako řádný daňový doklad.")

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
    parser.add_argument("--provider", choices=["claude", "openai"],
                        help="LLM provider (výchozí: z LLM_PROVIDER v .env)")
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
            provider=args.provider,
        )
        errors += rc

    if errors:
        print(f"\n{errors} soubor(ů) skončilo chybou.")
        sys.exit(1)


if __name__ == "__main__":
    main()
