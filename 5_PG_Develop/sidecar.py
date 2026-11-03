"""sidecar 模組(M2 / Tier B)。

未受管理時,每張影像一份同目錄、同檔名主幹的 sidecar JSON(`<name>.cvr.json`)；
若設定 `CVR_SIDECAR_DIR`,則把 sidecar 寫到該受管理資料夾,不修改來源影像目錄。
兩種模式都只持久化人工判讀狀態,絕不修改原始影像檔。

契約見 3_Architect_Design/06_sidecar.md。除 default()/sidecar_path()/load()/save()
外的函式皆為純函式(copy-on-write,不就地改、不碰時鐘/亂數/檔案系統)。

僅依賴 Python 標準庫。
"""
import copy
import hashlib
import json
import os
import tempfile

# 設計 §2.1 合法的 review_status 列舉
_LEGAL_STATUS = ("none", "need_review", "done")


def default() -> dict:
    """回傳一份全新、獨立的預設 sidecar dict(§2.1 八欄位、固定初值)。"""
    return {
        "review_status": "none",
        "tags": [],
        "verdict": "unset",
        "comment": "",
        "bookmarked": False,
        "rois": [],
        "reviewer": "",
        "timestamp": "",
    }


def _legacy_sidecar_path(image_path) -> str:
    p = os.fspath(image_path)
    root, _ext = os.path.splitext(p)
    return root + ".cvr.json"


def _managed_sidecar_dir():
    value = os.environ.get("CVR_SIDECAR_DIR")
    if not value:
        return None
    return os.path.abspath(os.path.expanduser(value))


def _sidecar_path(image_path, managed_dir) -> str:
    if managed_dir is None:
        return _legacy_sidecar_path(image_path)
    image = os.path.normcase(os.path.abspath(os.fspath(image_path)))
    digest = hashlib.sha256(os.fsencode(image)).hexdigest()
    return os.path.join(managed_dir, digest + ".cvr.json")


def sidecar_path(image_path) -> str:
    """回傳 sidecar 路徑;受管理時依正規化影像路徑映射到外部資料夾。"""
    return _sidecar_path(image_path, _managed_sidecar_dir())


def load(image_path) -> dict:
    """讀取 sidecar;不存在 / 空檔 / 壞 JSON 都回 default()。
    合法但缺欄位時以 default() 補齊缺欄位,既有值保留。
    """
    managed_dir = _managed_sidecar_dir()
    path = _sidecar_path(image_path, managed_dir)
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        if managed_dir is None:
            return default()
        try:
            with open(_legacy_sidecar_path(image_path), encoding="utf-8") as f:
                raw = f.read()
        except (FileNotFoundError, OSError):
            return default()
    except OSError:
        return default()

    if raw.strip() == "":
        return default()

    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return default()

    if not isinstance(parsed, dict):
        return default()

    result = default()
    for key in result:
        if key in parsed:
            result[key] = parsed[key]
    return result


def save(image_path, data) -> None:
    """原子寫入;受管理時建立外部 sidecar 目錄,預設行為不變。"""
    managed_dir = _managed_sidecar_dir()
    path = _sidecar_path(image_path, managed_dir)
    directory = os.path.dirname(path) or "."
    if managed_dir is not None:
        os.makedirs(directory, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        suffix=".tmp", prefix=os.path.basename(path) + ".", dir=directory
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        # 失敗時清掉殘留暫存檔,避免污染目錄
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise


def set_status(data, status) -> dict:
    """設定 review_status;非法值丟 ValueError(及早失敗,不就地改輸入)。"""
    if status not in _LEGAL_STATUS:
        raise ValueError(
            "invalid review_status: %r (must be one of %r)" % (status, _LEGAL_STATUS)
        )
    new = copy.deepcopy(data)
    new["review_status"] = status
    return new


def toggle_bookmark(data) -> dict:
    """反轉 bookmarked(copy-on-write)。"""
    new = copy.deepcopy(data)
    new["bookmarked"] = not new["bookmarked"]
    return new


def add_tag(data, tag) -> dict:
    """加入 tag,去重且保序(copy-on-write)。"""
    new = copy.deepcopy(data)
    if tag not in new["tags"]:
        new["tags"].append(tag)
    return new


def remove_tag(data, tag) -> dict:
    """移除 tag;不存在視為 no-op(copy-on-write,不丟錯)。"""
    new = copy.deepcopy(data)
    if tag in new["tags"]:
        new["tags"] = [t for t in new["tags"] if t != tag]
    return new


def add_roi(data, bbox, label="", verdict="unset", comment="") -> dict:
    """追加一個 ROI;bbox 存成長度 4 的 list(copy-on-write)。"""
    new = copy.deepcopy(data)
    new["rois"].append({
        "bbox": [int(v) for v in bbox],
        "label": label,
        "verdict": verdict,
        "comment": comment,
    })
    return new
