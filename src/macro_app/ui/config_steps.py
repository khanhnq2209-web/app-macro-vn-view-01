"""Các khối của trang Cấu hình scorecard: danh sách bộ, 4 bước, thanh lưu.

Bản nháp nằm trong session_state["cfg_draft"] (dict bộ cấu hình); chỉ bấm Lưu mới ghi vào kho.
Đổi cấu trúc (thêm/xóa nhóm, dòng) thì tăng `cfg_ver` để các ô nhập nạp lại theo bản nháp.
"""

from __future__ import annotations

import copy
import html
import json

import pandas as pd
import streamlit as st

from macro_app import config_store as cs
from macro_app import fmt
from macro_app import profiles as pf
from macro_app.charts import theme as t
from macro_app.metrics import implications as im
from macro_app.metrics import scorecard as sc
from macro_app.ui import data, editor_gate, profile_store, rule_editor, scorecard_view
from macro_app.ui.threshold_form import changed

STEPS = (
    ("Thông tin", "tên, mô tả, phân khúc"),
    ("Nhóm, chỉ số, tỷ trọng", "mặc định chia đều"),
    ("Mốc từng chỉ số", "xác nhận chỉ số mới"),
    ("Xem lại và lưu", "kiểm tra rồi lưu"),
)
ss = st.session_state
E = html.escape


# --- trạng thái bản nháp ---


def ver() -> int:
    return ss.get("cfg_ver", 0)


def bump() -> None:
    ss["cfg_ver"] = ver() + 1


def unconfirmed() -> set[str]:
    return set(ss.get("cfg_unconf", []))


def set_unconfirmed(keys: set[str]) -> None:
    ss["cfg_unconf"] = sorted(keys)


def open_bo(slug: str, saved: dict, version: int, *, step: int = 1) -> None:
    ss.update(
        cfg_view="wiz",
        cfg_bo=slug,
        cfg_new=False,
        cfg_base=version,
        cfg_draft=copy.deepcopy(saved),
        cfg_step=step,
        cfg_unconf=[],
        cfg_conflict="",
    )
    ss.pop("cfg_sel", None)
    segs = list(saved["segments"])
    ss["cfg_seg"] = segs[0] if segs else None
    bump()


def open_new(source: dict | None, order: int) -> None:
    if source:
        body = copy.deepcopy(source)
        body["name"] = f"{source['name']} (bản sao)"
    else:
        seg = {"name": "Phân khúc 1", "order": 1, "description": "", "rows": [], "pillars": []}
        body = {"name": "", "description": "", "segments": {"phan_khuc_1": seg}}
    body["order"] = order
    ss.update(
        cfg_view="wiz",
        cfg_bo=None,
        cfg_new=True,
        cfg_base=0,
        cfg_draft=body,
        cfg_step=1,
        cfg_unconf=[],
        cfg_conflict="",
    )
    ss.pop("cfg_sel", None)
    ss["cfg_seg"] = next(iter(body["segments"]), None)
    bump()


def is_dirty(saved_all: dict) -> bool:
    draft = ss.get("cfg_draft")
    if not draft:
        return False
    if ss.get("cfg_new"):
        return True
    saved = saved_all.get(ss.get("cfg_bo"))
    return saved is None or pf.is_dirty(draft, saved)


def checks(saved_all: dict, catalog: dict) -> list[dict]:
    draft = ss["cfg_draft"]
    others = [p["name"] for s, p in saved_all.items() if s != ss.get("cfg_bo")]
    present = {
        f"{seg}/{r['code']}"
        for seg, card in draft["segments"].items()
        for r in card.get("rows", [])
    }
    set_unconfirmed(unconfirmed() & present)  # nhóm/phân khúc đã xóa thì bỏ khỏi danh sách chờ
    return pf.check_profile(
        draft, catalog, sc.load_settings(), unconfirmed=unconfirmed(), other_names=others
    )


def evaluate(card: dict) -> dict | None:
    """Điểm hiện tại của một phân khúc (None nếu chưa có dòng tính điểm)."""
    if not any(not r.get("info") for r in card.get("rows", [])):
        return None
    payload = json.dumps(pf.clean_card(card), ensure_ascii=False, sort_keys=True)
    table, total, _ = data.scorecard_eval(payload, data.build_stamp())
    return {"total": total, "table": table}


# --- danh sách bộ ---


