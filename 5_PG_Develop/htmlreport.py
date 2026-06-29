"""htmlreport 模組實作(PG / U-Net 上採樣)。

把一批「選定案例」(record 摘要 + sidecar 判讀 dict + model Detection 清單)
渲染成「一份自含(無外部 CSS/JS/圖片相依)、可直接以瀏覽器開啟/列印的 HTML
報告」,並可薄寫成 UTF-8 .html 檔。

依 3_Architect_Design/16_htmlreport.md 之契約實作。只用 Python 標準庫
(html / os);**不 import** casepkg / sidecar / yolo / tagging —— 扁平化規則
與「已審」判定逐字自含於本模組,值與上游一致。

對外三個函式(簽名為硬契約):
    escape(text) -> str
    build_html(items, title="CV Review Report") -> str
    write_report(out_path, items, title="CV Review Report") -> str

純函式 escape / build_html 無副作用、不就地改輸入;唯一有 I/O 者為
write_report(以 UTF-8 寫單一檔)。
"""

import html
from decimal import Decimal, ROUND_HALF_UP

__all__ = ["escape", "build_html", "write_report"]


# --- 缺鍵預設(視同值;與 casepkg §3.1 同值,自含不 import) -----------------
_DEFAULT_VERDICT = "unset"
_DEFAULT_STATUS = "none"

# 表頭 7 欄固定字面(不經 item 資料,故不逸出)。
_HEADERS = ["Name", "Verdict", "Tags", "Status", "Detections", "Max Conf", "Comment"]

# 量化目標:小數第 3 位。
_Q3 = Decimal("0.001")


def _fmt_conf(x) -> str:
    """把 conf 數值呈現為「四捨五入(round-half-up)至小數第 3 位、固定 3 位小數」。

    設計 §3.4 的釘死意圖是「四捨五入至小數第 3 位」並給定逐字範例
    0.8765 → "0.877"(同 4_PM_Feedback AC29 斷言)。直接用 f"{x:.3f}" 會在
    二進位浮點上以 round-half-to-even 求值,使 0.8765(實際存為 0.876499…)
    得 "0.876",違反設計自己的範例。故對「十進位字面值」做 ROUND_HALF_UP:
    先 Decimal(str(x))(取使用者所寫的十進位字面),再 quantize 至 0.001。
    對 0.5/0.9/1/0.0 等與 f"{x:.3f}" 結果一致,僅在 .xxx5 邊界上忠於「四捨五入」。
    """
    return str(Decimal(str(float(x))).quantize(_Q3, rounding=ROUND_HALF_UP))

# 內聯 CSS(極簡、列印可讀;無外部資源)。釘死只要求存在 <style>...</style>
# 且不引外部,確切內容不入 AC。
_STYLE = (
    "body{font-family:sans-serif;margin:1.5em;color:#222}"
    "h1{font-size:1.4em}"
    "table{border-collapse:collapse;width:100%;margin-top:1em}"
    "th,td{border:1px solid #999;padding:4px 8px;text-align:left;"
    "vertical-align:top;font-size:0.9em}"
    "th{background:#eee}"
    ".summary{margin:0.5em 0}"
)


def escape(text) -> str:
    """對任意輸入先 str(text),再做 HTML 逸出。

    釘死等價 html.escape(str(text), quote=True):
        & → &amp;   < → &lt;   > → &gt;   " → &quot;   ' → &#x27;
    其餘字元(含中文、逗號、分號、空白、數字)原樣保留。
    """
    return html.escape(str(text), quote=True)


def _reviewed(sidecar: dict) -> bool:
    """已審判定(逐字自含,與 tagging.is_reviewed 同義,但不 import)。

    reviewed := (verdict != "unset") or (review_status == "done")
    """
    return (
        sidecar.get("verdict", _DEFAULT_VERDICT) != _DEFAULT_VERDICT
        or sidecar.get("review_status", _DEFAULT_STATUS) == "done"
    )


def _row_cells(item: dict) -> list:
    """把一個 item 扁平化成 7 個「未逸出」的儲存格文字(原序對齊表頭)。"""
    sidecar = item.get("sidecar", {})
    detections = item.get("detections", [])

    name = item.get("name", "")
    verdict = sidecar.get("verdict", _DEFAULT_VERDICT)
    tags = sidecar.get("tags", [])
    tags_text = "; ".join(tags)                      # 分號 + 空格(人類可讀)
    status = sidecar.get("review_status", _DEFAULT_STATUS)
    n_det = len(detections)
    if n_det == 0:
        max_conf = 0.0
    else:
        max_conf = max(float(d["conf"]) for d in detections)
    max_conf_text = _fmt_conf(max_conf)              # 固定 3 位小數(四捨五入 half-up)
    comment = sidecar.get("comment", "")

    return [name, verdict, tags_text, status, str(n_det), max_conf_text, comment]


def build_html(items: list, title: str = "CV Review Report") -> str:
    """回完整 HTML 字串(以 "<!DOCTYPE html>" 開頭、以 "</html>" 結尾)。

    結構:<head>(meta/title/style) → <body>(h1 → 摘要 → table)。
    純函式:不就地改 items / sidecar / detections / tags。輸出不含外部資源
    參照,且一律使用 \\n(不用 \\r\\n)以利 write_report round-trip 逐字成立。
    """
    safe_title = escape(title)

    total = len(items)
    reviewed = sum(1 for it in items if _reviewed(it.get("sidecar", {})))

    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="zh-Hant">')
    parts.append("<head>")
    parts.append('<meta charset="utf-8">')
    parts.append(f"<title>{safe_title}</title>")
    parts.append(f"<style>{_STYLE}</style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append(f"<h1>{safe_title}</h1>")
    parts.append(f'<p class="summary">總案數:{total}　已審數:{reviewed}</p>')

    parts.append("<table>")
    # 表頭列(固定字面,不逸出)。
    header_cells = "".join(f"<th>{h}</th>" for h in _HEADERS)
    parts.append(f"<tr>{header_cells}</tr>")

    if total == 0:
        parts.append('<p class="summary">沒有可顯示的案例</p>')
    else:
        for item in items:
            cells = _row_cells(item)
            data_cells = "".join(f"<td>{escape(c)}</td>" for c in cells)
            parts.append(f"<tr>{data_cells}</tr>")

    parts.append("</table>")
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts)


def write_report(out_path, items: list, title: str = "CV Review Report") -> str:
    """把 build_html(items, title) 以 UTF-8 寫進 out_path,回傳 str(out_path)。

    覆寫語義:同 out_path 重複呼叫完全覆寫(非附加)。不負責自動建父目錄。
    以 newline="" 開檔,確保讀回 == build_html 輸出(平台換行不轉換)。
    """
    html_str = build_html(items, title)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write(html_str)
    return str(out_path)
