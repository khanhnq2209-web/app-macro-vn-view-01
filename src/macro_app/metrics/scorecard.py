"""Scorecard theo phân khúc (kiểu OECD/JRC composite indicator, ECB/ESRB heatmap).

Điểm dòng = điểm của mức hiện tại. Tỷ trọng chia theo nhóm (trụ cột) rồi trong nhóm: ô đã nhập
(%) giữ nguyên, ô để trống chia đều phần còn lại; không nhập gì thì chia đều.
Điểm tổng = tổng(điểm * trọng số) / tổng trọng số dòng có số; độ phủ < `min_coverage` thì bỏ.
Đóng góp hiển thị đã chia độ phủ nên cộng đúng ra điểm tổng.
Số cũ hơn `max_carry_months` coi như thiếu. Lịch sử chưa trừ độ trễ công bố.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from macro_app.config import CONFIG_DIR, Indicator, read_yaml
from macro_app.metrics import threshold_preview as tp
from macro_app.metrics.status import LEVELS, cuts_of, evaluate, validate_cfg
from macro_app.metrics.summary import measure_text, measure_unit
from macro_app.metrics.transforms import measure

ROW_KEYS = ("method", "window_years", "cuts", "side", "measure", "labels", "description")
COMPARE_MONTHS = (1, 3, 12)  # kỳ so sánh trên trang Scorecard


def load_settings(config_dir: Path = CONFIG_DIR) -> dict:
    return read_yaml(config_dir / "scorecard.yaml")


def make_context(  # noqa: PLR0913
    frames: dict[str, pd.DataFrame],
    catalog: dict[str, Indicator],
    target_series: dict[str, pd.Series],
    *,
    asof: pd.Timestamp,
    settings: dict,
    min_points: dict,
) -> dict:
    """Ngữ cảnh chấm: tháng chấm, mục tiêu Chính phủ theo chỉ số (năm của kỳ mới nhất)."""
    by_code, targets = {}, {}
    for code, ind in catalog.items():
        series = target_series.get(ind.target) if ind.target else None
        if series is None or series.empty:
            continue
        by_code[code] = series
        frame = frames.get(code)
        last = frame.index.max() if frame is not None and not frame.empty else pd.NaT
        same_year = series[series.index.year == last.year] if pd.notna(last) else series.iloc[:0]
        targets[code] = float(same_year.iloc[-1]) if len(same_year) else np.nan
    return {
        "settings": settings,
        "asof": pd.Timestamp(asof).normalize(),
        "min_points": min_points,
        "targets": targets,
        "target_series": by_code,
    }


def row_cfg(row: dict, min_points: dict) -> dict:
    cfg = {k: row[k] for k in ROW_KEYS if k in row}
    cfg["min_points"] = min_points
    return cfg


def pillar_of(row: dict, catalog: dict[str, Indicator]) -> str:
    return row.get("pillar") or catalog[row["code"]].group


def pillar_order(card: dict, catalog: dict[str, Indicator]) -> list[str]:
    """Thứ tự nhóm: danh sách `pillars` của phân khúc (nếu có) rồi theo thứ tự dòng."""
    named = [p["name"] for p in card.get("pillars") or []]
    from_rows = [pillar_of(r, catalog) for r in card.get("rows", []) if r.get("code") in catalog]
    return list(dict.fromkeys([*named, *from_rows]))


def _split(given: list[float | None]) -> list[float]:
    """Tỷ trọng (%): ô có số giữ nguyên, ô trống chia đều phần còn lại; chuẩn hóa tổng 1.

    Nhập sai (vượt 100% hoặc không đủ 100% mà không còn ô trống) thì chia theo tỷ lệ đã nhập;
    `weight_errors` báo lỗi để người dùng sửa.
    """
    if not given:
        return []
    n_free = sum(w is None for w in given)
    entered = sum(float(w) for w in given if w is not None)
    share = max(0.0, 100.0 - entered) / n_free if n_free else 0.0
    raw = [share if w is None else max(0.0, float(w)) for w in given]
    total = sum(raw)
    return [x / total for x in raw] if total else [1.0 / len(given)] * len(given)


def _scored_by_pillar(rows: list[dict], catalog: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("code") in catalog and not r.get("info"):
            out.setdefault(pillar_of(r, catalog), []).append(r)
    return out


def weights(
    rows: list[dict], catalog: dict[str, Indicator], pillars: list[dict] | None = None
) -> dict[str, float]:
    """Trọng số tổng 1 của các dòng tính điểm: chia theo nhóm, rồi trong nhóm.

    Nhóm chỉ có dòng tham khảo không nhận trọng số. `pillars` = [{name, weight (%)}].
    """
    by = _scored_by_pillar(rows, catalog)
    given = {p["name"]: p.get("weight") for p in pillars or []}
    pw = dict(zip(by, _split([given.get(name) for name in by]), strict=True))
    out = {}
    for name, part in by.items():
        for r, w in zip(part, _split([r.get("weight") for r in part]), strict=True):
            out[r["code"]] = pw[name] * w
    return out


def _check_split(label: str, given: list[float | None]) -> list[str]:
    entered = [float(w) for w in given if w is not None]
    total = sum(entered)
    has_blank = len(entered) < len(given)
    problems = [
        (any(w < 0 for w in entered), "tỷ trọng âm"),
        (total > 100 + 1e-6, f"tỷ trọng đã nhập {total:g}%, vượt 100%"),
        (
            bool(given) and not has_blank and abs(total - 100) > 1e-6,
            f"tỷ trọng cộng {total:g}%, cần đủ 100%",
        ),
        (
            has_blank and 100 - 1e-6 <= total <= 100 + 1e-6,
            f"đã nhập {total:g}%, các ô để trống sẽ thành 0%",
        ),
    ]
    return [f"{label}: {text}" for bad, text in problems if bad][:1]


def weight_errors(card: dict, catalog: dict) -> list[str]:
    by = _scored_by_pillar(card.get("rows", []), catalog)
    given = {p["name"]: p.get("weight") for p in card.get("pillars") or []}
    errors = _check_split("Các nhóm", [given.get(name) for name in by])
    for name, part in by.items():
        errors += _check_split(f"Nhóm {name}", [r.get("weight") for r in part])
    for name in given:
        if name not in by:
            errors.append(f"Nhóm {name} chưa có chỉ số tính điểm")
    return errors


def validate_card(card: dict, catalog: dict, settings: dict) -> list[str]:
    """Lỗi cấu hình scorecard (chạy lúc build và trước khi lưu)."""
    errors = weight_errors(card, catalog)
    default_levels = {int(k) for k in settings["default_scores"]}
    codes = [r.get("code") for r in card["rows"]]
    errors += [f"{c}: trùng dòng" for c in dict.fromkeys(codes) if codes.count(c) > 1]
    for row in card["rows"]:
        code = row.get("code")
        if code not in catalog:
            errors.append(f"{code}: không có trong catalog")
            continue
        errors += [f"{code}: {e}" for e in validate_cfg(row_cfg(row, {}))]
        n = len(cuts_of(row) or []) + 1
        if row.get("scores") is not None and len(row["scores"]) != n:
            errors.append(f"{code}: {len(row['scores'])} điểm cho {n} mức")
        if any(not -2 <= float(x) <= 2 for x in row.get("scores") or []):
            errors.append(f"{code}: điểm mỗi mức phải trong khoảng −2 đến +2")
        if n in LEVELS and n not in default_levels:
            errors.append(f"{code}: chưa có thang điểm mặc định cho {n} mức")
    return errors


def row_scores(row: dict, n_levels: int, settings: dict) -> list[float]:
    scores = row.get("scores")
    if scores and len(scores) == n_levels:
        return [float(x) for x in scores]
    return [float(x) for x in settings["default_scores"][n_levels]]


def rating(score: float, bands: list[dict]) -> str:
    if score is None or np.isnan(score):
        return "Chưa đủ dữ liệu"
    return next((b["label"] for b in bands if round(score, 6) >= b["min"]), bands[-1]["label"])


def _carry(ind: Indicator, settings: dict) -> int:
    return int(settings["history"]["max_carry_months"].get(ind.frequency, 3))


def _is_stale(series: pd.Series, ind: Indicator, asof: pd.Timestamp, settings: dict) -> bool:
    """Kỳ mới nhất cũ hơn giới hạn giữ số (cùng quy tắc với lịch sử)."""
    s = series.dropna()
    if s.empty:
        return True
    last_month = s.index[-1] + pd.offsets.MonthEnd(0)
    limit = asof + pd.offsets.MonthEnd(0) - pd.DateOffset(months=_carry(ind, settings))
    return last_month < limit + pd.offsets.MonthEnd(0)


def evaluate_row(row: dict, series: pd.Series, ind: Indicator, ctx: dict) -> dict:
    """Mức và điểm hiện tại của một dòng (số quá cũ coi như thiếu, giữ `last_score`)."""
    cfg = row_cfg(row, ctx["min_points"])
    res = evaluate(series, ind.frequency, cfg, "scorecard", ctx["targets"].get(row["code"], np.nan))
    n = len(cuts_of(cfg) or []) + 1
    score, scale = np.nan, [np.nan]
    if n in LEVELS:
        scale = row_scores(row, n, ctx["settings"])
        if res.status in LEVELS[n]:
            score = scale[LEVELS[n].index(res.status)]
    stale = _is_stale(series, ind, ctx["asof"], ctx["settings"])
    measured = measure(series, ind.frequency, cfg.get("measure")).dropna()
    return {
        "code": row["code"],
        "group": ind.group,
        "status": res.status,
        "label": res.label,
        "score": np.nan if stale else score,
        "last_score": score,
        "score_min": float(np.nanmin(scale)),
        "score_max": float(np.nanmax(scale)),
        "stale": stale,
        "measured": float(measured.iloc[-1]) if len(measured) else np.nan,
        "measured_unit": measure_unit(cfg.get("measure"), ind.unit),
        "measure_text": measure_text(cfg.get("measure"), ind.frequency),
        "detail": res.detail,
    }


def current(
    card: dict, frames: dict[str, pd.DataFrame], catalog: dict, ctx: dict
) -> tuple[pd.DataFrame, dict]:
    """Bảng dòng hiện tại + tổng (điểm, độ phủ, xếp hạng)."""
    rows = [r for r in card["rows"] if r["code"] in catalog]
    w = weights(rows, catalog, card.get("pillars"))
    out = []
    for row in rows:
        frame = frames.get(row["code"])
        series = frame["value"] if frame is not None and not frame.empty else pd.Series(dtype=float)
        rec = evaluate_row(row, series, catalog[row["code"]], ctx)
        rec["pillar"] = pillar_of(row, catalog)
        rec["weight"] = w.get(row["code"], 0.0)
        rec["info"] = bool(row.get("info"))  # chỉ tham khảo: không vào điểm
        rec["show_level"] = row.get("show_level", True) is not False
        out.append(rec)
    table = pd.DataFrame(out)
    have = (table["score"].notna() & ~table["info"]) if not table.empty else pd.Series(dtype=bool)
    coverage = float(table.loc[have, "weight"].sum()) if not table.empty else 0.0
    if not table.empty:  # trọng số thực dùng: chia lại theo độ phủ, đóng góp cộng ra điểm tổng
        table["weight_used"] = np.where(have, table["weight"] / coverage if coverage else 0.0, 0.0)
        table["contribution"] = np.where(have, table["score"] * table["weight_used"], np.nan)
    score = np.nan
    if coverage >= ctx["settings"]["min_coverage"]:
        weighted = (table.loc[have, "score"] * table.loc[have, "weight"]).sum()
        score = round(float(weighted / coverage), 6)
    total = {
        "score": score,
        "coverage": coverage,
        "rating": rating(score, ctx["settings"]["rating_bands"]),
    }
    return table, total


def pillar_table(table: pd.DataFrame, order: list[str]) -> pd.DataFrame:
    """Một dòng mỗi nhóm: số chỉ số tính điểm, trọng số cấu hình, đóng góp, mức (làm tròn)."""
    cols = ["pillar", "n_scored", "n_all", "weight", "contribution", "level"]
    if table.empty:
        return pd.DataFrame(columns=cols)
    out = []
    for name in [p for p in order if p in set(table["pillar"])]:
        part = table[(table["pillar"] == name) & ~table["info"].astype(bool)]
        have = part[part["score"].notna()]
        w = have["weight"].sum()
        level = np.nan
        if w:
            mean = (have["score"] * have["weight"]).sum() / w
            level = float(np.clip(np.floor(mean + 0.5), -2, 2))  # làm tròn 0,5 lên, như bảng điểm
        out.append(
            {
                "pillar": name,
                "n_scored": len(have),
                "n_all": len(part),
                "weight": float(part["weight"].sum()),
                "contribution": float(have["contribution"].sum()) if len(have) else np.nan,
                "level": level,
            }
        )
    return pd.DataFrame(out, columns=cols)


def sensitivity(table: pd.DataFrame) -> dict:
    """Điểm nếu các dòng số cũ quay lại: giữ mức cuối đã biết, và biên thấp nhất / cao nhất."""
    if table.empty or "last_score" not in table:
        return {}
    scored = table[~table["info"].astype(bool)]
    have = scored[scored["score"].notna()]
    stale = scored[scored["stale"].astype(bool) & scored["last_score"].notna()]
    cov, ws = have["weight"].sum(), stale["weight"].sum()
    if stale.empty or not cov + ws:
        return {}
    base = (have["score"] * have["weight"]).sum()

    def with_stale(values: pd.Series) -> float:
        return round(float((base + (values * stale["weight"]).sum()) / (cov + ws)), 6)

    return {
        "keep": with_stale(stale["last_score"]),
        "worst": with_stale(stale["score_min"]),
        "best": with_stale(stale["score_max"]),
        "codes": list(stale["code"]),
        "weight": float(ws),
    }


def _row_history(
    row: dict, series: pd.Series, ind: Indicator, ctx: dict, grid: pd.DatetimeIndex
) -> pd.Series:
    """Điểm của dòng trên lưới cuối tháng chung; giữ số cũ tối đa `max_carry_months`."""
    cfg = row_cfg(row, ctx["min_points"])
    measured = measure(series, ind.frequency, cfg.get("measure"))
    n = len(cuts_of(cfg) or []) + 1
    if measured.empty or n not in LEVELS:
        return pd.Series(np.nan, index=grid)
    target = ctx["target_series"].get(row["code"])
    point_scores = tp.history_scores(measured, cfg, ind.frequency, target)
    points = row_scores(row, n, ctx["settings"])
    statuses = point_scores.dropna().map(lambda x: tp.status_of_score(x, cfg))
    level_score = statuses.map(lambda s: points[LEVELS[n].index(s)] if s in LEVELS[n] else np.nan)
    monthly = level_score.resample("ME").last().reindex(grid)
    return monthly.ffill(limit=_carry(ind, ctx["settings"]))


def _values(frames: dict[str, pd.DataFrame], code: str) -> pd.Series:
    frame = frames.get(code)
    return frame["value"] if frame is not None and not frame.empty else pd.Series(dtype=float)


def row_history(
    card: dict, frames: dict[str, pd.DataFrame], catalog: dict, ctx: dict
) -> tuple[pd.DataFrame, pd.Series]:
    """Điểm từng dòng theo tháng (date × code) và trọng số cấu hình của các dòng tính điểm."""
    rows = [r for r in card["rows"] if r["code"] in catalog and not r.get("info")]
    if not rows:
        return pd.DataFrame(), pd.Series(dtype=float)
    w = weights(rows, catalog, card.get("pillars"))
    end = ctx["asof"] + pd.offsets.MonthEnd(0)
    start = end - pd.DateOffset(years=int(ctx["settings"]["history"]["years"]))
    grid = pd.date_range(start + pd.offsets.MonthEnd(0), end, freq="ME")
    table = pd.DataFrame(
        {
            r["code"]: _row_history(r, _values(frames, r["code"]), catalog[r["code"]], ctx, grid)
            for r in rows
        }
    )
    return table, pd.Series(w)[table.columns]


def _history_from(table: pd.DataFrame, wser: pd.Series, ctx: dict) -> pd.DataFrame:
    if table.empty:
        return pd.DataFrame(columns=["date", "score", "coverage", "rating"])
    coverage = table.notna().mul(wser, axis=1).sum(axis=1)
    score = (table.fillna(0).mul(wser, axis=1).sum(axis=1) / coverage.replace(0, np.nan)).round(6)
    score[coverage < ctx["settings"]["min_coverage"]] = np.nan
    out = pd.DataFrame({"score": score, "coverage": coverage}).rename_axis("date").reset_index()
    out["rating"] = out["score"].map(lambda s: rating(s, ctx["settings"]["rating_bands"]))
    return out


def history(card: dict, frames: dict[str, pd.DataFrame], catalog: dict, ctx: dict) -> pd.DataFrame:
    """Điểm scorecard theo tháng: [date, score, coverage, rating], tới tháng chấm."""
    table, wser = row_history(card, frames, catalog, ctx)
    return _history_from(table, wser, ctx)


def compare_at(  # noqa: PLR0913
    table: pd.DataFrame,
    wser: pd.Series,
    pillar_by_code: dict[str, str],
    date: pd.Timestamp,
    *,
    ctx: dict,
    months: int,
) -> dict:
    """Điểm tháng `date`: tổng, đóng góp từng nhóm (chia độ phủ của tháng đó), điểm từng dòng."""
    empty = {"months": months, "date": date, "total": np.nan, "pillars": {}, "rows": {}}
    if table.empty or date not in table.index:
        return empty
    s = table.loc[date]
    have = s.notna()
    cov = float(wser[have].sum())
    if not cov:
        return {**empty, "rows": s.to_dict()}
    if cov < ctx["settings"]["min_coverage"]:  # tháng đó không chấm: không so từng nhóm
        return {**empty, "rows": s.to_dict()}
    contrib = s[have] * wser[have] / cov
    total = float(contrib.sum())
    pillars = contrib.groupby(contrib.index.map(pillar_by_code)).sum().to_dict()
    return {
        **empty,
        "total": round(total, 6) if pd.notna(total) else np.nan,
        "pillars": pillars,
        "rows": s.to_dict(),
    }


def _stale_bad(table: pd.DataFrame) -> str:
    """Mã (cách nhau bằng dấu phẩy) các dòng bị loại vì số cũ nhưng mức cuối cùng là xấu."""
    if table.empty or "stale" not in table:
        return ""
    info = table["info"].astype(bool) if "info" in table else False
    bad = table[table["stale"].astype(bool) & ~info & table["status"].isin(["orange", "red"])]
    return ",".join(bad["code"])


def summarize_total(
    total: dict, hist: pd.DataFrame, table: pd.DataFrame, prev_month: pd.Timestamp
) -> dict:
    """Tổng cho đầu trang: điểm, điểm tháng trước, tháng gần nhất đủ dữ liệu, số dòng số cũ."""
    prev = hist.loc[hist["date"] == prev_month, "score"] if not hist.empty else pd.Series()
    scored = hist.dropna(subset=["score"]).tail(1) if not hist.empty else hist
    has = len(scored) > 0
    return {
        **total,
        "prev_score": float(prev.iloc[0]) if len(prev) else np.nan,
        "last_score": float(scored["score"].iloc[0]) if has else np.nan,
        "last_date": scored["date"].iloc[0] if has else pd.NaT,
        "last_rating": scored["rating"].iloc[0] if has else "",
        "n_stale": int((table["stale"] & ~table["info"]).sum()) if "stale" in table else 0,
        "stale_bad": _stale_bad(table),
    }


def evaluate_card(
    card: dict, frames: dict[str, pd.DataFrame], catalog: dict, ctx: dict
) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Chấm một phân khúc: bảng dòng, tổng (kèm so sánh kỳ, độ nhạy, nhóm), lịch sử."""
    table, total = current(card, frames, catalog, ctx)
    rh, wser = row_history(card, frames, catalog, ctx)
    hist = _history_from(rh, wser, ctx)
    month = ctx["asof"] + pd.offsets.MonthEnd(0)
    out = summarize_total(total, hist, table, month - pd.offsets.MonthEnd(1))
    pillar_by_code = {
        r["code"]: pillar_of(r, catalog) for r in card["rows"] if r["code"] in catalog
    }
    out["compare"] = {
        k: compare_at(rh, wser, pillar_by_code, month - pd.offsets.MonthEnd(k), ctx=ctx, months=k)
        for k in COMPARE_MONTHS
    }
    out["sensitivity"] = sensitivity(table)
    out["pillars"] = pillar_table(table, pillar_order(card, catalog)).to_dict("records")
    return table, out, hist
