"""Investment routing advisor — recommends which entity should hold an investment."""
import streamlit as st
from .base import BaseSkill

ENTITY_PROS = {
    "Company":     {"Tax rate": "Flat 25–30%", "CGT discount": "None (hold >12m via trust)", "Asset protection": "Moderate", "Flexibility": "Low"},
    "Trust":       {"Tax rate": "Distributed to beneficiaries", "CGT discount": "50% if individual beneficiary holds >12m", "Asset protection": "High", "Flexibility": "High"},
    "SMSF":        {"Tax rate": "15% (10% on capital gains if held >12m)", "CGT discount": "N/A — concessional rate", "Asset protection": "Very High (pension phase)", "Flexibility": "Low (strict rules)"},
    "Individual":  {"Tax rate": "Marginal rate", "CGT discount": "50% if held >12m", "Asset protection": "Low", "Flexibility": "High"},
    "Partnership": {"Tax rate": "Distributed to partners at marginal rate", "CGT discount": "50% for individual partners >12m", "Asset protection": "Low", "Flexibility": "Moderate"},
}


class InvestmentAdvisorSkill(BaseSkill):
    name = "Investment Routing Advisor"
    description = "Recommends the optimal entity to hold an investment based on type, hold period, and goals."
    icon = "📈"

    def render(self, entities, relationships, flows):
        st.subheader(f"{self.icon} {self.name}")
        st.caption("General guidance only — confirm with your accountant/financial adviser.")

        if not entities:
            st.info("Add entities first (use the Entities page).")
            return

        entity_types = list({e["type"] for e in entities})

        col1, col2 = st.columns(2)
        with col1:
            inv_type = st.selectbox("Investment type", [
                "Shares / ETFs", "Property", "Business purchase",
                "Private equity", "Cash / term deposits", "Crypto",
            ])
            hold_years = st.slider("Expected hold period (years)", 0, 30, 5)
        with col2:
            primary_goal = st.selectbox("Primary goal", [
                "Wealth accumulation", "Asset protection",
                "Income distribution", "Retirement funding",
                "Estate planning",
            ])
            marginal_rate = st.slider("Your personal marginal tax rate (%)", 0, 47, 34)

        st.markdown("---")
        st.markdown("### Recommendations for your entity types")

        scored = []
        for etype in entity_types:
            if etype not in ENTITY_PROS:
                continue
            score = _score(etype, inv_type, hold_years, primary_goal, marginal_rate)
            scored.append((score, etype))
        scored.sort(reverse=True)

        for score, etype in scored:
            matching = [e["name"] for e in entities if e["type"] == etype]
            pros = ENTITY_PROS[etype]
            rating = "⭐⭐⭐" if score >= 7 else "⭐⭐" if score >= 4 else "⭐"
            with st.expander(f"{rating}  **{etype}** — entities: {', '.join(matching)}", expanded=score >= 7):
                col_a, col_b = st.columns(2)
                with col_a:
                    for k, v in pros.items():
                        st.markdown(f"**{k}:** {v}")
                with col_b:
                    st.markdown(f"**Fit score:** {score}/10")
                    notes = _notes(etype, inv_type, hold_years, primary_goal)
                    for n in notes:
                        st.markdown(f"- {n}")


def _score(etype, inv_type, hold_years, goal, marginal_rate):
    s = 5
    if etype == "SMSF":
        if goal == "Retirement funding":
            s += 3
        if hold_years >= 10:
            s += 1
        if marginal_rate >= 37:
            s += 1
    if etype == "Trust":
        if goal in ("Asset protection", "Estate planning", "Income distribution"):
            s += 2
        if inv_type in ("Shares / ETFs", "Property") and hold_years >= 1:
            s += 2
    if etype == "Company":
        if inv_type == "Business purchase":
            s += 2
        if goal == "Wealth accumulation" and marginal_rate >= 37:
            s += 1
    if etype == "Individual":
        if marginal_rate <= 19:
            s += 2
        if hold_years >= 1:
            s += 1
    return min(s, 10)


def _notes(etype, inv_type, hold_years, goal):
    notes = []
    if etype == "Trust" and inv_type == "Property":
        notes.append("Land tax surcharge applies to trusts in some states — check your state rules.")
    if etype == "SMSF" and inv_type == "Crypto":
        notes.append("Crypto is permissible if the SMSF investment strategy allows it.")
    if etype == "Company" and hold_years >= 1:
        notes.append("Companies don't get the 50% CGT discount — consider trust ownership for long holds.")
    if etype == "Individual" and goal == "Asset protection":
        notes.append("Individuals offer minimal asset protection. Consider a trust as the holding structure.")
    if not notes:
        notes.append("No specific caveats for this combination.")
    return notes