def _when(meta: dict | None) -> str:
    if not meta:
        return "Bản gốc trong repo, chưa sửa trên app"
    at = str(meta.get("saved_at", ""))
    at = f"{at[8:10]}/{at[5:7]}/{at[:4]} {at[11:16]}" if len(at) >= 16 else at
    return f"Cập nhật {at} bởi {meta.get('saved_by', '')} · phiên bản {meta.get('version')}"


def _resume_banner(saved_all: dict) -> bool:
    """Bản nháp chưa lưu: mời sửa tiếp hoặc bỏ. True nếu đang có nháp (khóa nút mở bộ khác)."""
    if not (ss.get("cfg_draft") and is_dirty(saved_all)):
        return False
    name = ss["cfg_draft"].get("name") or "(chưa đặt tên)"
    with st.container(border=True):
        c = st.columns([4, 1.4, 1.2], vertical_alignment="center")
        c[0].markdown(f"✏️ Bản nháp chưa lưu: **{fmt.md(name)}**")
        if c[1].button("Tiếp tục sửa", type="primary", key="cfg_resume", width="stretch"):
            ss["cfg_view"] = "wiz"
            st.rerun()
        if c[2].button("Bỏ bản nháp", key="cfg_drop_draft", width="stretch"):
            ss.pop("cfg_draft", None)
            ss["cfg_unconf"] = []
            st.rerun()
    return True


def render_list(store: dict, editor: str) -> None:
    saved_all, meta, default = store["profiles"], store["meta"], store["default"]
    busy = _resume_banner(saved_all)
    hint = "Đang có bản nháp chưa lưu: Tiếp tục sửa hoặc Bỏ bản nháp trước" if busy else None
    top = st.columns([1.4, 4], vertical_alignment="center")
    if top[0].button(
        "＋ Tạo scorecard mới",
        type="primary",
        key="cfg_new_btn",
        width="stretch",
        disabled=busy,
        help=hint,
    ):
        open_new(None, max((p.get("order", 0) for p in saved_all.values()), default=0) + 1)
        st.rerun()
    top[1].caption(
        f"Lưu vào: {store['where']}. Tạo trống, hoặc **Nhân bản** một bộ có sẵn để sửa nhanh."
    )
    for slug, prof in saved_all.items():
        with st.container(border=True, key=f"cfg_bo_{slug}"):
            c = st.columns([3.4, 2.6, 2.6], vertical_alignment="center")
            segs = " · ".join(
                f"{card['name']} ({len(card.get('rows', []))} chỉ số)"
                for card in prof["segments"].values()
            )
            mark = " · **mặc định**" if slug == default else ""
            c[0].markdown(f"**{fmt.md(prof['name'])}**{mark}")
            c[0].caption(f"{prof.get('description', '')}  \n{segs}")
            c[1].caption(_when(meta.get(slug)))
            b = c[2].columns(3)
            if b[0].button(
                "Sửa", key=f"cfg_edit_{slug}", width="stretch", disabled=busy, help=hint
            ):
                open_bo(slug, prof, meta.get(slug, {}).get("version", 0))
                st.rerun()
            if b[1].button(
                "Nhân bản", key=f"cfg_clone_{slug}", width="stretch", disabled=busy, help=hint
            ):
                open_new(prof, max(p.get("order", 0) for p in saved_all.values()) + 1)
                st.rerun()
            with b[2].popover("Thêm", width="stretch"):
                _more_actions(slug, prof, store, editor)
    _deleted_box(store, editor)


def _deleted_box(store: dict, editor: str) -> None:
    gone = cs.deleted(store["rows"])
    if not gone:
        return
    with st.expander(f"Bộ đã xóa ({len(gone)}) · khôi phục được"):
        for slug, info in gone.items():
            c = st.columns([4, 1.4], vertical_alignment="center")
            c[0].markdown(f"{fmt.md(info['name'])} · phiên bản {info['version']}")
            if c[1].button("Khôi phục", key=f"cfg_undelete_{slug}"):
                base = cs.version_of(store["rows"], slug)
                _write(
                    lambda s=slug, v=info["version"], b=base: profile_store.restore(
                        s, v, base=b, by=editor
                    ),
                    f"Đã khôi phục bộ {info['name']}",
                )


