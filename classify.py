"""行業分類：依 industries.json 的規則，比對標案名稱、標的分類、機關名稱。

規則格式（每個行業）：
  keywords  命中任一即可；用「A+B」表示 A 和 B 都要出現
  cpc       標的分類 CPC 碼前綴
  units     若有設定，機關名稱必須含其中之一（例如只算國防單位）
  exclude   出現任一就不算這個行業
一個標案可以同時屬於多個行業；都沒命中就歸「未分類」（網頁上顯示為「其他」）。
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))


def load_rules(path=os.path.join(HERE, "industries.json")):
    return json.load(open(path, encoding="utf-8"))


def _hit(k, text):
    return all(p in text for p in k.split("+"))


def classify(t, rules):
    title = t.get("title") or ""
    unit = t.get("unit_name") or ""
    text = " ".join(filter(None, [title, t.get("category"), unit]))
    cpc = re.findall(r"\d{3,}", t.get("category") or "")
    hits = []
    for name, r in rules.items():
        if any(_hit(x, text) for x in r.get("exclude", [])):
            continue
        if r.get("units") and not any(u in unit for u in r["units"]):
            continue
        if any(_hit(k, text) for k in r.get("keywords", [])) or \
           any(c.startswith(p) for c in cpc for p in r.get("cpc", [])):
            hits.append(name)
    return hits or ["未分類"]
