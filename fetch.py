#!/usr/bin/env python3
"""抓取政府電子採購網標案公告（透過 g0v 標案資料 API），分類後輸出 data/tenders.json。

用法：
  python fetch.py               # 抓最近 3 天
  python fetch.py --days 14     # 抓最近 14 天
  python fetch.py --date 20261102

資料來源：中華民國政府電子採購網 https://web.pcc.gov.tw/
經由 g0v 標案資料 API https://pcc-api.openfun.app/（請依其授權註明出處）
"""
import argparse, datetime as dt, json, os, sys, time, urllib.request, urllib.parse

from classify import load_rules, classify

API = os.environ.get("PCC_API", "https://pcc-api.openfun.app/api")
TOKEN = os.environ.get("OPENFUN_TOKEN")  # 選填：歐噴 token，可放寬限流
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "tenders.json")


def get(path, **params):
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "pcc-tracker/0.1"})
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    for i in range(4):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except Exception as e:  # 網路不穩或被限流（429）時等一下再試
            if i == 3:
                raise
            wait = 10 * (i + 1) if getattr(e, "code", None) == 429 else 2 ** (i + 1)
            time.sleep(wait)


def normalize(rec):
    b = rec.get("brief") or {}
    return {
        "id": f"{rec.get('unit_id')}|{rec.get('job_number')}|{rec.get('filename')}",
        "date": str(rec.get("date") or ""),
        "type": b.get("type"),            # 公告類型：公開招標公告、決標公告…
        "title": b.get("title"),
        "category": b.get("category"),    # 標的分類（工程/財物/勞務 + CPC 碼）
        "unit_id": rec.get("unit_id"),
        "unit_name": rec.get("unit_name"),
        "job_number": rec.get("job_number"),
        "companies": (b.get("companies") or {}).get("names", []),
        "url": None,                      # 原始公告連結在補抓詳細資料時取得（pcc_url）
        "api_url": rec.get("tender_api_url"),
    }


# 對照「標案記錄」表格的欄位：用關鍵字比對 API 詳細資料的欄位名稱（欄位名稱是「區塊:欄位」形式）
DETAIL_FIELDS = {
    "deadline": ["截止投標"],
    "method": ["招標方式"],
    "contact": ["聯絡人"],
    "phone": ["聯絡電話"],
    "fax": ["傳真"],
    "email": ["電子郵件"],
    "bond": ["押標金額度", "押標金"],
    "budget": ["預算金額"],
    "location": ["履約地點"],
    "doc_fee": ["機關文件費", "文件費", "領標費", "標書費"],   # 標書（招標文件）費用
    "e_tender": ["是否提供電子領標"],
}


def pick(detail, needles):
    for n in needles:
        for k, v in detail.items():
            if n in k.split(":")[-1] and v not in (None, "", []):
                return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return None


def roc_date(v):
    """民國日期「115/11/20 17:00」→「20261120 17:00」，方便排序與判斷是否快截止。"""
    import re
    m = re.match(r"\s*(\d{2,3})/(\d{1,2})/(\d{1,2})(.*)", str(v or ""))
    if not m:
        return v
    y, mo, d, rest = m.groups()
    return f"{int(y) + 1911}{int(mo):02d}{int(d):02d}{rest}"


def doc_buy(t):
    """標書是否需要購買：有文件費且大於 0 → 需購買；文件費 0 → 免費；不明 → None。"""
    fee = t.get("doc_fee")
    if fee is None:
        return None
    digits = "".join(ch for ch in str(fee) if ch.isdigit())
    if digits and int(digits) > 0:
        return f"需購買 NT${int(digits):,}"
    return "免費"


DEADLINE = [float("inf")]


def enrich(t):
    """只對有命中關注行業的案子抓詳細資料，避免一天上千次呼叫。超過時間預算就留到下次。"""
    if time.time() > DEADLINE[0]:
        return
    try:
        res = get("tender", unit_id=t["unit_id"], job_number=t["job_number"])
    except Exception as e:
        print(f"  詳細資料失敗 {t['job_number']}: {e}", file=sys.stderr)
        return
    recs = [r for r in res.get("records") or [] if r.get("filename") == t["id"].split("|")[-1]] or (res.get("records") or [])[-1:]
    if not recs:
        return
    detail = recs[-1].get("detail") or {}
    for f, needles in DETAIL_FIELDS.items():
        t[f] = pick(detail, needles)
    t["doc_buy"] = doc_buy(t)
    t["deadline"] = roc_date(t.get("deadline"))
    if detail.get("url"):
        t["pcc_url"] = detail["url"]
    time.sleep(0.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--date", help="YYYYMMDD，只抓這一天")
    ap.add_argument("--max-detail", type=int, default=150, help="每次最多補抓幾筆詳細資料")
    ap.add_argument("--time-budget", type=int, default=1200, help="補抓詳細資料最多花幾秒")
    ap.add_argument("--keep-days", type=int, default=90, help="網頁保留幾天的資料")
    a = ap.parse_args()

    today = dt.date.today()
    dates = [a.date] if a.date else [(today - dt.timedelta(d)).strftime("%Y%m%d") for d in range(a.days)]

    existing = {}
    if os.path.exists(OUT):
        for t in json.load(open(OUT, encoding="utf-8"))["tenders"]:
            existing[t["id"]] = t

    rules = load_rules()
    todo = []
    for d in dates:
        try:
            res = get("listbydate", date=d)
        except Exception as e:             # 某天 API 出錯就跳過，不要讓整次更新失敗
            print(f"{d}: 讀取失敗，略過（{e}）", file=sys.stderr)
            continue
        recs = res.get("records") or []
        print(f"{d}: {len(recs)} 筆", file=sys.stderr)
        for r in recs:
            t = normalize(r)
            t["industries"] = classify(t, rules)
            old = existing.get(t["id"])
            if old and "doc_fee" in old:           # 已抓過詳細資料就沿用
                t.update({k: old.get(k) for k in [*DETAIL_FIELDS, "pcc_url", "doc_buy"]})
            elif t["industries"] != ["未分類"]:
                todo.append(t)
            existing[t["id"]] = t

    # 補抓詳細資料：最新的優先，每次最多 max_detail 筆，2 條連線並行
    todo.sort(key=lambda t: ("決標" not in (t["type"] or ""), t["date"] or ""), reverse=True)  # 招標公告優先
    todo = todo[:a.max_detail]
    print(f"補抓詳細資料 {len(todo)} 筆", file=sys.stderr)
    DEADLINE[0] = time.time() + a.time_budget
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(2) as ex:
        list(ex.map(enrich, todo))

    for t in existing.values():               # 規則改過時，舊資料也一起重新分類
        t["industries"] = classify(t, rules)

    cutoff = (today - dt.timedelta(a.keep_days)).strftime("%Y%m%d")
    tenders = sorted((t for t in existing.values() if (t["date"] or "") >= cutoff),
                     key=lambda t: (t["date"] or "", t["title"] or ""), reverse=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"updated_at": dt.datetime.now().isoformat(timespec="seconds"),
               "source": "政府電子採購網（經 g0v 標案資料 API）",
               "tenders": tenders}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"寫出 {len(tenders)} 筆 → {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