def _more_actions(slug: str, prof: dict, store: dict, editor: str) -> None:
    saved_all, meta = store["profiles"], store["meta"]
    version = meta.get(slug, {}).get("version", 0)
    if st.button(
        "Đặt làm mặc định",
        key=f"cfg_default_{slug}",
        disabled=slug == store["default"],
        width="stretch",
    ):
        _write(lambda: profile_store.set_default(slug, by=editor), f"{prof['name']} là bộ mặc định")
    st.markdown("**Lịch sử thay đổi**")
    hist = cs.versions(store["rows"], slug)
    if not hist:
        st.caption("Chưa có lịch sử (đang là bản gốc trong repo).")
    for h in hist[:12]:
        row = st.columns([3, 1.4], vertical_alignment="center")
        label = "đã xóa" if h["status"] == "deleted" else f"phiên bản {h['version']}"
        row[0].caption(f"{label} · {h['at']} · {h['by']}")
        can_restore = h["status"] == "saved" and h["version"] != version
        if can_restore and row[1].button("Khôi phục", key=f"cfg_restore_{slug}_{h['version']}"):
            _write(
                lambda v=h["version"]: profile_store.restore(slug, v, base=version, by=editor),
                f"Đã khôi phục phiên bản {h['version']}",
            )
    st.divider()
    sure = st.checkbox("Tôi muốn xóa bộ này", key=f"cfg_del_ok_{slug}")
    if st.button(
        "Xóa bộ",
        key=f"cfg_del_{slug}",
        disabled=not sure or len(saved_all) <= 1,
        width="stretch",
    ):
        _write(
            lambda: profile_store.delete(slug, base=version, by=editor),
            f"Đã xóa bộ {prof['name']} (khôi phục ở mục Bộ đã xóa)",
        )


def _write(action, message: str) -> None:
    if not editor_gate.save_allowed():
        st.error("Đã lưu quá nhiều lần trong 1 giờ. Thử lại sau.")
        return
    try:
        action()
    except cs.ConflictError as exc:
        st.error(str(exc))
        return
    except Exception as exc:  # mạng, quyền: không in lỗi gốc
        st.error(f"Không lưu được ({type(exc).__name__}). Thử lại sau.")
        return
    editor_gate.note_save()
    st.toast(message)
    st.rerun()


# --- thanh bước ---


def render_stepper(results: list[dict]) -> None:
    ok = [all(r["ok"] for r in results if r["step"] == i + 1) for i in range(4)]
    ok[3] = all(r["ok"] for r in results)
    cols = st.columns(4)
    for i, ((title, hint), col) in enumerate(zip(STEPS, cols, strict=True)):
        mark = "✓" if ok[i] else "!"
        if col.button(
            f"{mark}  {i + 1}. {title}",
            key=f"cfg_step_btn_{i + 1}",
            type="primary" if ss.get("cfg_step", 1) == i + 1 else "secondary",
            width="stretch",
            help=hint,
        ):
            ss["cfg_step"] = i + 1
            st.rerun()


def pick_segment() -> str | None:
    draft = ss["cfg_draft"]
    segs = list(draft["segments"])
    if not segs:
        return None
    if ss.get("cfg_seg") not in segs:
        ss["cfg_seg"] = segs[0]
    if len(segs) == 1:
        return segs[0]
    # Không gắn key: key widget bị Streamlit xóa ở lượt không vẽ widget (bước 1, 4)
    picked = st.segmented_control(
        "Phân khúc",
        segs,
        format_func=lambda s: fmt.md(draft["segments"][s]["name"]),
        default=ss["cfg_seg"],
    )
    if picked and picked != ss["cfg_seg"]:
        ss["cfg_seg"] = picked
        st.rerun()
    return ss["cfg_seg"]


# --- bước 1 ---


