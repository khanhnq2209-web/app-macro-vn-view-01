"""Scorecard theo phân khúc (kiểu OECD/JRC composite indicator, ECB/ESRB heatmap).

Điểm dòng = điểm của mức hiện tại; trọng số chia đều theo trụ cột rồi trong trụ cột.
Điểm tổng = tổng(điểm * trọng số) / tổng trọng số dòng có số; độ phủ < `min_coverage` thì bỏ.
Số cũ hơn `max_carry_months` coi như thiếu. Lịch sử chưa trừ độ trễ công bố.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from macro_app.config import CONFIG_DIR, Indicator, read_yaml
from macro_app.metrics import threshold_preview as tp
from macro_app.metrics.status import LEVELS, cuts_of, evaluate, validate_cfg
from macro_app.metrics.summary import measure_text
from macro_app.metrics.transforms import measure

ROW_KEYS = ("method", "window_years", "cuts", "side", "measure", "labels", "description")


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


def validate_card(card: dict, catalog: dict, settings: dict) -> list[str]:
    """Lỗi cấu hình scorecard (chạy lúc build, ghi vào build_meta)."""
    errors = []
    given = [r.get("weight") for r in card["rows"] if r.get("weight") is not None]
    if any(float(w) < 0 for w in given):
        errors.append("trọng số âm")
    default_levels = {int(k) for k in settings["default_scores"]}
    for row in card["rows"]:
        code = row.get("code")
        if code not in catalog:
            errors.append(f"{code}: không có trong catalog")
            continue
        errors += [f"{code}: {e}" for e in validate_cfg(row_cfg(row, {}))]
        n = len(cuts_of(row) or []) + 1
        if row.get("scores") is not None and len(row["scores"]) != n:
            errors.append(f"{code}: {len(row['scores'])} điểm cho {n} mức")
        if n in LEVELS and n not in default_levels:
            errors.append(f"{code}: chưa có thang điểm mặc định cho {n} mức")
    return errors


def row_scores(row: dict, n_levels: int, settings: dict) -> list[float]:
    scores = row.get("scores")
    if scores and len(scores) == n_levels:
        return [float(x) for x in scores]
    return [float(x) for x in settings["default_scores"][n_levels]]


def pillar_of(row: dict, catalog: dict[str, Indicator]) -> str:
    return row.get("pillar") or catalog[row["code"]].group


def weights(rows: list[dict], catalog: dict[str, Indicator]) -> dict[str, float]:
    """Trọng số chuẩn hóa tổng 1: chia đều trụ cột rồi trong trụ cột.

    Có dòng ghi `weight` thì dùng số đó; dòng để trống nhận trung bình các `weight` đã ghi.
    """
    rows = [r for r in rows if r["code"] in catalog and not r.get("info")]
    explicit = [float(r["weight"]) for r in rows if r.get("weight") is not None]
    if explicit:
        fill = float(np.mean(explicit))
        raw = {r["code"]: float(r["weight"]) if r.get("weight") is not None else fill for r in rows}
    else:
        pillars = pd.Series({r["code"]: pillar_of(r, catalog) for r in rows})
        n_pillars = pillars.nunique()
        raw = {c: 1.0 / n_pillars / (pillars == pillars[c]).sum() for c in pillars.index}
    total = sum(raw.values())
    return {c: (w / total if total else 0.0) for c, w in raw.items()}


def rating(score: float, bands: list[dict]) -> str:
    if score is None or np.isnan(score):
        return "Chưa đủ dữ liệu"
    return next(b["label"] for b in bands if round(score, 6) >= b["min"])


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
    """Mức và điểm hiện tại của một dòng (số quá cũ coi như thiếu)."""
    cfg = row_cfg(row, ctx["min_points"])
    res = evaluate(series, ind.frequency, cfg, "scorecard", ctx["targets"].get(row["code"], np.nan))
    n = len(cuts_of(cfg) or []) + 1
    score = np.nan
    if n in LEVELS and res.status in LEVELS[n]:
        score = row_scores(row, n, ctx["settings"])[LEVELS[n].index(res.status)]
    stale = _is_stale(series, ind, ctx["asof"], ctx["settings"])
    measured = measure(series, ind.frequency, cfg.get("measure")).dropna()
    return {
        "code": row["code"],
        "group": ind.group,
        "status": res.status,
        "label": res.label,
        "score": np.nan if stale else score,
        "stale": stale,
        "measured": float(measured.iloc[-1]) if len(measured) else np.nan,
        "measure_text": measure_text(cfg.get("measure"), ind.frequency),
        "detail": res.detail,
    }


def current(
    card: dict, frames: dict[str, pd.DataFrame], catalog: dict, ctx: dict
) -> tuple[pd.DataFrame, dict]:
    """Bảng dòng hiện tại + tổng (điểm, độ phủ, xếp hạng)."""
    rows = [r for r in card["rows"] if r["code"] in catalog]
    w = weights(rows, catalog)
    out = []
    for row in rows:
        frame = frames.get(row["code"])
        series = frame["value"] if frame is not None and not frame.empty else pd.Series(dtype=float)
        rec = evaluate_row(row, series, catalog[row["code"]], ctx)
        rec["pillar"] = pillar_of(row, catalog)
        rec["weight"] = w.get(row["code"], 0.0)
        rec["info"] = bool(row.get("info"))  # chỉ tham khảo: không vào điểm
        rec["show_level"] = row.get("show_level", True) is not False
        rec["contribution"] = np.nan if rec["info"] else rec["score"] * rec["weight"]
        out.append(rec)
    table = pd.DataFrame(out)
    have = (table["score"].notna() & ~table["info"]) if not table.empty else pd.Series(dtype=bool)
    coverage = float(table.loc[have, "weight"].sum()) if not table.empty else 0.0
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


def history(card: dict, frames: dict[str, pd.DataFrame], catalog: dict, ctx: dict) -> pd.DataFrame:
    """Điểm scorecard theo tháng: [date, score, coverage, rating], tới tháng chấm."""
    rows = [r for r in card["rows"] if r["code"] in catalog and not r.get("info")]
    if not rows:
        return pd.DataFrame(columns=["date", "score", "coverage", "rating"])
    w = weights(rows, catalog)
    end = ctx["asof"] + pd.offsets.MonthEnd(0)
    start = end - pd.DateOffset(years=int(ctx["settings"]["history"]["years"]))
    grid = pd.date_range(start + pd.offsets.MonthEnd(0), end, freq="ME")
    table = pd.DataFrame(
        {
            r["code"]: _row_history(r, _values(frames, r["code"]), catalog[r["code"]], ctx, grid)
            for r in rows
        }
    )
    wser = pd.Series(w)[table.columns]
    coverage = table.notna().mul(wser, axis=1).sum(axis=1)
    score = (table.fillna(0).mul(wser, axis=1).sum(axis=1) / coverage.replace(0, np.nan)).round(6)
    score[coverage < ctx["settings"]["min_coverage"]] = np.nan
    out = pd.DataFrame({"score": score, "coverage": coverage}).rename_axis("date").reset_index()
    out["rating"] = out["score"].map(lambda s: rating(s, ctx["settings"]["rating_bands"]))
    return out


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
    """Chấm một phân khúc (dùng cho xem trước bản nháp): bảng dòng, tổng, lịch sử."""
    table, total = current(card, frames, catalog, ctx)
    hist = history(card, frames, catalog, ctx)
    prev_month = ctx["asof"] + pd.offsets.MonthEnd(0) - pd.offsets.MonthEnd(1)
    return table, summarize_total(total, hist, table, prev_month), hist
