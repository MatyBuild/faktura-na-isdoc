# Contributing

## Prerekvizity

- Python 3.11+
- pip / venv
- Git

## Nastavení vývojového prostředí

```bash
git clone https://github.com/MatyBuild/faktura-na-isdoc.git
cd faktura-na-isdoc

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
pip install pytest pytest-cov   # testovací závislosti

cp .env.example .env
# Doplň ANTHROPIC_API_KEY nebo OPENAI_API_KEY do .env
```

## Proměnné prostředí

<!-- AUTO-GENERATED from .env.example -->
| Proměnná | Povinná | Popis |
|----------|---------|-------|
| `LLM_PROVIDER` | Ne | `claude` (výchozí) nebo `openai` |
| `ANTHROPIC_API_KEY` | Pro `claude` | Anthropic API klíč |
| `OPENAI_API_KEY` | Pro `openai` | OpenAI API klíč |
| `OPENAI_MODEL` | Ne | Model OpenAI, výchozí `gpt-4o` |
<!-- END AUTO-GENERATED -->

## Spuštění testů

```bash
# Všechny testy
pytest tests/ -v

# S měřením pokrytí
pytest tests/ --cov --cov-report=term-missing

# Konkrétní soubor
pytest tests/test_isdoc_builder.py -v
```

Testy nevyžadují skutečné API klíče — LLM volání jsou mockována.

## Struktura testů

<!-- AUTO-GENERATED from tests/ -->
| Soubor | Co testuje |
|--------|-----------|
| `tests/test_models.py` | Datové modely, enum hodnoty, defaults |
| `tests/test_pdf_extractor.py` | Regex parsery (částky, data, IČO, typy dokladů) |
| `tests/test_isdoc_builder.py` | Sestavení ISDOC XML, multi-VAT, dobropis/vrubopis |
| `tests/test_isdoc_parsing.py` | Parsování ISDOC XML → ExtractedDocument |
| `tests/test_providers.py` | Dispatch Claude/OpenAI, mock API volání |
<!-- END AUTO-GENERATED -->

## Přidání nového testu

1. Zvol správný soubor podle oblasti (viz tabulka výše)
2. Vytvoř třídu nebo funkci s prefixem `Test` / `test_`
3. LLM volání vždy mockuj přes `unittest.mock.patch`
4. Spusť `pytest tests/ --cov --cov-fail-under=80`

## Architektura (stručně)

```
pdf_extractor.py   → kódová extrakce z PDF (bez API)
isdoc_builder.py   → ExtractionResult → ISDOC XML (bez API)
ocr.py             → text z PDF/obrázku (PyMuPDF / PaddleOCR)
isdoc.py           → OCR text → LLM → ISDOC XML → ExtractedDocument
convert.py         → CLI, orchestruje celý pipeline
models.py          → sdílené datové typy
config.py          → env proměnné, fail-fast validace
```

## Pipeline pro nový typ dokladu

1. Přidej hodnotu do `DocumentType` v `models.py`
2. Přidej detekci do `_extract_document_type()` v `pdf_extractor.py`
3. Přidej ISDOC kód do `_DOCTYPE_CODE` v `isdoc_builder.py`
4. Přidej mapování do `_ISDOC_DOCTYPE` v `isdoc.py`
5. Napiš testy do příslušných testovacích souborů

## Styl kódu

- Immutabilita: nevracuj mutovaný objekt, vrať novou kopii
- Funkce < 50 řádků, soubory < 800 řádků
- Bez hardcoded hodnot — konstanty nebo config
- Lazy import pro těžké závislosti (`fitz`, `paddleocr`) uvnitř funkcí

## PR checklist

- [ ] Testy projdou (`pytest tests/`)
- [ ] Pokrytí ≥ 80 % (`pytest --cov --cov-fail-under=80`)
- [ ] Žádné hardcoded API klíče
- [ ] README.md aktualizován (nové typy dokladů, přepínače, env proměnné)
