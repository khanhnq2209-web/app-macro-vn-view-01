"""Số dự báo/kế hoạch ghép vào scorecard để tham khảo, không vào điểm chính.

Mỗi điểm dự báo được so với ngưỡng của dòng (chỉ khi dòng đo giá trị gốc) để ra
"điểm nếu theo dự báo": thay điểm các dòng có dự báo, giữ nguyên dòng khác.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from macro_app.metrics import threshold_preview as tp
from macro_app.metrics.status import LEVELS, cuts_of

FED_CODES = {"fed_upper": "range_high_bp", "fed_lower": "range_low_bp", "effr": "effective"}
EFFR_OVER_LOWER = 0.08  # EFFR thường cao hơn biên dưới khoảng 8 bps


@dataclass(frozen=True)
class ForwardPoint:
    label: str  # vd "họp 09/12/2026", "mục tiêu 2026"
    date: pd.Timestamp
    value: float
    source: str  # vd "FedWatch (CME)", "Mục tiêu Chính phủ"
    kind: str  # "market" | "target"


def pick_fedwatch(fedwatch: dict[str, pd.DataFrame], max_gap_days: int = 7) -> pd.DataFrame:
    """Bản xác suất mới nhất: ưu tiên CME QuikStrike nếu không cũ hơn bản tự tính quá N ngày."""
    cme, own = fedwatch.get("quikstrike"), fedwatch.get("computed")
    frames = [f for f in (cme, own) if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame()
    for f in frames:
        f["asof"] = pd.to_datetime(f["asof"])
    if cme is not None and not cme.empty:
        own_last = own["asof"].max() if own is not None and not own.empty else cme["asof"].max()
        if (own_last - cme["asof"].max()).days <= max_gap_days:
            return cme[cme["asof"] == cme["asof"].max()]
    return own[own["asof"] == own["asof"].max()]


def expected_change_history(
    fedwatch: dict[str, pd.DataFrame], fed_upper: pd.Series, months: int = 12
) -> pd.Series:
    """Mỗi ngày có FedWatch: biên trên kỳ vọng ở kỳ họp cuối trong `months` tháng tới
    trừ biên trên Fed hiện hành ngày đó (bps). Ưu tiên CME QuikStrike, ngày không có thì
    dùng bản tự tính từ hợp đồng ZQ."""
    parts = [f for f in (fedwatch.get("quikstrike"), fedwatch.get("computed")) if f is not None]
    parts = [f.assign(asof=pd.to_datetime(f["asof"])) for f in parts if not f.empty]
    upper = fed_upper.dropna().sort_index()
    if not parts or upper.empty:
        return pd.Series(dtype=float)
    seen, out = set(), {}
    for probs in parts:
        for asof, day in probs.groupby("asof"):
            if asof in seen:
                continue
            seen.add(asof)
            path = fed_path(day)
            ahead = path[
                (path["meeting_date"] > asof)
                & (path["meeting_date"] <= asof + pd.DateOffset(months=months))
            ]
            now = upper[upper.index <= asof]
            if ahead.empty or now.empty:
                continue
            out[asof] = (float(ahead["exp_upper"].iloc[-1]) - float(now.iloc[-1])) * 100
    return pd.Series(out, dtype=float).sort_index()


def fed_path(probs: pd.DataFrame) -> pd.DataFrame:
    """Mỗi kỳ họp: biên trên/dưới kỳ vọng (bình quân xác suất) + khoảng khả năng cao nhất."""
    if probs.empty:
        return pd.DataFrame()
    rows = []
    for meeting, g in probs.groupby(pd.to_datetime(probs["meeting_date"])):
        p = g["prob"] / g["prob"].sum()
        top = g.loc[g["prob"].idxmax()]
        rows.append(
            {
                "meeting_date": meeting,
                "exp_upper": float((p * g["range_high_bp"]).sum() / 100),
                "exp_lower": float((p * g["range_low_bp"]).sum() / 100),
                "top_range": f"{top['range_low_bp'] / 100:.2f}–{top['range_high_bp'] / 100:.2f}%",
                "top_prob": float(top["prob"] / g["prob"].sum()),
                "asof": pd.to_datetime(g["asof"]).max(),
                "source": str(g["source"].iloc[0]),
            }
        )
    return pd.DataFrame(rows).sort_values("meeting_date").reset_index(drop=True)


def _horizon_meetings(path: pd.DataFrame) -> pd.DataFrame:
    """Kỳ họp kế tiếp và các kỳ gần cuối năm nay, gần mốc +12 tháng nhất (không trùng)."""
    if path.empty:
        return path
    asof = path["asof"].max()
    ahead = path[path["meeting_date"] > asof]
    picked = []
    year_end = pd.Timestamp(year=asof.year, month=12, day=31)
    for goal in (asof, year_end, asof + pd.DateOffset(months=12)):
        idx = (ahead["meeting_date"] - goal).abs().idxmin() if not ahead.empty else None
        if idx is not None and idx not in picked:
            picked.append(idx)
    return ahead.loc[picked]


def fed_points(code: str, path: pd.DataFrame) -> list[ForwardPoint]:
    out = []
    for r in _horizon_meetings(path).to_dict("records"):
        value = {
            "range_high_bp": r["exp_upper"],
            "range_low_bp": r["exp_lower"],
            "effective": r["exp_lower"] + EFFR_OVER_LOWER,
        }[FED_CODES[code]]
        source = "FedWatch (CME)" if "CME" in r["source"] else "FedWatch tự tính (ZQ)"
        out.append(
            ForwardPoint(
                f"họp {r['meeting_date']:%d/%m/%Y}", r["meeting_date"], value, source, "market"
            )
        )
    return out


def target_point(target: pd.Series | None, asof: pd.Timestamp) -> list[ForwardPoint]:
    if target is None or target.empty:
        return []
    this_year = target[target.index.year == asof.year]
    if this_year.empty:
        return []
    return [
        ForwardPoint(
            f"mục tiêu {asof.year}",
            pd.Timestamp(year=asof.year, month=12, day=31),
            float(this_year.iloc[-1]),
            "Mục tiêu Chính phủ",
            "target",
        )
    ]


KINDS = ("target", "fedwatch", "indicator", "manual")
KIND_LABEL = {
    "target": "Mục tiêu Chính phủ",
    "fedwatch": "FedWatch (CME)",
    "indicator": "Chỉ số khác",
    "manual": "Nhập tay",
}
FEDWATCH_REFS = {"upper": "fed_upper", "lower": "fed_lower", "effective": "effr"}


def load_forecast_map(path=None) -> list[dict]:
    from macro_app.config import read_yaml
    from macro_app.paths import CONFIG_DIR

    file = path or CONFIG_DIR / "forecast_map.yaml"
    return list((read_yaml(file) if file.exists() else {}).get("mappings") or [])


def validate_mapping(m: dict, catalog: dict, target_ids: set[str]) -> list[str]:
    """Lỗi của một dòng bản đồ (rỗng = hợp lệ)."""
    errors = []
    if m.get("code") not in catalog:
        errors.append(f"{m.get('code')}: không có trong catalog")
    kind, ref = m.get("kind"), m.get("ref")
    if kind not in KINDS:
        errors.append(f"{m.get('code')}: loại '{kind}' không hợp lệ")
    elif kind == "target" and ref not in target_ids:
        errors.append(f"{m.get('code')}: chưa có chuỗi mục tiêu '{ref}'")
    elif kind == "fedwatch" and ref not in FEDWATCH_REFS:
        errors.append(f"{m.get('code')}: FedWatch chỉ nhận upper, lower, effective")
    elif kind == "indicator" and ref not in catalog:
        errors.append(f"{m.get('code')}: chỉ số dự báo '{ref}' không có trong catalog")
    elif kind == "manual":
        try:
            float(m.get("value"))
        except (TypeError, ValueError):
            errors.append(f"{m.get('code')}: nhập tay cần giá trị số")
        if not str(m.get("period") or "").strip():
            errors.append(f"{m.get('code')}: nhập tay cần kỳ (vd 2026 hoặc 12/2026)")
    return errors


def _period_end(period) -> pd.Timestamp:
    """'2026' là 31/12/2026; '6/2026' hoặc '2026-06' là cuối tháng 6/2026."""
    text = str(period).strip()
    if text.isdigit() and len(text) == 4:
        return pd.Timestamp(year=int(text), month=12, day=31)
    if "/" in text:
        month, year = text.split("/")
        return pd.Timestamp(year=int(year), month=int(month), day=1) + pd.offsets.MonthEnd(0)
    return pd.Timestamp(text) + pd.offsets.MonthEnd(0)


def points_for(  # noqa: PLR0911
    m: dict | None,
    *,
    path: pd.DataFrame,
    targets: dict[str, pd.Series],
    frames: dict[str, pd.DataFrame],
    asof: pd.Timestamp,
) -> list[ForwardPoint]:
    """Các điểm kế hoạch / dự báo của một dòng bản đồ (rỗng nếu chưa có số)."""
    if not m:
        return []
    kind, ref, label = (
        m.get("kind"),
        m.get("ref"),
        m.get("label") or KIND_LABEL.get(m.get("kind"), ""),
    )
    if kind == "fedwatch" and ref in FEDWATCH_REFS:
        return fed_points(FEDWATCH_REFS[ref], path)
    if kind == "target":
        pts = target_point(targets.get(ref), asof)
        return [ForwardPoint(p.label, p.date, p.value, label or p.source, "target") for p in pts]
    if kind == "indicator":
        frame = frames.get(ref)
        s = (
            frame["value"].dropna()
            if frame is not None and not frame.empty
            else pd.Series(dtype=float)
        )
        if s.empty:
            return []
        return [
            ForwardPoint(f"{s.index[-1]:%d/%m/%Y}", s.index[-1], float(s.iloc[-1]), label, "market")
        ]
    if kind == "manual":
        try:
            value, when = float(m["value"]), _period_end(m["period"])
        except (KeyError, TypeError, ValueError):
            return []
        return [ForwardPoint(f"kỳ {m['period']}", when, value, label or "Nhập tay", "target")]
    return []


def level_of(value: float, measured: pd.Series, cfg: dict, target: float = np.nan) -> str | None:
    """Mức mà giá trị dự báo rơi vào theo ngưỡng của dòng (chỉ khi dòng đo giá trị gốc)."""
    kind = (cfg.get("measure") or {}).get("kind", "level")
    cuts = cuts_of(cfg)
    if kind != "level" or not cuts or len(cuts) + 1 not in LEVELS or measured.empty:
        return None
    score = tp.score_fn(measured, cfg, target)(value)
    status = tp.status_of_score(score, cfg)
    return status if status in LEVELS[len(cuts) + 1] else None


def forward_total(table: pd.DataFrame, min_coverage: float) -> float:
    """Điểm nếu các dòng có dự báo đi theo dự báo xa nhất (dòng khác giữ điểm hiện tại)."""
    if table.empty or "fwd_score" not in table:
        return np.nan
    score = table["fwd_score"].where(table["fwd_score"].notna(), table["score"])
    have = score.notna() & (table["weight"] > 0)
    coverage = float(table.loc[have, "weight"].sum())
    if coverage < min_coverage or not table.loc[table["weight"] > 0, "fwd_score"].notna().any():
        return np.nan
    return round(float((score[have] * table.loc[have, "weight"]).sum() / coverage), 6)


def primary(points: list[ForwardPoint], asof: pd.Timestamp) -> ForwardPoint | None:
    """Điểm hiện trên dòng: cuối năm nay (cùng kỳ với mục tiêu Chính phủ), không có thì xa nhất."""
    if not points:
        return None
    this_year = [p for p in points if p.date.year == asof.year]
    return this_year[-1] if this_year else points[-1]


def _fmt(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def annotate(  # noqa: PLR0913, PLR0915
    table: pd.DataFrame,
    card: dict,
    *,
    frames: dict[str, pd.DataFrame],
    catalog: dict,
    path: pd.DataFrame,
    ctx: dict,
) -> tuple[pd.DataFrame, float]:
    """Thêm cột dự báo vào bảng dòng scorecard; trả (bảng, điểm nếu theo dự báo)."""
    from macro_app.metrics.scorecard import row_cfg, row_scores
    from macro_app.metrics.transforms import measure

    out = table.copy()
    for col in ("fwd_text", "fwd_label", "fwd_status", "fwd_source", "fwd_when", "fwd_kind"):
        out[col] = ""
    for col in ("fwd_score", "fwd_value", "fwd_actual", "fwd_change", "fwd_better"):
        out[col] = np.nan
    if out.empty:
        return out, np.nan
    rows = {r["code"]: r for r in card["rows"]}
    mapping = {m.get("code"): m for m in ctx.get("forecast_map", [])}
    for i, rec in zip(out.index, out.to_dict("records"), strict=True):
        code = rec["code"]
        ind = catalog[code]
        pts = points_for(
            mapping.get(code),
            path=path,
            targets=ctx["target_series_by_id"],
            frames=frames,
            asof=ctx["asof"],
        )
        if not pts:
            continue
        unit = "%" if ind.unit == "%" else f" {ind.unit}"
        out.loc[i, "fwd_text"] = " · ".join(f"{p.label}: {_fmt(p.value)}{unit}" for p in pts)
        main = primary(pts, ctx["asof"])
        out.loc[i, "fwd_source"] = main.source
        out.loc[i, "fwd_kind"] = main.kind
        out.loc[i, "fwd_when"] = main.label
        out.loc[i, "fwd_value"] = main.value
        cfg = row_cfg(rows[code], ctx["min_points"])
        frame = frames.get(code)
        series = frame["value"] if frame is not None and not frame.empty else pd.Series(dtype=float)
        measured = measure(series, ind.frequency, cfg.get("measure"))
        if (cfg.get("measure") or {}).get("kind", "level") == "level" and not series.dropna().empty:
            actual = float(series.dropna().iloc[-1])
            out.loc[i, "fwd_actual"] = actual
            out.loc[i, "fwd_change"] = main.value - actual
        status = level_of(main.value, measured, cfg, ctx["targets"].get(code, np.nan))
        if status is None:
            continue
        n = len(cuts_of(cfg)) + 1
        from macro_app.metrics.status import labels_of

        idx = LEVELS[n].index(status)
        out.loc[i, "fwd_status"] = status
        out.loc[i, "fwd_label"] = labels_of(cfg, n)[idx]
        out.loc[i, "fwd_score"] = row_scores(rows[code], n, ctx["settings"])[idx]
        now_idx = LEVELS[n].index(rec["status"]) if rec["status"] in LEVELS[n] else None
        if now_idx is not None:  # 1: dự báo tốt hơn hiện tại, -1: xấu hơn, 0: như nhau
            out.loc[i, "fwd_better"] = float(np.sign(now_idx - idx))
    return out, forward_total(out, ctx["settings"]["min_coverage"])