def step_info(saved_all: dict) -> None:
    draft = ss["cfg_draft"]
    v = ver()
    with st.container(border=True):
        st.markdown("**1. Thông tin scorecard**")
        draft["name"] = st.text_input(
            "Tên scorecard",
            draft.get("name", ""),
            key=f"cfg_name_{v}",
            placeholder="vd. Theo dõi BĐS · 02",
        ).strip()
        draft["description"] = st.text_area(
            "Mô tả", draft.get("description", ""), key=f"cfg_desc_{v}", height=68
        )
        st.caption(
            "Tỷ trọng mặc định **chia đều**: các nhóm bằng nhau, các chỉ số trong nhóm bằng nhau. "
            "Ghi đè ở bước 2 nếu cần."
        )
    with st.container(border=True):
        st.markdown("**Phân khúc**")
        segs = draft["segments"]
        for slug, card in list(segs.items()):
            c = st.columns([3, 2, 1.2], vertical_alignment="bottom")
            new = c[0].text_input("Tên phân khúc", card["name"], key=f"cfg_segname_{slug}_{v}")
            if new.strip() and new.strip() != card["name"]:
                segs[slug] = {**card, "name": new.strip()}
            n_groups = len(pf.clean_pillars(card))
            c[1].caption(f"{n_groups} nhóm · {len(card.get('rows', []))} chỉ số")
            if c[2].button("Xóa", key=f"cfg_segdel_{slug}_{v}", disabled=len(segs) <= 1):
                ss["cfg_draft"] = pf.remove_segment(draft, slug)
                bump()
                st.rerun()
        c = st.columns([3, 3, 1.2], vertical_alignment="bottom")
        name = c[0].text_input("Thêm phân khúc", key=f"cfg_segnew_{v}", placeholder="vd. Văn phòng")
        sources = {"": "(trống)"}
        for pslug, prof in {**saved_all, "_draft": draft}.items():
            for sslug, card in prof["segments"].items():
                sources[f"{pslug}/{sslug}"] = (
                    f"Sao chép: {prof.get('name') or 'bộ này'} · {card['name']}"
                )
        src = c[1].selectbox(
            "Bắt đầu từ", list(sources), format_func=sources.get, key=f"cfg_segsrc_{v}"
        )
        if c[2].button("Thêm", key=f"cfg_segadd_{v}", disabled=not name.strip()):
            source = None
            if src:
                pslug, sslug = src.split("/", 1)
                source = ({**saved_all, "_draft": draft}[pslug])["segments"][sslug]
            try:
                ss["cfg_draft"], ss["cfg_seg"] = pf.add_segment(draft, name, source)
            except ValueError as exc:
                st.error(str(exc))
            else:
                bump()
                st.rerun()


# --- bước 2 ---


def _shares(card: dict, catalog: dict) -> tuple[dict, dict]:
    """(tỷ trọng nhóm, tỷ trọng trong bộ của từng dòng), dạng phân số."""
    eff = sc.weights(card.get("rows", []), catalog, pf.clean_pillars(card))
    group: dict[str, float] = {}
    for r in card.get("rows", []):
        if r["code"] in eff:
            group[r.get("pillar")] = group.get(r.get("pillar"), 0.0) + eff[r["code"]]
    return group, eff


def _num(  # noqa: PLR0913 - ô nhập cần nhãn, giá trị, gợi ý, khóa và kiểu nhãn
    box, label: str, value, placeholder: str, key: str, *, hide_label: bool = False
):
    return box.number_input(
        label,
        value=float(value) if value is not None else None,
        min_value=0.0,
        max_value=100.0,
        step=1.0,
        format="%.1f",
        placeholder=placeholder,
        key=key,
        label_visibility="collapsed" if hide_label else "visible",
    )


def step_groups(catalog: dict) -> None:
    seg = pick_segment()
    if seg is None:
        st.info("Chưa có phân khúc. Thêm ở bước 1.")
        return
    draft, v = ss["cfg_draft"], ver()
    card = draft["segments"][seg]
    group, eff = _shares(card, catalog)
    pillars = pf.clean_pillars(card)
    with st.container(border=True):
        top = st.columns([4, 1.4], vertical_alignment="center")
        top[0].markdown(
            "**2. Nhóm, chỉ số và tỷ trọng.** Mặc định **chia đều**. Để ô trống = tự chia phần còn "
            "lại; nhập số = giữ nguyên."
        )
        if top[1].button("Chia đều lại tất cả", key=f"cfg_eq_{seg}_{v}", width="stretch"):
            draft["segments"][seg] = pf.reset_weights(card)
            bump()
            st.rerun()
        colors = [*t.CATEGORICAL, t.MUTED]
        bar = "".join(
            f'<i style="width:{group.get(p["name"], 0) * 100:.2f}%;background:{colors[min(i, 5)]}" '
            f'title="{E(p["name"])} {fmt.number(group.get(p["name"], 0) * 100, 1)}%"></i>'
            for i, p in enumerate(pillars)
        )
        st.html(f'<div class="cfg-meter">{bar}</div>')
        for err in sc.weight_errors(card, catalog):
            st.warning(err, icon="⚠️")
    used = {r["code"] for r in card.get("rows", [])}
    for gi, p in enumerate(pillars):
        _group_box(seg, card, gi, p, group=group, eff=eff, used=used, catalog=catalog, v=v)
    with st.container(border=True):
        c = st.columns([4, 1.4], vertical_alignment="bottom")
        name = c[0].text_input(
            "Thêm nhóm", key=f"cfg_gnew_{seg}_{v}", placeholder="vd. Sản xuất và thương mại"
        )
        if c[1].button(
            "＋ Thêm nhóm", key=f"cfg_gadd_{seg}_{v}", disabled=not name.strip(), width="stretch"
        ):
            try:
                draft["segments"][seg] = pf.add_pillar(card, name)
            except ValueError as exc:
                st.error(str(exc))
            else:
                bump()
                st.rerun()


