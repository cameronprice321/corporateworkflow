"""Corporate Workflow System — main Streamlit application."""
import json
import sys
import uuid
from pathlib import Path
from datetime import datetime

import streamlit as st
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).parent))
from skills.loader import load_skills

st.set_page_config(
    page_title="Corporate Workflow",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

ENTITY_TYPES = ["Company", "Trust", "SMSF", "Individual", "Partnership", "Foundation", "Other"]
TRUST_SUBTYPES = ["Discretionary (Family)", "Unit", "Hybrid", "Bare", "Testamentary"]
COMPANY_SUBTYPES = ["Pty Ltd", "Ltd", "Shelf", "Holding Co", "Trading Co"]
REL_TYPES = ["Owns (%)", "Trustee of", "Beneficiary of", "Director of", "Lender to", "Guarantor of"]
FLOW_FREQ = ["Weekly", "Fortnightly", "Monthly", "Quarterly", "Annual", "One-off"]

STRUCTURE_TEMPLATES = {
    "Trading Co → Holding Co → Family Trust": {
        "description": (
            "Classic Australian profit-protection structure. Trading company earns income, "
            "pays 25% company tax, then dividends flow (fully franked) to a holding company "
            "tax-free (inter-company dividend rules >10% ownership). Holding company retains "
            "'safe capital' shielded from trading risk. When distributions are needed, the "
            "holding company pays dividends to a family trust, which distributes to beneficiaries "
            "at their marginal rates — with full franking credits attached."
        ),
        "entities": [
            {"name": "Trading Company", "type": "Company", "subtype": "Trading Co",
             "notes": "Generates profit. Exposed to trading risk."},
            {"name": "Holding Company", "type": "Company", "subtype": "Holding Co",
             "notes": "Retains profits. Safe capital. No trading risk."},
            {"name": "Family Trust", "type": "Trust", "subtype": "Discretionary (Family)",
             "notes": "Receives dividends from Holding Co. Distributes to beneficiaries."},
        ],
        "relationships": [
            {"from": "Holding Company", "to": "Trading Company", "rel_type": "Owns (%)", "detail": "100%"},
            {"from": "Family Trust",    "to": "Holding Company", "rel_type": "Owns (%)", "detail": "100%"},
        ],
        "flows": [
            {"from": "Trading Company", "to": "Holding Company", "label": "Fully Franked Dividend",
             "frequency": "Annual", "amount": 0,
             "notes": "No additional tax between companies (>10% ownership). Profits shielded from trading risk."},
            {"from": "Holding Company", "to": "Family Trust", "label": "Dividend to Trust",
             "frequency": "Annual", "amount": 0,
             "notes": "Franking credits pass through to beneficiaries."},
        ],
        "diagram_nodes": [
            ("Trading Company", 0.5, 0.9, "#4A90D9", "white"),
            ("25% Company Tax", 0.88, 0.75, "#E8A838", "white"),
            ("Holding Company", 0.5, 0.55, "#5BA85A", "white"),
            ("Family Trust", 0.5, 0.2, "#7B68EE", "white"),
            ("Safe Capital", 0.88, 0.38, "#5BA85A", "white"),
        ],
        "diagram_edges": [
            ("Trading Company", "25% Company Tax", "Pays company tax"),
            ("25% Company Tax", "Holding Company", "Fully Franked Dividend\n(no add'l tax >10% ownership)"),
            ("Holding Company", "Safe Capital", "Capital isolated\nfrom trading risk"),
            ("Holding Company", "Family Trust", "Dividends when\ndistributions needed"),
        ],
    }
}


# ── data helpers ──────────────────────────────────────────────────────────────
def _load_template(tname, entities, relationships, flows):
    tdata = STRUCTURE_TEMPLATES[tname]
    existing_names = {e["name"] for e in entities}
    name_to_id = {e["name"]: e["id"] for e in entities}

    for edef in tdata["entities"]:
        if edef["name"] not in existing_names:
            eid = new_id()
            entities.append({"id": eid, "name": edef["name"], "type": edef["type"],
                              "subtype": edef.get("subtype", ""), "abn": "", "state": "",
                              "address": "", "notes": edef.get("notes", ""),
                              "created": datetime.now().isoformat()})
            name_to_id[edef["name"]] = eid

    for rdef in tdata["relationships"]:
        fid = name_to_id.get(rdef["from"])
        tid = name_to_id.get(rdef["to"])
        if fid and tid:
            already = any(r["from_id"] == fid and r["to_id"] == tid for r in relationships)
            if not already:
                relationships.append({"id": new_id(), "from_id": fid, "to_id": tid,
                                      "rel_type": rdef["rel_type"], "detail": rdef.get("detail", "")})

    for fdef in tdata["flows"]:
        fid = name_to_id.get(fdef["from"])
        tid = name_to_id.get(fdef["to"])
        if fid and tid:
            already = any(f["from_id"] == fid and f["to_id"] == tid and f.get("label") == fdef["label"] for f in flows)
            if not already:
                flows.append({"id": new_id(), "from_id": fid, "to_id": tid,
                              "label": fdef["label"], "amount": fdef.get("amount", 0),
                              "frequency": fdef.get("frequency", "Annual"),
                              "notes": fdef.get("notes", "")})

    save("entities", entities)
    save("relationships", relationships)
    save("flows", flows)


def _sync_beneficiaries(trust_entity, beneficiaries, entities, relationships):
    """Ensure each beneficiary has an Individual entity and a Beneficiary-of relationship."""
    name_to_id = {e["name"]: e["id"] for e in entities}
    for b in beneficiaries:
        bname = b["name"].strip()
        if not bname:
            continue
        # create Individual entity if not already present
        if bname not in name_to_id:
            eid = new_id()
            entities.append({"id": eid, "name": bname, "type": "Individual", "subtype": "",
                              "abn": "", "state": "", "address": "", "notes": "",
                              "created": datetime.now().isoformat()})
            name_to_id[bname] = eid
        bid = name_to_id[bname]
        # create Beneficiary-of relationship if not already present
        already = any(r["from_id"] == bid and r["to_id"] == trust_entity["id"]
                      and r["rel_type"] == "Beneficiary of" for r in relationships)
        if not already:
            pct = f"{b['percentage']}%" if b.get("percentage") else ""
            relationships.append({"id": new_id(), "from_id": bid,
                                   "to_id": trust_entity["id"],
                                   "rel_type": "Beneficiary of", "detail": pct})


def _render_template_diagram(tdata):
    nodes = tdata.get("diagram_nodes", [])
    edges = tdata.get("diagram_edges", [])
    if not nodes:
        return
    node_pos = {name: (x, y) for name, x, y, *_ in nodes}
    fig = go.Figure()
    for src, dst, label in edges:
        sx, sy = node_pos[src]
        dx, dy = node_pos[dst]
        fig.add_trace(go.Scatter(
            x=[sx, dx], y=[sy, dy], mode="lines",
            line=dict(color="#aaa", width=1.5, dash="dot" if "no add" in label.lower() else "solid"),
            hoverinfo="skip", showlegend=False,
        ))
        mx, my = (sx + dx) / 2, (sy + dy) / 2
        fig.add_annotation(x=mx, y=my, text=label.replace("\n", "<br>"),
                           font=dict(size=9, color="#ddd"), showarrow=False,
                           bgcolor="rgba(0,0,0,0.4)", borderpad=3)
    for name, x, y, color, fcolor in nodes:
        fig.add_trace(go.Scatter(
            x=[x], y=[y], mode="markers+text",
            marker=dict(size=80, color=color, symbol="square",
                        line=dict(color="white", width=1.5)),
            text=[name], textposition="middle center",
            textfont=dict(color=fcolor, size=11, family="Arial Black"),
            hoverinfo="skip", showlegend=False,
        ))
    fig.update_layout(
        height=480, margin=dict(l=20, r=20, t=10, b=10),
        plot_bgcolor="#111", paper_bgcolor="#111",
        xaxis=dict(visible=False, range=[0, 1.2]),
        yaxis=dict(visible=False, range=[0, 1.1]),
    )
    st.plotly_chart(fig, use_container_width=True)


def load(name: str) -> list:
    p = DATA_DIR / f"{name}.json"
    if p.exists():
        return json.loads(p.read_text())
    return []


def save(name: str, data: list) -> None:
    p = DATA_DIR / f"{name}.json"
    p.write_text(json.dumps(data, indent=2))


def new_id() -> str:
    return str(uuid.uuid4())[:8]


# ── sidebar ───────────────────────────────────────────────────────────────────
pages = ["🏠 Dashboard", "🗺️ Structure View", "📋 Information Form", "🏢 Entities", "🔗 Relationships", "💰 Flows", "📄 Accountant Summary", "⚡ Skills"]
with st.sidebar:
    st.title("🏢 Corporate Workflow")
    st.caption("Entity & financial management")
    page = st.radio("Navigate", pages, label_visibility="collapsed")
    st.divider()
    entities = load("entities")
    relationships = load("relationships")
    flows = load("flows")
    st.metric("Entities", len(entities))
    st.metric("Relationships", len(relationships))
    st.metric("Flows", len(flows))
    st.divider()

    # ── Export all data as a single JSON download ─────────────────────────────
    export_blob = json.dumps({
        "entities": entities,
        "relationships": relationships,
        "flows": flows,
        "exported": datetime.now().isoformat(),
    }, indent=2)
    st.download_button(
        "⬇️ Export data",
        data=export_blob,
        file_name=f"corporate_data_{datetime.now().strftime('%Y%m%d')}.json",
        mime="application/json",
        help="Download all your data as a single file to back up or send to your accountant.",
        use_container_width=True,
    )

    # ── Import data from a previously exported file ───────────────────────────
    uploaded = st.file_uploader("⬆️ Import data", type="json",
                                 help="Upload a previously exported data file to restore or merge.")
    if uploaded:
        try:
            imported = json.loads(uploaded.read())
            save("entities", imported.get("entities", []))
            save("relationships", imported.get("relationships", []))
            save("flows", imported.get("flows", []))
            st.success("Data imported — refreshing.")
            st.rerun()
        except Exception as e:
            st.error(f"Import failed: {e}")

    st.divider()
    st.caption("Drop .py files into `/skills/` to add capabilities.")


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if page == "🏠 Dashboard":
    st.title("Corporate Workflow Dashboard")

    if not entities:
        st.info("👋 Get started by loading a **Structure Template** (see Structure View) or add entities manually via **Entities**.")

        st.markdown("---")
        st.subheader("Quick-start templates")
        for tname, tdata in STRUCTURE_TEMPLATES.items():
            with st.expander(f"**{tname}**"):
                st.write(tdata["description"])
                if st.button(f"Load this template", key=f"dash_{tname}"):
                    _load_template(tname, entities, relationships, flows)
                    st.rerun()
    else:
        counts = {t: 0 for t in ENTITY_TYPES}
        for e in entities:
            counts[e["type"]] = counts.get(e["type"], 0) + 1
        active = [(t, c) for t, c in counts.items() if c]
        if active:
            cols = st.columns(len(active))
            for i, (etype, count) in enumerate(active):
                cols[i].metric(etype, count)

        st.divider()
        st.subheader("Entity structure")
        entity_map = {e["id"]: e["name"] for e in entities}
        for e in entities:
            rels = [r for r in relationships if r["from_id"] == e["id"] or r["to_id"] == e["id"]]
            eflows = [f for f in flows if f["from_id"] == e["id"] or f["to_id"] == e["id"]]
            with st.expander(f"**{e['name']}**  —  {e['type']}" + (f" / {e['subtype']}" if e.get('subtype') else "")):
                c1, c2, c3 = st.columns(3)
                c1.markdown(f"**ABN/ACN:** {e.get('abn') or '—'}")
                c2.markdown(f"**Relationships:** {len(rels)}")
                c3.markdown(f"**Flows:** {len(eflows)}")
                if e.get("notes"):
                    st.caption(e["notes"])

        st.divider()
        st.subheader("Recent flows")
        if flows:
            for f in flows[-5:]:
                frm = entity_map.get(f["from_id"], "?")
                to  = entity_map.get(f["to_id"], "?")
                amt = f"${f['amount']:,.0f}" if f.get("amount") else "—"
                st.markdown(f"- **{frm}** → **{to}**  |  {amt}  |  {f.get('frequency','—')}  |  {f.get('label','')}")
        else:
            st.caption("No flows added yet.")


# ══════════════════════════════════════════════════════════════════════════════
# STRUCTURE VIEW
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🗺️ Structure View":
    st.title("Structure View")

    tab_live, tab_templates = st.tabs(["Your structure", "Templates"])

    # ── Live diagram — hierarchical layout ───────────────────────────────────
    with tab_live:
        if not entities:
            st.info("Add entities and relationships to see your structure here.")
        else:
            TYPE_COLORS = {
                "Individual": "#2ECC71", "Company": "#3498DB",
                "Trust": "#9B59B6", "SMSF": "#E67E22",
                "Partnership": "#E74C3C", "Foundation": "#1ABC9C", "Other": "#95A5A6",
            }
            REL_COLORS  = {
                "Owns (%)": "#3498DB", "Trustee of": "#9B59B6",
                "Beneficiary of": "#2ECC71", "Director of": "#95A5A6",
                "Lender to": "#E74C3C", "Guarantor of": "#E67E22",
            }
            TIER_ORDER  = ["Individual", "Company", "Trust", "SMSF", "Partnership", "Foundation", "Other"]

            # assign display tier — holding cos above trading cos
            def tier(e):
                if e["type"] == "Individual": return 0
                if e["type"] in ("Trust", "SMSF"): return 2
                sub = e.get("subtype", "")
                if sub in ("Holding Co", "Shelf"): return 1
                if e["type"] == "Company": return 3
                return 4

            from collections import defaultdict
            tiers = defaultdict(list)
            for e in entities:
                tiers[tier(e)].append(e)

            pos = {}
            tier_y = {0: 0.92, 1: 0.68, 2: 0.44, 3: 0.16, 4: 0.08}
            for t, members in sorted(tiers.items()):
                n = len(members)
                for i, e in enumerate(members):
                    x = (i + 1) / (n + 1)
                    pos[e["id"]] = (x, tier_y.get(t, 0.1))

            fig = go.Figure()

            # draw relationship lines (skip Director-of to reduce clutter — shown in table)
            drawn = set()
            for r in relationships:
                if r["rel_type"] == "Director of":
                    continue
                key = tuple(sorted([r["from_id"], r["to_id"]]))
                fpos = pos.get(r["from_id"])
                tpos = pos.get(r["to_id"])
                if not fpos or not tpos:
                    continue
                color = REL_COLORS.get(r["rel_type"], "#aaa")
                dash  = "dot" if r["rel_type"] == "Beneficiary of" else "solid"
                fig.add_trace(go.Scatter(
                    x=[fpos[0], tpos[0]], y=[fpos[1], tpos[1]],
                    mode="lines", line=dict(color=color, width=1.8, dash=dash),
                    hoverinfo="skip", showlegend=False,
                ))
                mx, my = (fpos[0] + tpos[0]) / 2, (fpos[1] + tpos[1]) / 2
                detail = f" {r['detail']}" if r.get("detail") else ""
                if key not in drawn:
                    fig.add_annotation(x=mx, y=my,
                        text=f"<i>{r['rel_type']}{detail}</i>",
                        font=dict(size=8, color=color), showarrow=False,
                        bgcolor="rgba(15,15,25,0.7)", borderpad=2)
                    drawn.add(key)

            # draw nodes
            for e in entities:
                x, y = pos[e["id"]]
                color = TYPE_COLORS.get(e["type"], "#888")
                name_lines = e["name"].replace(" Pty Ltd", "<br>Pty Ltd").replace(" Trust", "<br>Trust")
                hover = f"<b>{e['name']}</b><br>{e['type']}"
                if e.get("subtype"): hover += f" / {e['subtype']}"
                if e.get("abn"):     hover += f"<br>ABN: {e['abn']}"
                if e.get("notes"):   hover += f"<br>{e['notes'][:80]}"
                fig.add_trace(go.Scatter(
                    x=[x], y=[y], mode="markers+text",
                    marker=dict(size=52, color=color,
                                line=dict(color="white", width=2),
                                symbol="square" if e["type"] == "Individual" else "circle"),
                    text=[name_lines],
                    textposition="middle center",
                    textfont=dict(color="white", size=9),
                    hovertext=[hover], hoverinfo="text",
                    showlegend=False,
                ))

            tier_labels = {0.92: "People", 0.68: "Holding Companies",
                           0.44: "Trusts & SMSF", 0.16: "Trading Companies"}
            for y, label in tier_labels.items():
                fig.add_annotation(x=0.01, y=y, text=f"<b>{label}</b>",
                    xref="paper", font=dict(size=10, color="#888"),
                    showarrow=False, xanchor="left")

            fig.update_layout(
                height=680, margin=dict(l=80, r=20, t=20, b=20),
                plot_bgcolor="#0f0f19", paper_bgcolor="#0f0f19",
                xaxis=dict(visible=False, range=[0, 1]),
                yaxis=dict(visible=False, range=[0, 1]),
            )
            st.plotly_chart(fig, use_container_width=True)

            # legend
            lcols = st.columns(len(TYPE_COLORS))
            for i, (t, c) in enumerate(TYPE_COLORS.items()):
                lcols[i].markdown(f"<span style='color:{c}'>■</span> {t}", unsafe_allow_html=True)

            # director table below diagram
            st.markdown("#### Directorships")
            dir_rels = [r for r in relationships if r["rel_type"] == "Director of"]
            emap = {e["id"]: e["name"] for e in entities}
            if dir_rels:
                rows = [{"Person": emap.get(r["from_id"],"?"),
                         "Company": emap.get(r["to_id"],"?"),
                         "Role": r.get("detail","Director")} for r in dir_rels]
                st.table(rows)

    # ── Templates ─────────────────────────────────────────────────────────────
    with tab_templates:
        for tname, tdata in STRUCTURE_TEMPLATES.items():
            st.subheader(tname)
            st.write(tdata["description"])

            # Static diagram
            _render_template_diagram(tdata)

            st.markdown("**Structure includes:**")
            c1, c2, c3 = st.columns(3)
            c1.markdown("**Entities**\n" + "\n".join(f"- {e['name']} ({e['type']})" for e in tdata["entities"]))
            c2.markdown("**Relationships**\n" + "\n".join(f"- {r['from']} → {r['to']} ({r['rel_type']} {r['detail']})" for r in tdata["relationships"]))
            c3.markdown("**Flows**\n" + "\n".join(f"- {f['from']} → {f['to']}: {f['label']}" for f in tdata["flows"]))

            existing_names = {e["name"] for e in entities}
            would_add = [e for e in tdata["entities"] if e["name"] not in existing_names]
            already = [e for e in tdata["entities"] if e["name"] in existing_names]

            if already:
                st.caption(f"Already in your system: {', '.join(e['name'] for e in already)}")
            if would_add:
                st.info(f"Will add: {', '.join(e['name'] for e in would_add)}")
                if st.button(f"Load template into my structure", key=f"tpl_{tname}", type="primary"):
                    _load_template(tname, entities, relationships, flows)
                    st.success("Template loaded! Head to Dashboard or Structure View.")
                    st.rerun()
            else:
                st.success("All entities from this template are already in your structure.")

            st.markdown("---")


# ══════════════════════════════════════════════════════════════════════════════
# ENTITIES
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🏢 Entities":
    st.title("Entities")
    tab_list, tab_add, tab_edit = st.tabs(["List", "Add new", "Edit / Delete"])

    # ── List ─────────────────────────────────────────────────────────────────
    with tab_list:
        if not entities:
            st.info("No entities yet.")
        for e in entities:
            label = f"**{e['name']}** — {e['type']}" + (f" / {e['subtype']}" if e.get('subtype') else "")
            with st.expander(label):
                cols = st.columns(3)
                cols[0].markdown(f"**ABN/ACN:** {e.get('abn') or '—'}")
                cols[1].markdown(f"**State:** {e.get('state') or '—'}")
                cols[2].markdown(f"**ID:** `{e['id']}`")
                if e.get("address"):
                    st.markdown(f"**Address:** {e['address']}")
                if e.get("notes"):
                    st.caption(e["notes"])
                # show beneficiaries inline for trusts
                if e["type"] == "Trust" and e.get("beneficiaries"):
                    st.markdown("**Beneficiaries:**")
                    for b in e["beneficiaries"]:
                        pct = f" — {b['percentage']}%" if b.get("percentage") else ""
                        note = f" ({b['notes']})" if b.get("notes") else ""
                        st.markdown(f"  - {b['name']}{pct}{note}")

    # ── Add new ───────────────────────────────────────────────────────────────
    with tab_add:
        with st.form("add_entity"):
            c1, c2 = st.columns(2)
            name  = c1.text_input("Entity name *")
            etype = c2.selectbox("Entity type *", ENTITY_TYPES)
            subtype_opts = (TRUST_SUBTYPES if etype == "Trust" else COMPANY_SUBTYPES if etype == "Company" else [])
            subtype = st.selectbox("Sub-type", [""] + subtype_opts) if subtype_opts else ""
            c3, c4 = st.columns(2)
            abn   = c3.text_input("ABN / ACN")
            state = c4.selectbox("State / Territory", ["", "NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"])
            address = st.text_input("Registered address")
            notes   = st.text_area("Notes / key people")
            if st.form_submit_button("Add entity", type="primary"):
                if not name:
                    st.error("Name is required.")
                else:
                    entities.append({"id": new_id(), "name": name, "type": etype, "subtype": subtype,
                                     "abn": abn, "state": state, "address": address, "notes": notes,
                                     "created": datetime.now().isoformat()})
                    save("entities", entities)
                    st.success(f"Added **{name}**.")
                    st.rerun()

    # ── Edit / Delete ─────────────────────────────────────────────────────────
    with tab_edit:
        if not entities:
            st.info("No entities to edit.")
        else:
            names  = {e["id"]: e["name"] for e in entities}
            sel_id = st.selectbox("Select entity", list(names.keys()), format_func=lambda x: names[x])
            sel    = next(e for e in entities if e["id"] == sel_id)

            with st.form("edit_entity"):
                st.markdown("#### Details")
                c1, c2   = st.columns(2)
                new_name = c1.text_input("Name", value=sel["name"])
                new_type = c2.selectbox("Type", ENTITY_TYPES, index=ENTITY_TYPES.index(sel["type"]))
                subtype_opts = (TRUST_SUBTYPES if new_type == "Trust" else COMPANY_SUBTYPES if new_type == "Company" else [])
                cur_sub = sel.get("subtype", "") or ""
                if subtype_opts:
                    opts = [""] + subtype_opts
                    sub_idx = opts.index(cur_sub) if cur_sub in opts else 0
                    new_subtype = st.selectbox("Sub-type", opts, index=sub_idx)
                else:
                    new_subtype = ""
                c3, c4  = st.columns(2)
                new_abn = c3.text_input("ABN / ACN", value=sel.get("abn", ""))
                states  = ["", "NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"]
                new_state = c4.selectbox("State", states, index=states.index(sel.get("state", "") or ""))
                new_address = st.text_input("Address", value=sel.get("address", ""))
                new_notes   = st.text_area("Notes", value=sel.get("notes", ""))

                # ── Beneficiaries (Trusts only) ───────────────────────────────
                existing_bens = sel.get("beneficiaries", [])
                new_bens = []
                if new_type == "Trust":
                    st.markdown("#### Beneficiaries")
                    st.caption("Add each person who can receive distributions from this trust.")
                    n_bens = st.number_input("Number of beneficiaries", min_value=0,
                                             max_value=20, value=len(existing_bens), step=1)
                    for i in range(int(n_bens)):
                        cur = existing_bens[i] if i < len(existing_bens) else {}
                        bc1, bc2, bc3 = st.columns([3, 1, 2])
                        bname = bc1.text_input(f"Name", value=cur.get("name", ""), key=f"bn_{i}")
                        bpct  = bc2.number_input(f"%", min_value=0, max_value=100,
                                                  value=int(cur.get("percentage", 0)), key=f"bp_{i}")
                        bnote = bc3.text_input(f"Role / note", value=cur.get("notes", ""), key=f"bnt_{i}")
                        if bname:
                            new_bens.append({"name": bname, "percentage": bpct, "notes": bnote})

                s_col, d_col = st.columns(2)
                save_clicked   = s_col.form_submit_button("Save changes", type="primary")
                delete_clicked = d_col.form_submit_button("Delete entity")

                if save_clicked:
                    sel.update({"name": new_name, "type": new_type, "subtype": new_subtype,
                                "abn": new_abn, "state": new_state,
                                "address": new_address, "notes": new_notes})
                    if new_type == "Trust":
                        sel["beneficiaries"] = new_bens
                        # sync Individual entities + Beneficiary-of relationships
                        _sync_beneficiaries(sel, new_bens, entities, relationships)
                    save("entities", entities)
                    save("relationships", relationships)
                    st.success("Saved.")
                    st.rerun()

                if delete_clicked:
                    entities      = [e for e in entities if e["id"] != sel_id]
                    relationships = [r for r in relationships
                                     if r["from_id"] != sel_id and r["to_id"] != sel_id]
                    flows         = [f for f in flows
                                     if f["from_id"] != sel_id and f["to_id"] != sel_id]
                    save("entities", entities)
                    save("relationships", relationships)
                    save("flows", flows)
                    st.success("Deleted.")
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# INFORMATION FORM
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📋 Information Form":
    st.title("Information Form")
    st.markdown(
        "Fill in what you know — skip anything you don't have yet. "
        "Each section saves independently. This feeds directly into your entity records and the Accountant Summary."
    )

    emap     = {e["name"]: e for e in entities}
    id_map   = {e["id"]: e for e in entities}
    name_map = {e["id"]: e["name"] for e in entities}

    def get(name): return emap.get(name, {})
    def update_entity(name, fields):
        for e in entities:
            if e["name"] == name:
                e.update({k: v for k, v in fields.items() if v not in (None, "")})
                return
    def add_entity_if_missing(name, etype, subtype="", notes=""):
        if name not in emap:
            eid = new_id()
            entities.append({"id": eid, "name": name, "type": etype, "subtype": subtype,
                              "abn": "", "state": "", "address": "", "notes": notes,
                              "created": datetime.now().isoformat()})
            return eid
        return emap[name]["id"]
    def add_rel_if_missing(from_id, to_id, rel_type, detail=""):
        if not any(r["from_id"] == from_id and r["to_id"] == to_id and r["rel_type"] == rel_type
                   for r in relationships):
            relationships.append({"id": new_id(), "from_id": from_id, "to_id": to_id,
                                   "rel_type": rel_type, "detail": detail})

    STATES = ["", "NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"]

    # ══ SECTION 1 — VERSYHIRE ═════════════════════════════════════════════════
    with st.expander("**1. Versyhire Pty Ltd** — new company", expanded=True):
        st.caption("Tell us about the three shareholders/directors and the business.")
        with st.form("form_versyhire"):
            c1, c2 = st.columns(2)
            vh_abn   = c1.text_input("ABN / ACN", value=get("Versyhire Pty Ltd").get("abn",""))
            vh_state = c2.selectbox("State", STATES)
            vh_notes = st.text_area("What does Versyhire do?", value=get("Versyhire Pty Ltd").get("notes",""))
            st.markdown("**Shareholders / Directors**")
            sh_cols = st.columns(3)
            vh_people, vh_pcts = [], []
            for i, col in enumerate(sh_cols):
                col.markdown(f"*Person {i+1}*")
                vh_people.append(col.text_input("Name", key=f"vh_name_{i}"))
                vh_pcts.append(col.number_input("Share %", 0, 100, 0, key=f"vh_pct_{i}"))
            if st.form_submit_button("Save Versyhire", type="primary"):
                vh_id = add_entity_if_missing("Versyhire Pty Ltd", "Company", "Trading Co")
                update_entity("Versyhire Pty Ltd", {"abn": vh_abn, "state": vh_state, "notes": vh_notes})
                for name, pct in zip(vh_people, vh_pcts):
                    name = name.strip()
                    if not name: continue
                    pid = add_entity_if_missing(name, "Individual")
                    add_rel_if_missing(pid, vh_id, "Director of")
                    add_rel_if_missing(pid, vh_id, "Owns (%)", f"{pct}%")
                save("entities", entities)
                save("relationships", relationships)
                st.success("Versyhire saved.")
                st.rerun()

    # ══ SECTION 2 — DECON SERVICES ════════════════════════════════════════════
    with st.expander("**2. Decon Services Pty Ltd**", expanded=True):
        with st.form("form_decon"):
            c1, c2 = st.columns(2)
            dc_abn   = c1.text_input("ABN / ACN", value=get("Decon Services Pty Ltd").get("abn",""))
            dc_state = c2.selectbox("State", STATES, key="dc_state")
            dc_notes = st.text_area("What does Decon do?", value=get("Decon Services Pty Ltd").get("notes",""))
            st.markdown("**Shareholders / Directors** — add as many as apply")
            dc_cols = st.columns(3)
            dc_people, dc_pcts, dc_roles = [], [], []
            for i, col in enumerate(dc_cols):
                col.markdown(f"*Person {i+1}*")
                dc_people.append(col.text_input("Name", key=f"dc_name_{i}"))
                dc_pcts.append(col.number_input("Share %", 0, 100, 0, key=f"dc_pct_{i}"))
            dc_peter = st.checkbox("Peter Thomas is involved in Decon")
            if st.form_submit_button("Save Decon Services", type="primary"):
                dc_id = add_entity_if_missing("Decon Services Pty Ltd", "Company", "Trading Co")
                update_entity("Decon Services Pty Ltd", {"abn": dc_abn, "state": dc_state, "notes": dc_notes})
                for name, pct in zip(dc_people, dc_pcts):
                    name = name.strip()
                    if not name: continue
                    pid = add_entity_if_missing(name, "Individual")
                    add_rel_if_missing(pid, dc_id, "Director of")
                    add_rel_if_missing(pid, dc_id, "Owns (%)", f"{pct}%")
                if dc_peter:
                    pet_id = emap.get("Peter Thomas", {}).get("id")
                    if pet_id:
                        add_rel_if_missing(pet_id, dc_id, "Director of")
                save("entities", entities)
                save("relationships", relationships)
                st.success("Decon Services saved.")
                st.rerun()

    # ══ SECTION 3 — PATHWAY RECRUITMENT ═══════════════════════════════════════
    with st.expander("**3. Pathway Recruitment Pty Ltd**", expanded=True):
        with st.form("form_pathway"):
            c1, c2 = st.columns(2)
            pw_abn   = c1.text_input("ABN / ACN", value=get("Pathway Recruitment Pty Ltd").get("abn",""))
            pw_state = c2.selectbox("State", STATES, key="pw_state")
            pw_notes = st.text_area("What does Pathway do?", value=get("Pathway Recruitment Pty Ltd").get("notes",""))
            st.markdown("**Shareholders / Directors**")
            pw_cols = st.columns(3)
            pw_people, pw_pcts = [], []
            for i, col in enumerate(pw_cols):
                col.markdown(f"*Person {i+1}*")
                pw_people.append(col.text_input("Name", key=f"pw_name_{i}"))
                pw_pcts.append(col.number_input("Share %", 0, 100, 0, key=f"pw_pct_{i}"))
            pw_peter = st.checkbox("Peter Thomas is involved in Pathway")
            if st.form_submit_button("Save Pathway Recruitment", type="primary"):
                pw_id = add_entity_if_missing("Pathway Recruitment Pty Ltd", "Company", "Trading Co")
                update_entity("Pathway Recruitment Pty Ltd", {"abn": pw_abn, "state": pw_state, "notes": pw_notes})
                for name, pct in zip(pw_people, pw_pcts):
                    name = name.strip()
                    if not name: continue
                    pid = add_entity_if_missing(name, "Individual")
                    add_rel_if_missing(pid, pw_id, "Director of")
                    add_rel_if_missing(pid, pw_id, "Owns (%)", f"{pct}%")
                if pw_peter:
                    pet_id = emap.get("Peter Thomas", {}).get("id")
                    if pet_id:
                        add_rel_if_missing(pet_id, pw_id, "Director of")
                save("entities", entities)
                save("relationships", relationships)
                st.success("Pathway Recruitment saved.")
                st.rerun()

    # ══ SECTION 4 — TEAL PROPERTY HOLDINGS ════════════════════════════════════
    with st.expander("**4. Teal Property Holdings Pty Ltd**", expanded=True):
        with st.form("form_teal"):
            c1, c2 = st.columns(2)
            tp_abn   = c1.text_input("ABN / ACN", value=get("Teal Property Holdings Pty Ltd").get("abn",""))
            tp_state = c2.selectbox("State", STATES, key="tp_state")
            tp_owner = st.selectbox("Who owns Teal Property Holdings?", [
                "", "Cameron Price (personally)",
                "C Price Investments Pty Ltd",
                "CE Price Family Trust",
                "In Price we Trust",
                "Other (add in notes)",
            ])
            tp_dirs  = st.text_input("Directors (comma separated)")
            tp_props = st.text_area("Properties held (address, value if known)")
            tp_notes = st.text_area("Other notes", value=get("Teal Property Holdings Pty Ltd").get("notes",""))
            if st.form_submit_button("Save Teal Property Holdings", type="primary"):
                tp_id = add_entity_if_missing("Teal Property Holdings Pty Ltd", "Company", "Holding Co")
                update_entity("Teal Property Holdings Pty Ltd", {
                    "abn": tp_abn, "state": tp_state,
                    "notes": f"Owner: {tp_owner}. Properties: {tp_props}. {tp_notes}".strip(". ")
                })
                owner_map = {
                    "Cameron Price (personally)": "cam001",
                    "C Price Investments Pty Ltd": emap.get("C Price Investments Pty Ltd",{}).get("id"),
                    "CE Price Family Trust": emap.get("CE Price Family Trust",{}).get("id"),
                    "In Price we Trust": emap.get("In Price we Trust",{}).get("id"),
                }
                owner_id = owner_map.get(tp_owner)
                if owner_id:
                    add_rel_if_missing(owner_id, tp_id, "Owns (%)", "100%")
                for d in [x.strip() for x in tp_dirs.split(",") if x.strip()]:
                    did = add_entity_if_missing(d, "Individual")
                    add_rel_if_missing(did, tp_id, "Director of")
                save("entities", entities)
                save("relationships", relationships)
                st.success("Teal Property Holdings saved.")
                st.rerun()

    # ══ SECTION 5 — IN PRICE WE TRUST ════════════════════════════════════════
    with st.expander("**5. In Price we Trust**", expanded=True):
        with st.form("form_ipwt"):
            ipwt = get("In Price we Trust")
            c1, c2 = st.columns(2)
            ipwt_abn     = c1.text_input("ABN / TFN", value=ipwt.get("abn",""))
            ipwt_subtype = c2.selectbox("Trust type", [""] + TRUST_SUBTYPES,
                                         index=(TRUST_SUBTYPES.index(ipwt.get("subtype","")) + 1
                                                if ipwt.get("subtype","") in TRUST_SUBTYPES else 0))
            ipwt_trustee = st.text_input("Trustee company name")
            ipwt_purpose = st.text_input("Purpose (e.g. property, general wealth)")
            ipwt_bens    = st.text_area("Beneficiaries (one per line, include % if known)")
            ipwt_notes   = st.text_area("Other notes", value=ipwt.get("notes",""))
            if st.form_submit_button("Save In Price we Trust", type="primary"):
                ipwt_id = add_entity_if_missing("In Price we Trust", "Trust")
                update_entity("In Price we Trust", {
                    "abn": ipwt_abn, "subtype": ipwt_subtype,
                    "notes": f"Purpose: {ipwt_purpose}. {ipwt_notes}".strip(". ")
                })
                if ipwt_trustee.strip():
                    tid = add_entity_if_missing(ipwt_trustee.strip(), "Company", "Holding Co")
                    add_rel_if_missing(tid, ipwt_id, "Trustee of")
                for line in [l.strip() for l in ipwt_bens.splitlines() if l.strip()]:
                    bid = add_entity_if_missing(line, "Individual")
                    add_rel_if_missing(bid, ipwt_id, "Beneficiary of")
                save("entities", entities)
                save("relationships", relationships)
                st.success("In Price we Trust saved.")
                st.rerun()

    # ══ SECTION 6 — CE PRICE FAMILY TRUST ════════════════════════════════════
    with st.expander("**6. CE Price Family Trust — beneficiaries**", expanded=True):
        with st.form("form_cepft"):
            st.caption("List everyone who can receive distributions — spouse, children, related entities.")
            cepft_bens = st.text_area(
                "Beneficiaries (one per line)",
                value="\n".join(b["name"] for b in get("CE Price Family Trust").get("beneficiaries",[]))
            )
            cepft_notes = st.text_area("Other notes", value=get("CE Price Family Trust").get("notes",""))
            if st.form_submit_button("Save CE Price Family Trust", type="primary"):
                trust_id = emap.get("CE Price Family Trust", {}).get("id")
                bens_list = [{"name": l.strip(), "percentage": 0, "notes": ""}
                             for l in cepft_bens.splitlines() if l.strip()]
                for e in entities:
                    if e["name"] == "CE Price Family Trust":
                        e["beneficiaries"] = bens_list
                        if cepft_notes: e["notes"] = cepft_notes
                if trust_id:
                    for b in bens_list:
                        bid = add_entity_if_missing(b["name"], "Individual")
                        add_rel_if_missing(bid, trust_id, "Beneficiary of")
                save("entities", entities)
                save("relationships", relationships)
                st.success("CE Price Family Trust updated.")
                st.rerun()

    # ══ SECTION 7 — TRADING COMPANIES STATUS ══════════════════════════════════
    with st.expander("**7. Trading company status**", expanded=True):
        with st.form("form_trading_status"):
            st.caption("Confirm whether each company is active, dormant, or wound up.")
            trading_cos = ["Commerce Building Services Pty Ltd", "Commerce Building Investments Pty Ltd",
                           "CBS Roofing Contractors Services Pty Ltd", "Commerce Joinery & Cabinetry Pty Ltd",
                           "Decon Services Pty Ltd", "Pathway Recruitment Pty Ltd"]
            statuses = {}
            for co in trading_cos:
                statuses[co] = st.selectbox(co, ["Active", "Dormant", "Wound up / Deregistered"],
                                             key=f"status_{co}")
            if st.form_submit_button("Save statuses", type="primary"):
                for co, status in statuses.items():
                    for e in entities:
                        if e["name"] == co:
                            existing = e.get("notes","")
                            e["notes"] = f"Status: {status}. " + existing.replace(f"Status: {e.get('status','')}. ","")
                save("entities", entities)
                st.success("Statuses saved.")
                st.rerun()

    # ══ SECTION 8 — ABN / ACN REGISTER ═══════════════════════════════════════
    with st.expander("**8. ABN / ACN numbers**", expanded=True):
        st.caption(
            "Click the 🔍 link next to each entity to open the ABR search in a new tab, "
            "then paste the ABN back here. Leave blank if unknown — your accountant can fill these in."
        )
        with st.form("form_abns"):
            abn_vals = {}
            for e in entities:
                if e["type"] == "Individual":
                    continue
                abr_url = f"https://www.abr.business.gov.au/Search/ResultsActive?SearchText={e['name'].replace(' ', '+')}"
                label = f"{e['name']}  [🔍 ABR]({abr_url})"
                abn_vals[e["id"]] = st.text_input(
                    label, value=e.get("abn",""), key=f"abn_{e['id']}"
                )
            if st.form_submit_button("Save ABNs / ACNs", type="primary"):
                for e in entities:
                    if e["id"] in abn_vals and abn_vals[e["id"]]:
                        e["abn"] = abn_vals[e["id"]]
                save("entities", entities)
                st.success("ABNs / ACNs saved.")
                st.rerun()

    # ══ SECTION 9 — DOCUMENTS ══════════════════════════════════════════════════
    with st.expander("**9. Supporting documents**", expanded=True):
        st.caption("Upload any documents related to your structure — trust deeds, ASIC extracts, shareholder agreements.")
        uploaded = st.file_uploader("Upload documents", accept_multiple_files=True,
                                     type=["pdf","docx","xlsx","png","jpg"])
        if uploaded:
            docs_dir = DATA_DIR / "documents"
            docs_dir.mkdir(exist_ok=True)
            for f in uploaded:
                (docs_dir / f.name).write_bytes(f.read())
                st.success(f"Saved: {f.name}")
        existing_docs = list((DATA_DIR / "documents").glob("*")) if (DATA_DIR / "documents").exists() else []
        if existing_docs:
            st.markdown("**Uploaded documents:**")
            for d in existing_docs:
                st.markdown(f"- {d.name}")


# ══════════════════════════════════════════════════════════════════════════════
# RELATIONSHIPS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔗 Relationships":
    st.title("Relationships")
    tab_list, tab_add = st.tabs(["List", "Add new"])

    with tab_list:
        if not relationships:
            st.info("No relationships yet.")
        entity_map = {e["id"]: e["name"] for e in entities}
        for r in relationships:
            frm    = entity_map.get(r["from_id"], "?")
            to     = entity_map.get(r["to_id"], "?")
            detail = f" — {r['detail']}" if r.get("detail") else ""
            st.markdown(f"- **{frm}** › *{r['rel_type']}* › **{to}**{detail}")

    with tab_add:
        if len(entities) < 2:
            st.info("You need at least two entities to create a relationship.")
        else:
            entity_map = {e["id"]: e["name"] for e in entities}
            with st.form("add_rel"):
                c1, c2, c3 = st.columns(3)
                from_id  = c1.selectbox("From entity", list(entity_map.keys()), format_func=lambda x: entity_map[x])
                rel_type = c2.selectbox("Relationship", REL_TYPES)
                to_id    = c3.selectbox("To entity", list(entity_map.keys()), format_func=lambda x: entity_map[x])
                detail   = st.text_input("Detail (e.g. 50%, trustee name, loan amount)")
                if st.form_submit_button("Add relationship", type="primary"):
                    if from_id == to_id:
                        st.error("From and To must be different entities.")
                    else:
                        relationships.append({"id": new_id(), "from_id": from_id, "to_id": to_id,
                                              "rel_type": rel_type, "detail": detail})
                        save("relationships", relationships)
                        st.success("Relationship added.")
                        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# FLOWS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "💰 Flows":
    st.title("Money Flows")
    tab_list, tab_add = st.tabs(["List", "Add new"])
    entity_map = {e["id"]: e["name"] for e in entities}

    with tab_list:
        if not flows:
            st.info("No flows yet.")
        for f in flows:
            frm = entity_map.get(f["from_id"], "?")
            to  = entity_map.get(f["to_id"], "?")
            amt = f"${f['amount']:,.0f}" if f.get("amount") else "—"
            st.markdown(f"- **{frm}** → **{to}**  |  {amt}  |  {f.get('frequency','—')}  |  {f.get('label','')}")

    with tab_add:
        if len(entities) < 2:
            st.info("You need at least two entities to create a flow.")
        else:
            with st.form("add_flow"):
                c1, c2 = st.columns(2)
                from_id   = c1.selectbox("From entity", list(entity_map.keys()), format_func=lambda x: entity_map[x])
                to_id     = c2.selectbox("To entity",   list(entity_map.keys()), format_func=lambda x: entity_map[x])
                c3, c4, c5 = st.columns(3)
                amount    = c3.number_input("Amount ($)", min_value=0, value=0, step=500)
                frequency = c4.selectbox("Frequency", FLOW_FREQ)
                label     = c5.text_input("Label (e.g. Dividend, Salary)")
                notes     = st.text_area("Notes")
                if st.form_submit_button("Add flow", type="primary"):
                    if from_id == to_id:
                        st.error("From and To must be different.")
                    else:
                        flows.append({"id": new_id(), "from_id": from_id, "to_id": to_id,
                                      "amount": amount, "frequency": frequency, "label": label, "notes": notes})
                        save("flows", flows)
                        st.success("Flow added.")
                        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# ACCOUNTANT SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📄 Accountant Summary":
    st.title("Accountant Summary")
    st.caption("A plain-English summary of your structure — copy, print, or send directly to your accountant.")

    emap = {e["id"]: e["name"] for e in entities}
    today = datetime.now().strftime("%-d %B %Y")

    # ── header ────────────────────────────────────────────────────────────────
    st.markdown(f"**Prepared:** {today}  \n**Subject:** Corporate Structure Overview — Cameron Price")
    st.divider()

    # ── 1. People ─────────────────────────────────────────────────────────────
    people = [e for e in entities if e["type"] == "Individual"]
    st.subheader("1. Key People")
    for p in people:
        directorships = [emap.get(r["to_id"],"?") for r in relationships
                         if r["from_id"] == p["id"] and r["rel_type"] == "Director of"]
        ownerships    = [f"{emap.get(r['to_id'],'?')} ({r.get('detail','')})" for r in relationships
                         if r["from_id"] == p["id"] and r["rel_type"] == "Owns (%)"]
        beneficiary   = [emap.get(r["to_id"],"?") for r in relationships
                         if r["from_id"] == p["id"] and r["rel_type"] == "Beneficiary of"]
        with st.expander(f"**{p['name']}**", expanded=True):
            if directorships:
                st.markdown(f"**Director of:** {', '.join(directorships)}")
            if ownerships:
                st.markdown(f"**Shareholding:** {', '.join(ownerships)}")
            if beneficiary:
                st.markdown(f"**Beneficiary of:** {', '.join(beneficiary)}")
            if p.get("notes"):
                st.caption(p["notes"])

    st.divider()

    # ── 2. Companies ──────────────────────────────────────────────────────────
    companies = [e for e in entities if e["type"] == "Company"]
    holding   = [e for e in companies if e.get("subtype") in ("Holding Co","Shelf")]
    trading   = [e for e in companies if e not in holding]

    st.subheader("2. Holding / Investment Companies")
    for e in holding:
        owners    = [f"{emap.get(r['from_id'],'?')} ({r.get('detail','')})" for r in relationships
                     if r["to_id"] == e["id"] and r["rel_type"] == "Owns (%)"]
        directors = [emap.get(r["from_id"],"?") for r in relationships
                     if r["to_id"] == e["id"] and r["rel_type"] == "Director of"]
        trustee   = [emap.get(r["to_id"],"?") for r in relationships
                     if r["from_id"] == e["id"] and r["rel_type"] == "Trustee of"]
        with st.expander(f"**{e['name']}**", expanded=True):
            c1, c2 = st.columns(2)
            c1.markdown(f"**ABN/ACN:** {e.get('abn') or 'TBC'}")
            c2.markdown(f"**State:** {e.get('state') or 'TBC'}")
            if owners:    st.markdown(f"**Shareholders:** {', '.join(owners)}")
            if directors: st.markdown(f"**Directors:** {', '.join(directors)}")
            if trustee:   st.markdown(f"**Trustee of:** {', '.join(trustee)}")
            if e.get("notes"): st.caption(e["notes"])

    st.subheader("3. Trading / Operating Companies")
    for e in trading:
        owners    = [f"{emap.get(r['from_id'],'?')} ({r.get('detail','')})" for r in relationships
                     if r["to_id"] == e["id"] and r["rel_type"] == "Owns (%)"]
        directors = [emap.get(r["from_id"],"?") for r in relationships
                     if r["to_id"] == e["id"] and r["rel_type"] == "Director of"]
        with st.expander(f"**{e['name']}**", expanded=True):
            c1, c2 = st.columns(2)
            c1.markdown(f"**ABN/ACN:** {e.get('abn') or 'TBC'}")
            c2.markdown(f"**State:** {e.get('state') or 'TBC'}")
            if owners:    st.markdown(f"**Shareholders:** {', '.join(owners)}")
            if directors: st.markdown(f"**Directors:** {', '.join(directors)}")
            if e.get("notes"): st.caption(e["notes"])

    st.divider()

    # ── 3. Trusts ─────────────────────────────────────────────────────────────
    trusts = [e for e in entities if e["type"] in ("Trust", "SMSF")]
    st.subheader("4. Trusts & Superannuation")
    for e in trusts:
        trustee = [emap.get(r["from_id"],"?") for r in relationships
                   if r["to_id"] == e["id"] and r["rel_type"] == "Trustee of"]
        bens    = [f"{emap.get(r['from_id'],'?')} ({r.get('detail','')})" for r in relationships
                   if r["to_id"] == e["id"] and r["rel_type"] == "Beneficiary of"]
        inline  = e.get("beneficiaries", [])
        with st.expander(f"**{e['name']}** ({e['type']})", expanded=True):
            c1, c2 = st.columns(2)
            c1.markdown(f"**ABN/TFN:** {e.get('abn') or 'TBC'}")
            c2.markdown(f"**Type:** {e.get('subtype') or e['type']}")
            if trustee: st.markdown(f"**Trustee:** {', '.join(trustee)}")
            if bens:    st.markdown(f"**Beneficiaries:** {', '.join(bens)}")
            if inline:
                for b in inline:
                    pct = f" — {b['percentage']}%" if b.get("percentage") else ""
                    st.markdown(f"  - {b['name']}{pct}" + (f" ({b['notes']})" if b.get("notes") else ""))
            if e.get("notes"): st.caption(e["notes"])

    st.divider()

    # ── 4. Items to confirm ───────────────────────────────────────────────────
    st.subheader("5. Items to confirm / update")
    missing_abn  = [e["name"] for e in entities if not e.get("abn") and e["type"] != "Individual"]
    missing_rels = [e["name"] for e in entities if e["name"] in
                    {"Decon Services Pty Ltd", "Pathway Recruitment Pty Ltd"}]
    st.markdown("**ABN/ACN not yet entered:**")
    for n in missing_abn:
        st.markdown(f"  - {n}")
    st.markdown("**Ownership structure to be confirmed:**")
    for n in missing_rels:
        st.markdown(f"  - {n} — shareholder(s) and director(s) unknown")
    st.markdown("**Other open questions:**")
    st.markdown("""
  - Teal Property Holdings Pty Ltd — confirm ownership (Cameron personally, via C Price Investments, or via trust?)
  - In Price we Trust — confirm trustee company and full beneficiary list
  - Decon Services / Pathway Recruitment — confirm if Peter Thomas has any involvement
  - Commerce Building Investments Pty Ltd — confirm if still active or dormant
  - B-Sure Pty Ltd distribution ($131,667) — confirm purpose and destination
    """)

    st.divider()
    st.info("To copy this for your accountant: use your browser's print function (Cmd+P) and choose 'Save as PDF'.")


# ══════════════════════════════════════════════════════════════════════════════
# SKILLS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "⚡ Skills":
    st.title("Financial Skills")
    all_skills = load_skills()
    if not all_skills:
        st.warning("No skills found. Drop Python files into the `/skills/` folder.")
    else:
        skill_names = [f"{s.icon}  {s.name}" for s in all_skills]
        chosen = st.radio("Select a skill", skill_names, horizontal=True)
        idx    = skill_names.index(chosen)
        st.divider()
        all_skills[idx].render(entities, relationships, flows)


