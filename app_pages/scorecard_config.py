"""Cấu hình scorecard: bộ → phân khúc → chỉ số → ngưỡng từng chỉ số.

Mọi thay đổi vào bản nháp (giữ trong phiên), điểm nháp tính lại ngay; bấm Lưu mới ghi vào
config/profiles/. Trang Scorecard chỉ hiện bản đã lưu.
"""

import json

import pandas as pd
import streamlit as st

from macro_app import fmt
from macro_app import profiles as pf
from macro_app.build import rescore
from macro_app.ui import components as ui
from macro_app.ui import data, rule_editor, scorecard_view, sidebar
from macro_app.ui.threshold_form import changed

st.title("Cấu hình scorecard")
if not sidebar.is_admin():
    st.info("Chỉ sửa được khi chạy app trên máy (APP_MODE=admin).")
    st.stop()

ss = st.session_state
saved_all = pf.load_profiles()
if not saved_all:
    st.info("Chưa có bộ cấu hình nào trong config/profiles/.")
    st.stop()
drafts: dict = ss.setdefault("sc_drafts", {})
ss.setdefault("sc_ver", 0)
catalog = data.catalog_map()
default = pf.default_profile()
NEW_PILLAR = "＋ Trụ cột mới…"


def put(slug: str, new_profile: dict) -> None:
    """Ghi vào bản nháp rồi vẽ lại."""
    drafts[slug] = new_profile
    st.rerun()


def reload_widgets() -> None:
    ss["sc_ver"] += 1  # đổi khóa ô nhập → nạp lại từ bản nháp/bản đã lưu


def refresh(message: str) -> None:
    with st.spinner("Đang tính lại…"):
        rescore()
    st.cache_data.clear()
    reload_widgets()
    st.toast(message)
    st.rerun()


def is_dirty(slug: str) -> bool:
    return slug in drafts and pf.is_dirty(drafts[slug], saved_all[slug])


def evaluate(card: dict):
    payload = json.dumps(pf.clean_card(card), ensure_ascii=False, sort_keys=True)
    return data.scorecard_eval(payload, data.build_stamp())


# ---------------- Chọn bộ, phân khúc ----------------
options = list(saved_all)
if "cfg_pending_profile" in ss:
    ss["cfg_profile"] = ss.pop("cfg_pending_profile")
if ss.get("cfg_profile") not in options:
    ss["cfg_profile"] = default
top = st.columns([2, 3, 1])
profile = top[0].selectbox(
    "Bộ cấu hình",
    options,
    format_func=lambda s: (
        saved_all[s]["name"]
        + (" · mặc định" if s == default else "")
        + (" · chưa lưu" if is_dirty(s) else "")
    ),
    key="cfg_profile",
)
saved = saved_all[profile]
current = drafts.get(profile, saved)
ver = ss["sc_ver"]
segments = list(current["segments"])
seg_key = f"cfg_seg_{profile}"
if "cfg_pending_segment" in ss:
    ss[seg_key] = ss.pop("cfg_pending_segment")
if ss.get(seg_key) not in segments:
    ss[seg_key] = segments[0] if segments else None
with top[1]:
    segment = (
        st.segmented_control(
            "Phân khúc",
            segments,
            format_func=lambda s: current["segments"][s]["name"],
            key=seg_key,
        )
        if segments
        else None
    ) or (segments[0] if segments else None)

with top[2].popover("Phân khúc", width="stretch"):
    st.markdown("**Thêm phân khúc**")
    sources = {"": "(trống)"}
    for pslug, prof in saved_all.items():
        for sslug, c in (current if pslug == profile else prof)["segments"].items():
            sources[f"{pslug}/{sslug}"] = f"Sao chép: {prof['name']} · {c['name']}"
    new_seg = st.text_input("Tên phân khúc mới", key="cfg_new_seg_name")
    src = st.selectbox("Bắt đầu từ", list(sources), format_func=sources.get, key="cfg_new_seg_src")
    if st.button("Thêm phân khúc", disabled=not new_seg.strip(), key="cfg_new_seg"):
        source = None
        if src:
            pslug, sslug = src.split("/", 1)
            source = (current if pslug == profile else saved_all[pslug])["segments"][sslug]
        try:
            new_profile, slug = pf.add_segment(current, new_seg, source)
        except ValueError as exc:
            st.error(str(exc))
        else:
            ss["cfg_pending_segment"] = slug
            put(profile, new_profile)
    if segment:
        card = current["segments"][segment]
        st.divider()
        st.markdown(f"**Phân khúc {card['name']}**")
        name = st.text_input("Tên", card["name"], key=f"cfg_seg_name_{profile}_{segment}_{ver}")
        desc = st.text_area(
            "Mô tả", card["description"], key=f"cfg_seg_desc_{profile}_{segment}_{ver}"
        )
        if (name.strip() and name.strip() != card["name"]) or desc != card["description"]:
            new_card = {**card, "name": name.strip() or card["name"], "description": desc}
            put(profile, pf.update_segment(current, segment, new_card))
        if st.button(f"Xóa phân khúc {card['name']}", key=f"cfg_seg_del_{profile}_{segment}"):
            put(profile, pf.remove_segment(current, segment))