def _group_box(seg, card, gi, p, *, group, eff, used, catalog, v) -> None:  # noqa: PLR0913
    draft = ss["cfg_draft"]
    name = p["name"]
    rows = [r for r in card.get("rows", []) if r.get("pillar") == name]
    with st.container(border=True):
        h = st.columns([3, 1.5, 2, 1.6, 1.2], vertical_alignment="bottom")
        new = h[0].text_input("Tên nhóm", name, key=f"cfg_gname_{seg}_{gi}_{v}")
        w = _num(
            h[1],
            "Tỷ trọng nhóm (%)",
            p.get("weight"),
            f"tự chia {fmt.number(group.get(name, 0) * 100, 1)}",
            f"cfg_gw_{seg}_{gi}_{v}",
        )
        h[2].caption(
            ("đã đặt" if p.get("weight") is not None else "tự chia đều") + f" · {len(rows)} chỉ số"
        )
        if h[3].button("Chia đều trong nhóm", key=f"cfg_geq_{seg}_{gi}_{v}", width="stretch"):
            draft["segments"][seg] = pf.reset_weights(card, name)
            bump()
            st.rerun()
        if h[4].button("✕ Xóa nhóm", key=f"cfg_gdel_{seg}_{gi}_{v}", width="stretch"):
            draft["segments"][seg] = pf.remove_pillar(card, name)
            bump()
            st.rerun()
        if new.strip() and new.strip() != name:
            try:
                draft["segments"][seg] = pf.rename_pillar(card, name, new)
            except ValueError as exc:
                st.error(str(exc))
            else:
                bump()
                st.rerun()
        if w != p.get("weight"):
            draft["segments"][seg] = pf.set_pillar_weight(card, name, w)
            st.rerun()
        for r in rows:
            ctx = {"gshare": group.get(name, 0.0), "eff": eff, "catalog": catalog, "v": v}
            _row_line(seg, card, r, ctx)
        free = sorted((c for c in catalog if c not in used), key=lambda c: catalog[c].name)
        a = st.columns([4, 1.4], vertical_alignment="bottom")
        code = a[0].selectbox(
            "Thêm chỉ số vào nhóm",
            ["", *free],
            format_func=lambda c: catalog[c].name if c else "Chọn chỉ số…",
            key=f"cfg_radd_{seg}_{gi}_{v}",
        )
        if a[1].button(
            "Thêm", key=f"cfg_raddbtn_{seg}_{gi}_{v}", disabled=not code, width="stretch"
        ):
            row = rule_editor.starter_row(code, catalog[code], data.series(code))
            draft["segments"][seg] = pf.add_row(card, row, name)
            set_unconfirmed(unconfirmed() | {f"{seg}/{code}"})
            bump()
            st.rerun()


def _row_line(seg: str, card: dict, r: dict, ctx: dict) -> None:
    """Một dòng chỉ số ở bước 2. ctx: gshare (tỷ trọng nhóm), eff, catalog, v."""
    gshare, eff, catalog, v = ctx["gshare"], ctx["eff"], ctx["catalog"], ctx["v"]
    draft = ss["cfg_draft"]
    ind = catalog.get(r["code"])
    c = st.columns([4, 1.5, 1.3, 0.5], vertical_alignment="bottom")
    c[0].markdown(
        f"{ind.name if ind else r['code']}"
        + ("  \n:gray[chỉ tham khảo, không vào điểm]" if r.get("info") else "")
    )
    if r.get("info") or ind is None:
        c[1].caption("Tham khảo")
    else:
        inside = eff.get(r["code"], 0) / gshare if gshare else 0
        w = _num(
            c[1],
            "Trong nhóm (%)",
            r.get("weight"),
            f"tự chia {fmt.number(inside * 100, 1)} %",
            f"cfg_rw_{seg}_{r['code']}_{v}",
            hide_label=True,
        )
        c[2].caption(f"trong bộ {fmt.number(eff.get(r['code'], 0) * 100, 1)}%")
        if w != r.get("weight"):
            draft["segments"][seg] = pf.set_row_weight(card, r["code"], w)
            st.rerun()
    if c[3].button("✕", key=f"cfg_rdel_{seg}_{r['code']}_{v}", help="Bỏ chỉ số khỏi nhóm"):
        draft["segments"][seg] = pf.remove_row(card, r["code"])
        set_unconfirmed(unconfirmed() - {f"{seg}/{r['code']}"})
        bump()
        st.rerun()


