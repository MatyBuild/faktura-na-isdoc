# Faktura na ISDOC

Nástroj pro převod faktur (PDF, JPG, PNG) do formátu **ISDOC 6.0.2** – standardního elektronického formátu účetních dokladů v ČR.

## Co to umí

- Převede faktury, dobropisy a účtenky do ISDOC 6.0.2 XML
- Extrahuje: dodavatel, IČO, DIČ, adresa, číslo dokladu, datum, splatnost, DPH, položky
- **Dva způsoby extrakce** podle kvality dokladu:
  - **Kódová extrakce** (PyMuPDF) – pro strojová PDF, žádné API volání
  - **OCR + Claude** – pro naskenované dokumenty a obrázky (1 API volání)
- Podpora zahraničních faktur (samovyměření DPH, měna EUR/USD/…)
- Volitelný výstup jako JSON

## Instalace

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Zkopíruj `.env.example` → `.env` a doplň API klíč:

```bash
cp .env.example .env
```

```
ANTHROPIC_API_KEY=sk-ant-...
```

> API klíč je potřeba jen pro naskenované doklady. Pro strojová PDF (confidence ≥ 0.85) se Claude nevolá.

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

Vytvoří `faktura.json` se strukturovanými daty (ExtractedDocument).

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

## Pipeline

```
Vstupní soubor
  └─► pdf_extractor.try_extract()     ← čistě kódová extrakce (PyMuPDF)
        confidence ≥ 0.85?
          Ano → isdoc_builder.build_isdoc()  ← bez API volání
          Ne  → ocr.extract_text()
                  └─► isdoc.extract_to_isdoc()  ← 1× Claude API volání
        └─► isdoc.isdoc_to_extracted()  ← XML → ExtractedDocument
        └─► výstup .xml nebo .json
```

## Struktura projektu

| Soubor | Popis |
|--------|-------|
| `convert.py` | CLI vstupní bod |
| `pdf_extractor.py` | Kódová extrakce polí z PDF (regex, PyMuPDF) |
| `isdoc_builder.py` | Sestavení ISDOC XML z `ExtractionResult` |
| `isdoc.py` | Claude pipeline: OCR text → ISDOC XML → `ExtractedDocument` |
| `ocr.py` | OCR wrapper (PyMuPDF pro digitální PDF, PaddleOCR pro skeny) |
| `models.py` | Datové modely (`ExtractedDocument`, `LineItem`, …) |
| `config.py` | Načítání proměnných prostředí |

## Výstupní formáty

### ISDOC XML (výchozí)

Validní ISDOC 6.0.2 XML kompatibilní se standardem [mv.gov.cz/isdoc](https://mv.gov.cz/isdoc/clanek/aktualni-verze.aspx). Lze importovat do účetních systémů (Pohoda, Money, ABRA, Fakturoid…).

### JSON

Strukturovaná data vhodná pro další zpracování nebo import do vlastního systému:

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
  "lines": [
    {
      "name": "Vývojové práce",
      "quantity": 10.0,
      "unit_price": 1500.0,
      "vat_rate": 21.0
    }
  ]
}
```

## Typy dokladů

| DocumentType | ISDOC kód | Popis |
|---|---|---|
| `faktura` | 1 | Daňový doklad |
| `dobropis` | 3 | Opravný daňový doklad |
| `uctenka` | 5 | Zjednodušený daňový doklad (paragon) |

## Poznámky

- Pro naskenované dokumenty je potřeba PaddleOCR (stahuje modely ~300 MB při prvním spuštění)
- Zahraniční faktury (ne-CZ dodavatel) automaticky nastaví `reverse_charge: true` a sazbu DPH 21 %
- Dobropisy mají záporné hodnoty položek
- Threshold pro kódovou extrakci je 0.85 (skóre z: IČO 30 %, název 20 %, celková částka 25 %, datum 15 %, číslo dokladu 10 %)
