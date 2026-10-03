# Findings from the simulated dataset

These come from the default simulation (2024-01-01 to 2025-12-31, 190,949 orders,
764,479 CDC rows), read from the `kpi` marts. The data is synthetic, but the generator encodes
realistic drivers, and the warehouse recovers them from the raw feed without being told
about them.

| # | Finding | Evidence (mart) |
|---|---|---|
| 1 | **The North-East is the weakest region**: 69.6% on-time and 16.4 days order-to-door, against 86.2% and 7.9 days in the West. Five NE states are *critical* (more than 10 points below the national on-time rate). | `mart_state_scorecard` |
| 2 | **Last-mile transit is the bottleneck in 24 of 33 states.** Approval drives the excess in 6 states and warehouse processing in 3. | `mart_stage_bottlenecks` |
| 3 | **Cross-region shipments take almost twice as long** (10.7 vs 5.7 days) and are 10.5 points less on time (79.4% vs 89.9%). Inventory placement matters more than courier choice. | `fct_orders.is_cross_region` |
| 4 | **The October Festive Sale is the most expensive event operationally**: 3.1x volume, +6 h approval, +4.6 days delivery and on-time down about 49 points against its baseline. End-of-season sales cost 15–30 points. | `mart_sale_event_impact` |
| 5 | **COD costs twice over**: approval takes 18.4 h against 10.1 h for prepaid (verification), and the RTO rate doubles (3.6% vs 1.8%). | `fct_orders` by payment method |
| 6 | **Courier spread is about 22 points of on-time rate** (SwiftShip around 90% vs TrailBlaze around 68%). The gap widens on sale days. | `mart_courier_performance` |
| 7 | **The feed itself is noisy**: about 2% of CDC rows arrive 1–3 days late, about 0.5% are re-sent duplicates (3,802 dropped), and 504 orders have delivery timestamps before shipment. All are handled and surfaced in `mart_data_quality_daily`. | `mart_data_quality_daily` |

Overall: average approval is 12.4 h and average order-to-door is 9.4 days, with 82.1% on time.
These match the original dashboard's KPI bands (approval 10–15 h, delivery 8–15 days by state).
