# 技術設計:`imageset`(Tier B,M1b)

> `/architect` 產物(module 粒度)。對齊 PRD `2_PO_PRD/01` M1 與 ROADMAP M1b。
> 同名三層:`3_Architect_Design/03_imageset.md` / `4_PM_Feedback/test_imageset.py` / `5_PG_Develop/imageset.py`。
> 本文件只定契約與驗收,**不含實作**。

---

## 1. 目的 (Purpose)
把一個資料夾變成「可自然排序、可重排(name/time/size)、可顯示進度 `i / n`、可記住每資料夾上次瀏覽位置(持久化)」的影像清單。

---

## 2. I/O 契約 (逐字採用,不可改簽名)

```python
def scan(folder, exts=(".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")) -> list[dict]:
    """掃描資料夾,回傳影像記錄清單。
    每筆記錄 = {"path": str, "name": str, "index": int, "mtime": float, "size": int}
    依檔名自然排序 (natural sort) 給 index;資料夾不存在 → NotADirectoryError。
    """

def sort_records(records, key="name") -> list:
    """回新 list 並重編 index;key in {"name", "time", "size"}。"""

def progress(index, total) -> str:
    """顯示 "i / n"(1-based);total<=0 → ValueError。"""

class Position:
    """記住每資料夾上次 index,以 json 狀態檔持久化。"""
    def __init__(self, state_path): ...
    def get(self, folder, default=0) -> int: ...
    def set(self, folder, index) -> None: ...   # set 立即持久化
```

### 2.1 資料結構:影像記錄 (record)
每筆為 `dict`,鍵與型別固定如下:

| 鍵 | 型別 | 語義 |
|----|------|------|
| `path`  | `str`   | 影像檔絕對路徑(`os.path.abspath`,正規化分隔字元) |
| `name`  | `str`   | 含副檔名的檔名(`os.path.basename`),例如 `img2.png` |
| `index` | `int`   | 在目前清單順序中的 0-based 位置(`scan` 用自然排序給,`sort_records` 重排後重編) |
| `mtime` | `float` | 檔案最後修改時間(`os.path.getmtime`,Unix epoch 秒) |
| `size`  | `int`   | 檔案位元組大小(`os.path.getsize`) |

### 2.2 排序定義(load-bearing,必須釘死)
- **自然排序 (natural sort)**:把檔名中連續數字當整數比較,其餘字元逐字比較;**大小寫不敏感**(以 `str.lower()` 正規化後比較),數字部分以整數值比較。
  - 期望:`["img1.png","img2.png","img10.png"]` 而**非** ASCII 字典序 `["img1.png","img10.png","img2.png"]`。
- `scan` 一律以「檔名自然排序」決定初始 `index`。
- `sort_records(records, key=...)`:
  - `key="name"` → 對 `name` 做自然排序(與 scan 一致)。
  - `key="time"` → 對 `mtime` 升冪 (`mtime` 小者在前);**tie-break 用 name 自然排序**(確保 deterministic)。
  - `key="size"` → 對 `size` 升冪 (`size` 小者在前);**tie-break 用 name 自然排序**。
  - 任何排序均**穩定且 deterministic**(相同輸入恆得相同輸出),回傳**新 list**,不可原地修改傳入的 `records`,且重新指派 `index` 為 0..n-1。

### 2.3 狀態檔 (state file) 格式
- `Position` 以單一 JSON 物件持久化:`{ "<folder_key>": <int_index>, ... }`。
- `folder_key`:資料夾路徑經正規化(`os.path.abspath` + 統一分隔字元)後的字串,使「同一資料夾不同寫法」對應同一筆。
- `set` **每次呼叫立即把整份狀態寫回 `state_path`**(寫入後檔案即為最新真值;不依賴 `__del__`/flush)。
- `state_path` 的父目錄不存在時由實作建立(`os.makedirs(..., exist_ok=True)`)。

---

## 3. 資料流 (Data Flow)

```
資料夾路徑 ──scan()──► [record, record, ...]   (依 name 自然排序, index 0..n-1)
                          │
                          ├──sort_records(key="time"|"size"|"name")──► 新 list (重排 + 重編 index)
                          │
            (目前 index, 總數) ──progress()──► "i / n"  (1-based 顯示字串)

Position(state_path) ── get(folder) ──► 上次 index (無紀錄→default)
                     └─ set(folder, index) ──► 立即寫 JSON 狀態檔(下次程序啟動仍讀得到)
```

- `scan` 是唯一的檔案系統「讀目錄」入口;只列出副檔名(case-insensitive)落在 `exts` 內的**檔案**(非子目錄)。
- `sort_records` / `progress` 為純函式,不碰 I/O。
- `Position` 是唯一「讀寫狀態檔」的元件;`scan` 產出的清單 + `Position.get` 的 index 共同決定 app 啟動時停在哪一張。

---

## 4. 邊界條件與錯誤處理