# ---------------- Thanh lưu ----------------
dirty = is_dirty(profile)
bar = st.columns([4, 1, 1, 1.2])
if segment:
    _, total_now, _ = evaluate(current["segments"][segment])
    saved_card = saved["segments"].get(segment)
    shown = fmt.signed(total_now["score"], 2) if pd.notna(total_now["score"]) else "—"
    rating = total_now["rating"]
    if pd.isna(total_now["score"]) and pd.notna(total_now.get("last_score")):
        shown = f"{fmt.signed(total_now['last_score'], 2)} (tháng {total_now['last_date']:%m/%Y})"
        rating = total_now["last_rating"]
    compare = ""
    if dirty and saved_card is not None:
        _, total_saved, _ = evaluate(saved_card)
        value = total_saved["score"]
        if pd.isna(value):
            value = total_saved.get("last_score")
        compare = f" · bản đã lưu {fmt.signed(value, 2)}" if pd.notna(value) else ""
    label = "Điểm bản nháp" if dirty else "Điểm"
    warn = ' · <b style="color:#B3261E">có thay đổi chưa lưu</b>' if dirty else ""
    bar[0].html(
        f'<div class="cfg-bar">{label} <b>{shown}</b>{scorecard_view.rating_chip(rating)}'
        f"{compare}{warn}</div>"
    )
if bar[1].button("Lưu", type="primary", disabled=not dirty, key="cfg_save", width="stretch"):
    pf.write_profile(profile, drafts.pop(profile))
    refresh(f"Đã lưu bộ {saved['name']}")
if bar[2].button("Bỏ thay đổi", disabled=not dirty, key="cfg_discard", width="stretch"):
    drafts.pop(profile, None)
    reload_widgets()
    st.rerun()
with bar[3].popover("Quản lý bộ", width="stretch"):
    st.markdown(f"**Bộ {saved['name']}**")
    name = st.text_input("Tên bộ", current["name"], key=f"cfg_prof_name_{profile}_{ver}")
    pdesc = st.text_area("Mô tả bộ", current["description"], key=f"cfg_prof_desc_{profile}_{ver}")
    if (name.strip() and name.strip() != current["name"]) or pdesc != current["description"]:
        put(profile, {**current, "name": name.strip() or current["name"], "description": pdesc})
    if st.button("Đặt làm bộ mặc định", disabled=profile == default, key="cfg_default"):
        pf.set_default_profile(profile)
        st.toast(f"{saved['name']} là bộ mặc định")
        st.rerun()
    st.divider()
    st.markdown("**Lưu thành bộ mới** (sao chép bộ đang mở, kể cả thay đổi chưa lưu)")
    copy_name = st.text_input("Tên bộ mới", key="cfg_copy_name")
    b1, b2 = st.columns(2)
    if b1.button("Lưu thành bộ mới", disabled=not copy_name.strip(), key="cfg_copy"):
        try:
            slug = pf.create_profile(copy_name, current["description"], current)
        except ValueError as exc:
            st.error(str(exc))
        else:
            drafts.pop(profile, None)  # bộ gốc giữ như lần lưu trước
            ss["cfg_pending_profile"] = slug
            refresh(f"Đã tạo bộ {copy_name.strip()}")
    if b2.button("Tạo bộ trống", disabled=not copy_name.strip(), key="cfg_blank"):
        try:
            slug = pf.create_profile(copy_name)
        except ValueError as exc:
            st.error(str(exc))
        else:
            ss["cfg_pending_profile"] = slug
            refresh(f"Đã tạo bộ trống {copy_name.strip()}")
    st.divider()
    sure = st.checkbox("Tôi muốn xóa bộ này", key=f"cfg_del_ok_{profile}")
    if st.button("Xóa bộ", disabled=not sure or len(saved_all) == 1, key="cfg_delete"):
        pf.delete_profile(profile)
        drafts.pop(profile, None)
        ss["cfg_pending_profile"] = pf.default_profile()
        refresh(f"Đã xóa bộ {saved['name']}")

if not segment:
    st.info("Bộ này chưa có phân khúc. Thêm ở nút Phân khúc.")
    st.stop()

# ---------------- Bảng chỉ số (trái) + bộ sửa (phải) ----------------
card = current["segments"][segment]
table, _, _ = evaluate(card)
info = table.set_index("code") if not table.empty else pd.DataFrame()
pillars = list(dict.fromkeys(r.get("pillar") or catalog[r["code"]].group for r in card["rows"]))
left, right = st.columns([1, 1], gap="large")

