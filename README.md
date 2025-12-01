# 🏈 query-scores  
Fetch NFL scores from **Footballdb.com** via CLI or Python library.

This tool provides:

- A **CLI command**: `nflscores`
- A **Python library** for programmatic access  
- Support for:
  - Specific **season/year/week**
  - Filtering by **team**
  - JSON output
  - **CSV export**
  - Homepage “current week” scrape  
- Modern Python packaging (`pyproject.toml`)

---

## 📦 Installation

### 🔹 Using uv (recommended)

Install globally as a uv tool:

```bash
uv tool install .
```

Or install from anywhere:

```bash
uv tool install /path/to/query-scores
```

After install:

```bash
nflscores --help
```

Uninstall:

```bash
uv tool uninstall query-scores
```

---

### 🔹 Editable install for development

```bash
pip install -e .
```

---

## 🚀 CLI Usage

```bash
nflscores --help
```

Examples:

```bash
nflscores --use-homepage
nflscores -y 2025 -w 13 --team Miami
nflscores -y 2025 -w 13 --csv week13.csv
```

---

## 🧩 Library Usage

```python
from query_scores import fetch_live_scores, build_scores_url

url = build_scores_url(year=2025, week=13)
games = fetch_live_scores(url)
```

---

## 📁 Project Structure

```
query-scores/
├─ pyproject.toml
├─ README.md
└─ src/
   └─ query_scores/
      ├─ __init__.py
      └─ fetch_nfl_scores.py
```

---

## 📝 License

MIT License © Jay Torres
