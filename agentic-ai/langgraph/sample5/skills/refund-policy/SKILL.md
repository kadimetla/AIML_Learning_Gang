---
name: refund-policy
description: Decide whether a customer order is eligible for a refund. Use when the user asks about refunding, returning, or cancelling an order.
---

Follow this procedure exactly:

1. Call the `lookup_order` tool with the order id to get its status, total and age in days.
2. Apply the rules:
   - Delivered 30 days ago or less: full refund.
   - Delivered 31-60 days ago: store credit only.
   - Older than 60 days, or status `final_sale`: not refundable.
3. If the total is over $500, also read `references/escalation.md` (use
   `read_skill_file`) -- large refunds need manager approval.
4. Answer with the decision and the one rule that decided it.