# --- bước 3 ---


def step_rules(catalog: dict) -> None:
    seg = pick_segment()
    if seg is None:
        st.info("Chưa có phân khúc. Thêm ở bước 1.")
        return
    card = ss["cfg_draft"]["segments"][seg]
    rows = [r for r in card.get("rows", []) if r["code"] in catalog]
    if not rows:
        st.info("Phân khúc chưa có chỉ số. Thêm nhóm và chỉ số ở bước 2.")
        return
    if ss.get("cfg_sel") not in [r["code"] for r in rows]:
        ss["cfg_sel"] = rows[0]["code"]
    left, right = st.columns([1, 2.2], gap="large")
    with left, st.container(border=True):
        _rule_list(seg, card, rows, catalog)
    with right:
        _rule_panel(seg, card, next(r for r in rows if r["code"] == ss["cfg_sel"]), catalog)


def _rule_list(seg: str, card: dict, rows: list[dict], catalog: dict) -> None:
    """Danh sách chỉ số theo nhóm; ⚠ = chưa xác nhận mốc, · = chỉ tham khảo."""
    pending, v = unconfirmed(), ver()
    for p in pf.clean_pillars(card):
        part = [r for r in rows if r.get("pillar") == p["name"]]
        if part:
            st.caption(f"**{p['name']}**")
        for r in part:
            flag = "⚠ " if f"{seg}/{r['code']}" in pending else ("· " if r.get("info") else "")
            if st.button(
                f"{flag}{catalog[r['code']].name}",
                key=f"cfg_sel_{seg}_{r['code']}_{v}",
                type="primary" if r["code"] == ss["cfg_sel"] else "tertiary",
                width="stretch",
                help="Chưa xác nhận mốc" if flag.startswith("⚠") else None,
            ):
                ss["cfg_sel"] = r["code"]
                st.rerun()


def _set_info(card: dict, code: str, info: bool) -> dict:
    rows = [
        ({**r, "info": True} if info else {k: x for k, x in r.items() if k != "info"})
        if r["code"] == code
        else r
        for r in card["rows"]
    ]
    return {**card, "rows": rows}


def _rule_panel(seg: str, card: dict, row: dict, catalog: dict) -> None:
    draft, v, pending = ss["cfg_draft"], ver(), unconfirmed()
    code = row["code"]
    ind = catalog[code]
    key_unconf = f"{seg}/{code}"
    st.markdown(f"#### {ind.name}")
    st.caption(f"{ind.source} · [Xem chi tiết chỉ số](detail?code={code})")
    names = [p["name"] for p in pf.clean_pillars(card)]
    c = st.columns([2, 2], vertical_alignment="bottom")
    moved = c[0].selectbox(
        "Nhóm",
        names,
        index=names.index(row["pillar"]) if row.get("pillar") in names else 0,
        key=f"cfg_mv_{seg}_{code}_{v}",
    )
    info = c[1].checkbox(
        "Chỉ tham khảo (không vào điểm)", bool(row.get("info")), key=f"cfg_info_{seg}_{code}_{v}"
    )
    if moved != row.get("pillar") or info != bool(row.get("info")):
        new = pf.move_row(card, code, moved) if moved != row.get("pillar") else card
        draft["segments"][seg] = _set_info(new, code, info)
        bump()
        st.rerun()
    if key_unconf in pending:
        st.warning(
            "Chỉ số mới thêm: mốc dưới đây là **gợi ý ban đầu**. Kiểm tra rồi bấm Xác nhận mốc."
        )
    new_cfg = rule_editor.edit(code, row, key=f"cfg_rule_{seg}_{code}_{v}", with_scores=True)
    if new_cfg is not None and changed(new_cfg, row):
        draft["segments"][seg] = pf.set_row_cfg(card, code, new_cfg)
        set_unconfirmed(pending - {key_unconf})
    if key_unconf in pending and st.button(
        "Xác nhận mốc", type="primary", key=f"cfg_conf_{seg}_{code}"
    ):
        set_unconfirmed(pending - {key_unconf})
        st.rerun()
    _note_editor(seg, card, row, v)
    with st.container(border=True):
        st.markdown(":red[**Vùng nguy hiểm**]")
        if st.button("Bỏ chỉ số khỏi scorecard", key=f"cfg_rowdel_{seg}_{code}_{v}"):
            draft["segments"][seg] = pf.remove_row(card, code)
            set_unconfirmed(pending - {key_unconf})
            ss.pop("cfg_sel", None)
            bump()
            st.rerun()
        st.caption("Chỉ tác động bản nháp. Bấm “Bỏ thay đổi” để hoàn tác.")


