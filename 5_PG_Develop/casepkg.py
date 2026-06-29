"""casepkg 模組實作(/pg 產物)。

把一組「選定案例」(record 摘要 + sidecar 判讀 dict + model Detection 清單)
扁平化成一張每案一列的 CSV,與一份保留巢狀 detections 的 JSON case list,
並把兩者寫進輸出目錄。

僅用 Python 標準庫(csv / json / io / os);**不 import** sidecar / yolo / tagging。
契約見 3_Architect_Design/11_casepkg.md;驗收見 4_PM_Feedback/test_casepkg.py。
"""
import csv
import io
import json
import os

# §3.2 釘死的 11 欄順序(CSV 表頭 / row dict 鍵順序)。
_FIELDS = [
    "name", "path", "status", "verdict", "tags", "bookmarked",
    "n_rois", "n_det", "max_conf", "classes", "comment",
]


def _max_conf(detections):
    """§3.2 max_conf 規則:空 → 0.0;否則 max(float(conf)),不四捨五入。"""
    if not detections:
        return 0.0
    return max(float(d["conf"]) for d in detections)


def _classes_list(detections):
    """§3.2 classes 規則:取每筆 cls,去重、保留首見順序,回 list[str]。"""
    seen = set()
    result = []
    for d in detections:
        cls = d["cls"]
        if cls not in seen:
            seen.add(cls)
            result.append(cls)
    return result


def build_rows(items):
    """每個 item → 一個扁平 row dict;鍵順序 == §3.2 的 11 欄(dict 保序即契約)。"""
    rows = []
    for item in items:
        sidecar = item.get("sidecar", {})
        detections = item.get("detections", [])
        row = {
            "name": item.get("name", ""),
            "path": item.get("path", ""),
            "status": sidecar.get("review_status", "none"),
            "verdict": sidecar.get("verdict", "unset"),
            "tags": ";".join(sidecar.get("tags", [])),
            "bookmarked": bool(sidecar.get("bookmarked", False)),
            "n_rois": len(sidecar.get("rois", [])),
            "n_det": len(detections),
            "max_conf": _max_conf(detections),
            "classes": ",".join(_classes_list(detections)),
            "comment": sidecar.get("comment", ""),
        }
        rows.append(row)
    return rows


def to_csv(rows):
    """rows(build_rows 的輸出)→ CSV 字串;表頭 + 資料列;行尾 \\r\\n;QUOTE_MINIMAL。

    空 rows 仍輸出僅表頭一行(含結尾 \\r\\n)。
    """
    buf = io.StringIO()
    # csv 模組預設 lineterminator="\r\n"、quoting=QUOTE_MINIMAL,即 §3.3 契約。
    writer = csv.DictWriter(buf, fieldnames=_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def build_case_list(items):
    """每個 item → 一個巢狀 case dict(保留 detections 結構);鍵順序見 §3.4。

    純函式、不就地改輸入:bbox / tags 皆以 list(...) 複製。
    """
    case_list = []
    for item in items:
        sidecar = item.get("sidecar", {})
        detections = item.get("detections", [])
        case = {
            "name": item.get("name", ""),
            "path": item.get("path", ""),
            "review": {
                "status": sidecar.get("review_status", "none"),
                "verdict": sidecar.get("verdict", "unset"),
                "tags": list(sidecar.get("tags", [])),
                "bookmarked": bool(sidecar.get("bookmarked", False)),
                "comment": sidecar.get("comment", ""),
                "n_rois": len(sidecar.get("rois", [])),
            },
            "detections": [
                {"bbox": list(d["bbox"]), "cls": d["cls"], "conf": float(d["conf"])}
                for d in detections
            ],
            "summary": {
                "n_det": len(detections),
                "max_conf": _max_conf(detections),
                "classes": _classes_list(detections),
            },
        }
        case_list.append(case)
    return case_list


def to_json(items):
    """== json.dumps(build_case_list(items), ensure_ascii=False, indent=2)。"""
    return json.dumps(build_case_list(items), ensure_ascii=False, indent=2)


def write_package(out_dir, items):
    """在 out_dir 寫 case_list.csv + case_list.json,回 {"csv": ..., "json": ...}。

    out_dir 不存在則建立;覆寫語義(非附加);CSV 以 newline="" 開檔避免雙重換行。
    """
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "case_list.csv")
    json_path = os.path.join(out_dir, "case_list.json")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        f.write(to_csv(build_rows(items)))
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(to_json(items))
    return {"csv": csv_path, "json": json_path}