| 情境 | 期望行為 |
|------|----------|
| `scan` folder 不存在 | raise `NotADirectoryError` |
| `scan` folder 是一個檔案(非目錄) | raise `NotADirectoryError` |
| `scan` 空資料夾 / 無符合副檔名 | 回傳 `[]`(空 list,不報錯) |
| `scan` 副檔名大小寫 | case-insensitive:`A.PNG`、`b.Jpg` 皆視為影像 |
| `scan` 忽略子目錄 | 子目錄即使名為 `x.png` 也不納入(只收檔案) |
| `scan` 副檔名比對 | 以**完整副檔名**比對(`.tif`/`.tiff` 分別比對),非前綴 |
| `sort_records` 非法 key | `key` 不在 `{"name","time","size"}` → raise `ValueError` |
| `sort_records` 空 list | 回傳 `[]`(新物件) |
| `sort_records` 不可變性 | 不修改傳入 `records`(含其內 dict 的 `index`);回傳新 list |
| `progress` `total<=0` | raise `ValueError`(`total==0` 與負值皆是) |
| `progress` 1-based | `progress(0, 5) == "1 / 5"`;`progress(4, 5) == "5 / 5"` |
| `Position` 狀態檔不存在 | `get` 回傳 `default`;不報錯 |
| `Position` 狀態檔毀損(非合法 JSON) | `get` 視為空狀態回傳 `default`(容錯,不讓壞檔擋住瀏覽);下一次 `set` 以乾淨內容覆寫 |
| `Position` 未知資料夾 | `get` 回傳 `default`(預設 0) |
| `Position` 路徑正規化 | 同一資料夾的不同字串寫法,`set` 後 `get` 取得同一值 |
| `Position` 持久化 | `set` 後**新建**一個 `Position(同 state_path)` 仍 `get` 得到剛寫入的值 |

---

## 5. Acceptance Criteria(可被 pytest 驗,帶具體期望值)

> 測試一律以 `tmp_path` 建假影像檔(寫任意 bytes 即可,`scan` 不解碼內容)與狀態檔。
> 控制 `mtime` 用 `os.utime(path, (atime, mtime))`;控制 `size` 用寫入不同長度 bytes。
> 路徑斷言請用 `os.path.normcase` 容忍 Windows 分隔字元差異。

### scan
- **AC1**(自然排序 index):在 `tmp_path` 建 `img1.png`、`img2.png`、`img10.png`,
  `recs = scan(str(tmp_path))` 後 `[r["name"] for r in recs] == ["img1.png", "img2.png", "img10.png"]`,
  且 `[r["index"] for r in recs] == [0, 1, 2]`。
- **AC2**(大小寫不敏感副檔名):建 `a.PNG`、`b.Jpg`、`c.TIFF`,`scan` 後 `len(scan(str(tmp_path))) == 3`,
  且 `{r["name"] for r in recs} == {"a.PNG", "b.Jpg", "c.TIFF"}`。
- **AC3**(過濾非影像 + 忽略子目錄):資料夾含 `keep.png`、`note.txt`、子目錄 `sub/`(內有 `inner.png`)。
  `recs = scan(str(tmp_path))` → `[r["name"] for r in recs] == ["keep.png"]`(`note.txt`、`sub`、`inner.png` 皆不在)。
- **AC4**(record 欄位齊全且型別正確):對 `scan` 任一筆 `r`,
  `set(r.keys()) == {"path","name","index","mtime","size"}`,
  且 `isinstance(r["path"], str) and isinstance(r["name"], str) and isinstance(r["index"], int)
  and isinstance(r["mtime"], float) and isinstance(r["size"], int)`。
- **AC5**(size/mtime 為真實檔案值):建 `x.png` 寫入 `b"abcde"`(5 bytes)並 `os.utime(path, (1000.0, 1234.5))`,
  `r = scan(str(tmp_path))[0]` → `r["size"] == 5` 且 `r["mtime"] == 1234.5`,
  且 `os.path.normcase(r["path"]) == os.path.normcase(os.path.join(str(tmp_path), "x.png"))`。
- **AC6**(資料夾不存在):`scan(str(tmp_path / "no_such_dir"))` 應 `raise NotADirectoryError`
  (`pytest.raises(NotADirectoryError)`)。
- **AC7**(目標是檔案非目錄):對 `tmp_path` 下一個已建立的檔案 `f.png` 呼叫 `scan(str(f.png))`
  應 `raise NotADirectoryError`。
- **AC8**(空 / 無符合):空資料夾 `scan(...) == []`;只含 `readme.md` 的資料夾 `scan(...) == []`。
- **AC9**(.tif 與 .tiff 都收;完整副檔名比對):建 `a.tif`、`b.tiff`、`c.notpng`,
  `{r["name"] for r in scan(str(tmp_path))} == {"a.tif", "b.tiff"}`(`c.notpng` 不因含 `png` 子字串而入選)。

