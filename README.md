# Faktura na ISDOC

Nástroj pro převod faktur (PDF, JPG, PNG) do formátu **ISDOC 6.0.2** – standardního elektronického formátu účetních dokladů v ČR.

## Co to umí

- Převede faktury, dobropisy, vrubopisy, zálohové faktury a účtenky do ISDOC 6.0.2 XML
- Extrahuje: dodavatel, IČO, DIČ, adresa, číslo dokladu, datum, splatnost, DPH (více sazeb), položky
- **Dva způsoby extrakce** podle kvality dokladu:
  - **Kódová extrakce** (PyMuPDF + regex) – pro strojová PDF, žádné API volání
  - **OCR + LLM** – pro naskenované dokumenty a obrázky (1 API volání, Claude nebo OpenAI)
- Podpora zahraničních faktur (samovyměření DPH, měna EUR/USD/…)
- Validace paragonu: upozornění při překročení limitu 10 000 Kč (§ 30 ZDPH)
- Volitelný výstup jako JSON

## Instalace

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Zkopíruj `.env.example` → `.env` a doplň přístupové údaje:

```bash
cp .env.example .env
```

<!-- AUTO-GENERATED from .env.example -->
## Proměnné prostředí

| Proměnná | Povinná | Popis | Výchozí / Příklad |
|----------|---------|-------|-------------------|
| `LLM_PROVIDER` | Ne | LLM provider pro OCR cestu | `claude` nebo `openai` |
| `ANTHROPIC_API_KEY` | Pro `claude` | API klíč Anthropic Claude | `sk-ant-...` |
| `OPENAI_API_KEY` | Pro `openai` | API klíč OpenAI | `sk-...` |
| `OPENAI_MODEL` | Ne | Model OpenAI | `gpt-4o` (výchozí), `gpt-4o-mini` |
<!-- END AUTO-GENERATED -->

> API klíč je potřeba **jen pro naskenované doklady**. Pro strojová PDF (confidence ≥ 0.85) se LLM nevolá.

## Použití

### Základní převod

```bash
python convert.py faktura.pdf
```

Vytvoří `faktura.xml` ve stejné složce.

### Více souborů najednou

```bash
python convert.py *.pdf
```

### Vlastní výstupní soubor

```bash
python convert.py faktura.pdf --output /cesta/vystup.xml
```

### Výstup jako JSON

```bash
python convert.py faktura.pdf --json
```

### Volba LLM providera

```bash
# Použít OpenAI místo Claude (vyžaduje OPENAI_API_KEY v .env)
python convert.py faktura.pdf --provider openai

# Použít Claude (výchozí)
python convert.py faktura.pdf --provider claude
```

### Podrobný výpis

```bash
python convert.py faktura.pdf --verbose
```

```
Zpracovávám: faktura.pdf
  → kódová extrakce (confidence 0.95)
  ✓ ISDOC XML uložen: faktura.xml  [kód (confidence 0.95)]
     Dodavatel:  Acme s.r.o.
     IČO:        12345678
     Číslo dok.: FV2024001
     Vystaveno:  2024-03-15
     Typ:        faktura
     Položky:    3
```

<!-- AUTO-GENERATED from convert.py -->
## CLI – přehled přepínačů

| Přepínač | Popis |
|----------|-------|
| `soubory...` | Jeden nebo více souborů PDF/JPG/PNG |
| `-o`, `--output` | Výstupní soubor (pouze pro 1 vstup) |
| `--json` | Uložit jako JSON místo ISDOC XML |
| `--provider claude\|openai` | LLM provider (přepisuje `LLM_PROVIDER` z .env) |
| `-v`, `--verbose` | Podrobný výpis (dodavatel, IČO, položky…) |
<!-- END AUTO-GENERATED -->

## Pipeline

```
Vstupní soubor (PDF / JPG / PNG)
  └─► pdf_extractor.try_extract()       ← kódová extrakce, PyMuPDF + regex
        confidence ≥ 0.85?
          Ano → isdoc_builder.build_isdoc()   ← žádné API volání
          Ne  → ocr.extract_text()
                  └─► isdoc.extract_to_isdoc(provider)
                        ├─ claude  → Anthropic Claude Sonnet
                        └─ openai  → OpenAI GPT-4o
        └─► isdoc.isdoc_to_extracted()  ← ISDOC XML → ExtractedDocument
        └─► výstup .xml nebo .json
```

## Struktura projektu

| Soubor | Popis |
|--------|-------|
| `convert.py` | CLI vstupní bod |
| `pdf_extractor.py` | Kódová extrakce polí z PDF (regex, PyMuPDF tabulky) |
| `isdoc_builder.py` | Sestavení ISDOC XML z `ExtractionResult` (bez API) |
| `isdoc.py` | LLM pipeline: OCR text → ISDOC XML → `ExtractedDocument` |
| `ocr.py` | OCR wrapper (PyMuPDF pro digitální PDF, PaddleOCR pro skeny) |
| `models.py` | Datové modely (`ExtractedDocument`, `LineItem`, …) |
| `config.py` | Načítání a validace proměnných prostředí |
| `tests/` | 110 unit testů (pytest) |
| `.github/workflows/ci.yml` | GitHub Actions CI (Python 3.11 + 3.12) |

## Typy dokladů

<!-- AUTO-GENERATED from models.py DocumentType + isdoc.py _ISDOC_DOCTYPE -->
| `document_type` | ISDOC kód | Popis |
|-----------------|-----------|-------|
| `faktura` | 1 | Daňový doklad (přijatá faktura) |
| `zaloha` | 2 | Zálohový daňový doklad |
| `dobropis` | 3 | Opravný daňový doklad – snížení (záporné částky) |
| `vrubopis` | 3 | Opravný daňový doklad – zvýšení (kladné částky) |
| `uctenka` | 5 | Zjednodušený daňový doklad (paragon, max 10 000 Kč) |
| `unknown` | 1 | Nerozpoznaný typ, zpracován jako faktura |
<!-- END AUTO-GENERATED -->

## Výstupní formáty

### ISDOC XML (výchozí)

Validní ISDOC 6.0.2 XML kompatibilní se standardem [mv.gov.cz/isdoc](https://mv.gov.cz/isdoc/clanek/aktualni-verze.aspx). Lze importovat do účetních systémů (Pohoda, Money, ABRA, Fakturoid…).

### JSON

Strukturovaná data vhodná pro další zpracování:

```json
{
  "document_type": "faktura",
  "supplier_name": "Acme s.r.o.",
  "registration_no": "12345678",
  "vat_no": "CZ12345678",
  "issued_on": "2024-03-15",
  "due_on": "2024-03-29",
  "currency": "CZK",
  "reverse_charge": false,
  "amount_total": 1210.0,
  "lines": [
    { "name": "Vývojové práce", "quantity": 10.0, "unit_price": 1500.0, "vat_rate": 21.0 }
  ]
}
```

## Poznámky

- Pro naskenované dokumenty je potřeba PaddleOCR (stahuje modely ~300 MB při prvním spuštění)
- Zahraniční faktury (ne-CZ dodavatel) → `reverse_charge: true`, sazba DPH vynucena na 21 %
- Dobropisy: záporné hodnoty položek; vrubopisy: kladné hodnoty
- Confidence threshold 0.85 (IČO 30 %, název 20 %, celková částka 25 %, datum 15 %, číslo dok. 10 %)
- Faktury s více sazbami DPH (0 %/12 %/21 %) generují samostatný `TaxSubTotal` pro každou sazbu