with left:
    rows = []
    for r in card["rows"]:
        if r["code"] not in catalog:
            continue
        ind = catalog[r["code"]]
        rec = info.loc[r["code"]] if r["code"] in info.index else None
        unit = (
            "%"
            if (r.get("measure") or {}).get("kind") in ("pct_change", "ytd_pct", "sum12_pct")
            else ""
        )
        now = (
            f"{fmt.number(rec['measured'], 2)}{unit}"
            if rec is not None and pd.notna(rec["measured"])
            else "—"
        )
        level = rec["label"] if rec is not None and rec["label"] else "—"
        if rec is not None and bool(rec["stale"]):
            level += " (số cũ)"
        rows.append(
            {
                "Trụ cột": r.get("pillar") or ind.group,
                "Chỉ số": ind.name,
                "Hiện tại": now,
                "Mức": level,
                "_code": r["code"],
            }
        )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["_order"] = frame["Trụ cột"].map({p: i for i, p in enumerate(pillars)})
        frame = frame.sort_values("_order", kind="stable").reset_index(drop=True)
    pick_key = f"cfg_pick_{profile}_{segment}"
    event = st.dataframe(
        frame.drop(columns=["_code", "_order"], errors="ignore"),
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key=f"cfg_table_{profile}_{segment}_{ver}",
        column_config={
            "Trụ cột": st.column_config.TextColumn(width=115),
            "Chỉ số": st.column_config.TextColumn(width=190),
            "Hiện tại": st.column_config.TextColumn(width=70),
            "Mức": st.column_config.TextColumn(width=95),
        },
    )
    picked = event.selection.rows if event and event.selection else []
    if picked:
        ss[pick_key] = frame.loc[picked[0], "_code"]
    codes = frame["_code"].tolist() if not frame.empty else []
    if ss.get(pick_key) not in codes:
        ss[pick_key] = codes[0] if codes else None
    st.caption(
        "Bấm một dòng để sửa ngưỡng. Trọng số chia đều theo trụ cột, rồi chia đều trong trụ cột."
    )
    with st.popover("＋ Thêm chỉ số"):
        used = {r["code"] for r in card["rows"]}
        choices = sorted((c for c in catalog if c not in used), key=lambda c: catalog[c].name)
        add_code = st.selectbox(
            "Chỉ số", choices, format_func=lambda c: catalog[c].name, key="cfg_add_code"
        )
        add_pillar = st.selectbox("Trụ cột", [*pillars, NEW_PILLAR], key="cfg_add_pillar")
        new_pillar = (
            st.text_input("Tên trụ cột mới", key="cfg_add_pillar_new")
            if add_pillar == NEW_PILLAR
            else ""
        )
        pillar_name = new_pillar.strip() if add_pillar == NEW_PILLAR else add_pillar
        if st.button("Thêm", disabled=not add_code or not pillar_name, key="cfg_add"):
            row = rule_editor.starter_row(add_code, catalog[add_code], data.series(add_code))
            row["pillar"] = pillar_name
            ss[pick_key] = add_code
            put(
                profile, pf.update_segment(current, segment, {**card, "rows": [*card["rows"], row]})
            )

with right:
    code = ss.get(pick_key)
    if not code:
        st.info("Phân khúc chưa có chỉ số. Bấm ＋ Thêm chỉ số.")
    else:
        row = next(r for r in card["rows"] if r["code"] == code)
        ind = catalog[code]
        st.markdown(f"#### {ind.name}")
        st.caption(f"{ind.source} · [Xem chi tiết chỉ số](detail?code={code})")
        p1, p2 = st.columns([3, 1])
        pillar_now = row.get("pillar") or ind.group
        options_p = [*dict.fromkeys([pillar_now, *pillars]), NEW_PILLAR]
        chosen = p1.selectbox(
            "Trụ cột",
            options_p,
            index=options_p.index(pillar_now),
            key=f"cfg_pillar_{profile}_{segment}_{code}_{ver}",
        )
        if chosen == NEW_PILLAR:
            typed = p1.text_input(
                "Tên trụ cột mới", key=f"cfg_pillar_new_{profile}_{segment}_{code}"
            )
            chosen = typed.strip() or pillar_now
        if chosen != pillar_now:
            new_rows = [{**r, "pillar": chosen} if r["code"] == code else r for r in card["rows"]]
            put(profile, pf.update_segment(current, segment, {**card, "rows": new_rows}))
        p2.write("")
        if p2.button("Xóa dòng", key=f"cfg_drop_{profile}_{segment}_{code}", width="stretch"):
            new_rows = [r for r in card["rows"] if r["code"] != code]
            ss.pop(pick_key, None)
            put(profile, pf.update_segment(current, segment, {**card, "rows": new_rows}))
        new_cfg = rule_editor.edit(
            code, row, key=f"cfg_rule_{profile}_{segment}_{code}_{ver}", with_scores=True
        )
        if new_cfg is not None and changed(new_cfg, row):
            put(profile, pf.update_segment(current, segment, pf.set_row_cfg(card, code, new_cfg)))
ui.footer()
