"""行業分類：依 industries.json 的規則，比對標案名稱、標的分類、機關名稱。

規則格式（之後會換成你提供的行業資料庫）：
  {"行業名稱": {"keywords": [...], "cpc": ["CPC 碼前綴", ...], "exclude": [...]}}
一個標案可以同時屬於多個行業；都沒命中就歸「未分類」。
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))


def load_rules(path=os.path.join(HERE, "industries.json")):
    return json.load(open(path, encoding="utf-8"))


def classify(t, rules):
    text = " ".join(filter(None, [t.get("title"), t.get("category"), t.get("unit_name")]))
    cpc = re.findall(r"\d{3,}", t.get("category") or "")
    hits = []
    for name, r in rules.items():
        if any(x in text for x in r.get("exclude", [])):
            continue
        if any(k in text for k in r.get("keywords", [])) or \
           any(c.startswith(p) for c in cpc for p in r.get("cpc", [])):
            hits.append(name)
    return hits or ["未分類"]