def _note_editor(seg: str, card: dict, row: dict, v: int) -> None:
    """Hàm ý hiện trên trang Scorecard khi chỉ số bất lợi / thuận lợi; trống = câu mặc định."""
    code = row["code"]
    default = im.default_note(im.load_notes(), seg, code)
    with st.expander("AI comment hiện trên Scorecard"):
        if code in im.FED_CODES:
            st.caption(
                "Lãi Fed: hàm ý tự sinh từ FedWatch (số lần dự báo tăng / giảm 12 tháng tới)."
            )
            return
        bad = st.text_area(
            "Khi bất lợi",
            row.get("note_bad", ""),
            placeholder=default.get("bad", "Chưa có câu mặc định"),
            key=f"cfg_nb_{seg}_{code}_{v}",
            height=70,
        )
        good = st.text_area(
            "Khi thuận lợi",
            row.get("note_good", ""),
            placeholder=default.get("good", "Chưa có câu mặc định"),
            key=f"cfg_ng_{seg}_{code}_{v}",
            height=70,
        )
        st.caption(
            "Để trống = dùng câu mặc định (chữ mờ trong ô). Mức trung tính không hiện hàm ý."
        )
        if bad.strip() != row.get("note_bad", "") or good.strip() != row.get("note_good", ""):
            ss["cfg_draft"]["segments"][seg] = pf.set_row_notes(card, code, bad, good)


# --- bước 4 ---


def step_review(results: list[dict], catalog: dict) -> None:
    draft = ss["cfg_draft"]
    with st.container(border=True):
        st.markdown("**4. Kiểm tra trước khi lưu**")
        for i, r in enumerate(results):
            c = st.columns([5, 1.3], vertical_alignment="center")
            icon = ":green[✓]" if r["ok"] else ":red[!]"
            c[0].markdown(f"{icon} {r['text']}")
            if not r["ok"] and c[1].button(f"Sửa ở bước {r['step']}", key=f"cfg_fix_{i}"):
                ss["cfg_step"] = r["step"]
                st.rerun()
    for card in draft["segments"].values():
        with st.container(border=True):
            ev = evaluate(card)
            head = f"**{card['name']}**"
            if ev:
                tot = ev["total"]
                score = fmt.signed(tot["score"], 2) if pd.notna(tot["score"]) else "—"
                head += f" · điểm xem trước {score} · {tot['rating']} · độ phủ {fmt.number(tot['coverage'] * 100, 0)}%"
            st.markdown(head)
            group, eff = _shares(card, catalog)
            lines = []
            for p in pf.clean_pillars(card):
                rows = [r for r in card.get("rows", []) if r.get("pillar") == p["name"]]
                items = ", ".join(
                    f"{catalog[r['code']].name}"
                    + (
                        " (tham khảo)"
                        if r.get("info")
                        else f" {fmt.number(eff.get(r['code'], 0) * 100, 1)}%"
                    )
                    for r in rows
                    if r["code"] in catalog
                )
                lines.append(
                    f"- **{p['name']}** {fmt.number(group.get(p['name'], 0) * 100, 1)}%: {items or '(trống)'}"
                )
            st.markdown("\n".join(lines) or "(chưa có nhóm)")


# --- thanh lưu dính đáy ---


