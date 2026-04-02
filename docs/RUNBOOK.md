# Runbook

## Spuštění

```bash
cd faktura-na-isdoc
source .venv/bin/activate
python convert.py faktura.pdf
```

## Časté problémy

### `RuntimeError: LLM_PROVIDER=claude, ale ANTHROPIC_API_KEY není nastaven`

Chybí `.env` nebo není nastaven klíč. Zkopíruj `.env.example` → `.env` a doplň klíč:

```bash
cp .env.example .env
# Nastav ANTHROPIC_API_KEY nebo OPENAI_API_KEY podle zvoleného providera
```

### PaddleOCR při prvním spuštění trvá dlouho

PaddleOCR stahuje modely (~300 MB) do `~/.paddleocr/`. Jde o jednorázový download.

### `ModuleNotFoundError: No module named 'fitz'`

PyMuPDF není nainstalovaný:

```bash
pip install pymupdf>=1.24.0
```

### Výstupní XML nejde importovat do účetního systému

Zkontroluj, zda soubor začíná `<?xml version="1.0" encoding="UTF-8"?>` a namespace je `http://isdoc.cz/namespace/2013`. Pokud ne, Claude/OpenAI vrátil nevalidní odpověď — zkus znovu nebo přepni provider.

### Nízká přesnost extrakce (špatně rozpoznaný dodavatel, IČO)

- Kódová extrakce: confidence skóre je pod 0.85 → dokument jde automaticky přes LLM
- LLM cesta: zkus `--provider openai` nebo `--provider claude` pro srovnání
- Naskenovaný dokument: kvalita skenu pod 200 DPI snižuje přesnost OCR

### Paragon hlásí varování o limitu 10 000 Kč

Dle § 30 ZDPH musí doklad nad 10 000 Kč obsahovat IČO/DIČ odběratele jako řádný daňový doklad, nikoli zjednodušený. Toto je varování, výstupní XML se stejně vygeneruje.

## Výměna LLM providera

```bash
# V .env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Nebo per-soubor přepnutím
python convert.py faktura.pdf --provider openai
```

Dostupné modely OpenAI: `gpt-4o` (výchozí, přesnější), `gpt-4o-mini` (levnější).

## Dávkové zpracování

```bash
# Zpracovat všechny PDF v adresáři
python convert.py faktury/*.pdf

# S podrobným výpisem
python convert.py faktury/*.pdf --verbose
```

## CI/CD

GitHub Actions běží automaticky při každém push na `main`. Pipeline:
1. Instalace závislostí (bez PaddleOCR a PyMuPDF — testy je nepotřebují)
2. `pytest tests/ -v` — 110 testů, žádná API volání
3. Kontrola pokrytí ≥ 80 %

Spuštění CI lokálně:
```bash
ANTHROPIC_API_KEY=sk-ant-test-dummy pytest tests/ --cov --cov-fail-under=80
```
