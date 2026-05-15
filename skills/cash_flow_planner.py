"""Cash flow planning skill — models how money moves across entities."""
import streamlit as st
import plotly.graph_objects as go
from .base import BaseSkill


class CashFlowPlannerSkill(BaseSkill):
    name = "Cash Flow Planner"
    description = "Model and visualise money movement across your entity structure."
    icon = "💸"

    def render(self, entities, relationships, flows):
        st.subheader(f"{self.icon} {self.name}")
        st.write(self.description)

        if not entities:
            st.info("Add entities first (use the Entities page).")
            return

        entity_map = {e["id"]: e["name"] for e in entities}

        # ── Sankey flow diagram ──────────────────────────────────────────────
        active_flows = [f for f in flows if f.get("amount", 0) > 0]
        if active_flows:
            st.markdown("### Flow diagram")
            ids = list(entity_map.keys())
            idx = {eid: i for i, eid in enumerate(ids)}
            labels = [entity_map[i] for i in ids]
            sources, targets, values, flow_labels = [], [], [], []
            for f in active_flows:
                if f["from_id"] in idx and f["to_id"] in idx:
                    sources.append(idx[f["from_id"]])
                    targets.append(idx[f["to_id"]])
                    values.append(f["amount"])
                    flow_labels.append(f.get("label", ""))
            if sources:
                fig = go.Figure(go.Sankey(
                    node=dict(label=labels, pad=20, thickness=20),
                    link=dict(source=sources, target=targets, value=values,
                              label=flow_labels),
                ))
                fig.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=10))
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No flows with amounts yet. Add flows via the Flows page.")

        # ── Net position table ───────────────────────────────────────────────
        st.markdown("### Net positions (annual)")
        net = {e["id"]: 0.0 for e in entities}
        for f in active_flows:
            if f["from_id"] in net:
                net[f["from_id"]] -= f["amount"] * _freq_factor(f.get("frequency", "Annual"))
            if f["to_id"] in net:
                net[f["to_id"]] += f["amount"] * _freq_factor(f.get("frequency", "Annual"))
        rows = [{"Entity": entity_map[eid], "Net ($/yr)": f"{v:,.0f}"} for eid, v in net.items()]
        st.table(rows)


def _freq_factor(freq: str) -> float:
    return {"Weekly": 52, "Fortnightly": 26, "Monthly": 12,
            "Quarterly": 4, "Annual": 1}.get(freq, 1)