### sort_records
- **AC10**(key="time" 升冪 + 重編 index):用三筆 record(透過 `scan` 取得真實 mtime,
  或直接構造 dict),令 mtime 順序為 `b<a<c`。`out = sort_records(recs, key="time")` →
  `[r["name"] for r in out]` 依 mtime 升冪排列,且 `[r["index"] for r in out] == [0,1,2]`。
- **AC11**(key="size" 升冪):建 `big.png`(10 bytes)、`small.png`(2 bytes)、`mid.png`(5 bytes),
  `recs = scan(...)`;`out = sort_records(recs, key="size")` →
  `[r["name"] for r in out] == ["small.png", "mid.png", "big.png"]` 且 `[r["index"] for r in out] == [0,1,2]`。
- **AC12**(key="name" 自然排序):對名為 `f10,f2,f1` 的 record `sort_records(recs, key="name")` →
  `[r["name"] for r in out]` 開頭為 `["f1...", "f2...", "f10..."]`(自然序,非字典序)。
- **AC13**(tie-break deterministic):兩筆 record `mtime` 相同但 `name` 為 `z.png`、`a.png`,
  `sort_records(recs, key="time")` 的 `name` 順序為 `["a.png", "z.png"]`(同鍵以 name 自然序 tie-break)。
- **AC14**(非法 key):`sort_records(recs, key="bogus")` 應 `raise ValueError`。
- **AC15**(回新 list 且不變更原物件):
  `original = scan(...)`;`snapshot_names = [r["name"] for r in original]`;`snapshot_idx = [r["index"] for r in original]`;
  `out = sort_records(original, key="size")` → `out is not original`,
  且呼叫後 `[r["name"] for r in original] == snapshot_names` 且 `[r["index"] for r in original] == snapshot_idx`
  (原 list 與其內 dict 的 index 皆未被改動)。
- **AC16**(空輸入):`sort_records([], key="name") == []`。

### progress
- **AC17**(1-based 格式):`progress(0, 5) == "1 / 5"`。
- **AC18**(末尾):`progress(4, 5) == "5 / 5"`。
- **AC19**(total<=0):`progress(0, 0)` 與 `progress(2, -1)` 皆應 `raise ValueError`。

### Position(真實讀寫 / round-trip)
- **AC20**(預設值):`p = Position(str(tmp_path / "state.json"))`;
  `p.get(str(tmp_path)) == 0`,`p.get(str(tmp_path), default=7) == 7`(無紀錄回 default)。
- **AC21**(set→get round-trip):`p.set(str(tmp_path), 3)` 後 `p.get(str(tmp_path)) == 3`。
- **AC22**(立即持久化,跨實例):`state = str(tmp_path / "state.json")`;
  `Position(state).set(str(tmp_path), 9)`;
  **新建** `p2 = Position(state)` → `p2.get(str(tmp_path)) == 9`(證明 set 已落地檔案,非只在記憶體)。
- **AC23**(狀態檔內容為合法 JSON 且含寫入值):AC22 後 `json.loads(open(state, encoding="utf-8").read())`
  能解析,且其 value 含 `9`(對應該資料夾 key 的值為 `9`)。
- **AC24**(多資料夾互不干擾):對 `dirA`、`dirB` 分別 `set(...,1)`、`set(...,4)`;
  新實例 `get(dirA)==1` 且 `get(dirB)==4`。
- **AC25**(路徑正規化一致):`p.set(str(tmp_path), 2)` 後,以同一資料夾的不同寫法(例如尾端加分隔字元
  `str(tmp_path) + os.sep`,或 `os.path.join(str(tmp_path), "sub", "..")`)呼叫 `p.get(...)` 仍得 `2`。
- **AC26**(毀損狀態檔容錯):先寫 `state.json` 內容為 `"{ not valid json"`;
  `p = Position(state)`;`p.get(str(tmp_path)) == 0`(不丟例外);
  接著 `p.set(str(tmp_path), 5)` 後 `Position(state).get(str(tmp_path)) == 5`(壞檔被乾淨覆寫)。
- **AC27**(父目錄自動建立):`state = str(tmp_path / "nested" / "deep" / "state.json")`(父目錄不存在);
  `Position(state).set(str(tmp_path), 1)` 不報錯,且 `os.path.exists(state) is True`,
  新實例 `Position(state).get(str(tmp_path)) == 1`。

---

## 6. 對齊與相依
- **相依**:無跨模組契約;`scan` 回傳的 `path` 字串供 `imageio.load` 使用(單向,不成環)。
- **Tier B 理由**:有檔案系統 I/O(掃描目錄)與狀態檔持久化。但本模組**無 GUI、無瀏覽器解碼、無非同步**,
  故真實驗收以「以 tmp_path 真實檔案做 round-trip / 持久化 / 排序」涵蓋,**不需** `@pytest.mark.e2e`;
  上述 AC 即為真實讀寫驗證(AC5/AC22/AC23/AC27 直接斷言磁碟真值),非「物件存在」代理。
- **不在本模組範圍**:縮圖產生、影像解碼、Streamlit 渲染、鍵盤事件(屬 `imageio` / `app`)。