def render_bar(store: dict, results: list[dict], editor: str) -> None:
    saved_all = store["profiles"]
    draft = ss["cfg_draft"]
    dirty = is_dirty(saved_all)
    ok = all(r["ok"] for r in results)
    seg = ss.get("cfg_seg")
    with st.container(key="cfg_bar"):
        c = st.columns([4.2, 1.2, 1.1, 1.1, 1.2], vertical_alignment="center")
        c[0].html(_bar_summary(saved_all, draft, seg, dirty=dirty, results=results))
        if c[1].button(
            "Hủy tạo" if ss.get("cfg_new") else "Bỏ thay đổi",
            key="cfg_discard",
            disabled=not dirty,
            width="stretch",
        ):
            if ss.get("cfg_new"):
                ss["cfg_view"] = "list"
                ss.pop("cfg_draft", None)
            else:
                slug = ss["cfg_bo"]
                version = store["meta"].get(slug, {}).get("version", 0)
                open_bo(slug, saved_all[slug], version, step=ss.get("cfg_step", 1))
            st.rerun()
        step = ss.get("cfg_step", 1)
        if c[2].button("← Quay lại", key="cfg_back", disabled=step == 1, width="stretch"):
            ss["cfg_step"] = step - 1
            st.rerun()
        if c[3].button("Tiếp →", key="cfg_next", disabled=step == 4, width="stretch"):
            ss["cfg_step"] = step + 1
            st.rerun()
        if c[4].button(
            "Lưu",
            type="primary",
            key="cfg_save",
            disabled=not (dirty and ok),
            width="stretch",
            help=None if ok else "Còn mục chưa đạt ở bước 4",
        ):
            save(saved_all, editor)


def _bar_summary(saved_all, draft, seg, *, dirty, results) -> str:
    if not seg or seg not in draft["segments"]:
        return '<div class="cfg-sum">Chưa có phân khúc.</div>'
    card = draft["segments"][seg]
    now = evaluate(card)
    saved = saved_all.get(ss.get("cfg_bo")) if not ss.get("cfg_new") else None
    before = evaluate(saved["segments"][seg]) if saved and seg in saved["segments"] else None

    def score(ev):
        return fmt.signed(ev["total"]["score"], 2) if ev and pd.notna(ev["total"]["score"]) else "—"

    chip = scorecard_view.rating_chip(now["total"]["rating"]) if now else ""
    name = E(card["name"])
    if before and dirty:
        head = f"Điểm {name}: <b>{score(before)}</b> → <b>{score(now)}</b> {chip}"
    else:
        head = f"Điểm {name}: <b>{score(now)}</b> {chip}"
    notes = []
    if before and now:
        b = before["table"].set_index("code")["label"]
        for _, r in now["table"].iterrows():
            if r["code"] in b.index and b[r["code"]] != r["label"] and not r.get("info"):
                notes.append(
                    f"{E(r['code'])}: {E(str(b[r['code']]))} → <b>{E(str(r['label']))}</b>"
                )
    bad = [r["text"] for r in results if not r["ok"]]
    tail = (
        f"Chưa lưu được: {E(bad[0])}"
        if bad
        else ("Có thay đổi chưa lưu." if dirty else "Không có thay đổi.")
    )
    if ss.get("cfg_conflict"):
        tail = f'<span style="color:{t.STATUS_COLORS["red"][1]}">{E(ss["cfg_conflict"])}</span>'
    chg = "<br>".join(notes[:4])
    return f'<div class="cfg-sum">{head}<div class="cfg-chg">{tail}{"<br>" + chg if chg else ""}</div></div>'


def save(saved_all: dict, editor: str) -> None:
    if not editor_gate.save_allowed():
        st.error("Đã lưu quá nhiều lần trong 1 giờ. Thử lại sau.")
        return
    draft = ss["cfg_draft"]
    try:
        if ss.get("cfg_new"):
            slug = cs.new_slug(draft["name"], profile_store.fresh_rows(), saved_all)
        else:
            slug = ss["cfg_bo"]
        version = profile_store.save(slug, draft, base=ss.get("cfg_base", 0), by=editor)
    except cs.ConflictError as exc:
        ss["cfg_conflict"] = str(exc)
        st.rerun()
    except Exception as exc:  # mạng, quyền, quá lớn
        ss["cfg_conflict"] = f"Không lưu được ({type(exc).__name__}). Bản nháp vẫn giữ, thử lại."
        st.rerun()
    editor_gate.note_save()
    ss.update(cfg_bo=slug, cfg_new=False, cfg_base=version, cfg_conflict="", sc_profile=slug)
    st.toast(f"Đã lưu {draft['name']} (phiên bản {version})")
    st.rerun()
