"""Spending planner skill — models a proposed spend and recommends funding source."""
import streamlit as st
from .base import BaseSkill


TAX_RATES = {
    "Company": 0.275,
    "Trust": 0.0,        # depends on distribution — shown as note
    "SMSF": 0.15,
    "Individual": None,  # set by user
    "Partnership": None,
}

MARGINAL_BRACKETS = [
    (18_200, 0.0),
    (45_000, 0.19),
    (120_000, 0.325),
    (180_000, 0.37),
    (float("inf"), 0.45),
]


def marginal_rate(income):
    prev = 0
    tax = 0
    for threshold, rate in MARGINAL_BRACKETS:
        band = min(income, threshold) - prev
        if band <= 0:
            break
        tax += band * rate
        prev = threshold
    return tax / income if income else 0


class SpendingPlannerSkill(BaseSkill):
    name = "Spending Planner"
    description = "Given a spend you want to make, work out the best entity to fund it and the after-tax cost."
    icon = "🛒"

    def render(self, entities, relationships, flows):
        st.subheader(f"{self.icon} {self.name}")
        st.caption("Illustrative — not financial advice.")

        if not entities:
            st.info("Add entities first (use the Entities page).")
            return

        col1, col2 = st.columns(2)
        with col1:
            spend_amount = st.number_input("Amount you want to spend ($)", min_value=0, value=50_000, step=1_000)
            spend_type = st.selectbox("Nature of expense", [
                "Business operating cost",
                "Investment asset",
                "Personal expense",
                "Loan repayment",
                "Dividend / distribution",
            ])
        with col2:
            personal_income = st.number_input("Your personal gross income ($/yr)", min_value=0, value=120_000, step=5_000)
            gst_reg = st.checkbox("You are GST-registered (can claim GST credits)")

        st.markdown("---")
        st.markdown("### Funding source analysis")

        for e in entities:
            etype = e["type"]
            rate = TAX_RATES.get(etype)
            if rate is None:
                rate = marginal_rate(personal_income)

            gross_needed = spend_amount / (1 - rate) if rate < 1 else spend_amount
            gst_saving = spend_amount / 11 if gst_reg and spend_type in (
                "Business operating cost", "Investment asset") else 0
            net_cost = gross_needed - gst_saving

            deductible = spend_type in ("Business operating cost", "Investment asset")
            after_tax = spend_amount * (1 - rate) if deductible else spend_amount
            gross_to_earn = after_tax / (1 - rate) if deductible and rate < 1 else spend_amount

            with st.expander(f"**{e['name']}** ({etype})"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Gross pre-tax needed", f"${gross_needed:,.0f}")
                c2.metric("GST credit saving", f"${gst_saving:,.0f}")
                c3.metric("Net effective cost", f"${net_cost:,.0f}")

                if etype == "Trust":
                    st.info("Trust tax depends on who receives the distribution. Rates above use 0% as a placeholder — apply beneficiary marginal rates.")
                if deductible:
                    st.success(f"This expense is likely **tax-deductible** inside a {etype}.")
                else:
                    st.warning("Personal expenses are generally not deductible inside a business entity.")
