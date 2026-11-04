# Headcount and productivity

Quarter-end employees come from the "Number of employees" row in each earnings release (8-K exhibit 99.1);
headcount is not XBRL-tagged. Every quarter appears in two releases (current and year-ago column) and the
two values agree in every case. SQL: `sql/09_productivity.sql`. Per-employee figures are USD thousands.

| fiscal_quarter | employees | employees_yoy | revenue_ttm_per_employee_k | operating_income_ttm_per_employee_k | opex_per_employee_k_quarter |
|---|---:|---:|---:|---:|---:|
| 2024Q4 | 183,323 | +0.4% | 1,909 | 613 | 136 |
| 2025Q1 | 185,719 | +2.7% | 1,937 | 633 | 125 |
| 2025Q2 | 187,103 | +4.2% | 1,985 | 649 | 140 |
| 2025Q3 | 190,167 | +4.9% | 2,027 | 652 | 156 |
| 2025Q4 | 190,820 | +4.1% | 2,111 | 676 | 168 |
| 2026Q1 | 194,668 | +4.8% | 2,170 | 710 | 149 |
| 2026Q2 | 198,933 | +6.3% | 2,241 | 742 | 166 |
| 2026Q3 | 204,757 | +7.7% | 2,301 | 767 | 174 |

- 2026Q3: 204,757 employees (+7.7% YoY); trailing-12-month revenue per employee
  $2.30M vs $2.03M a year earlier.
- Headcount fell from its 2023Q1 peak of 190,711 to 179,582 in 2024Q2
  after the 2023 layoffs, then grew again to a new high.
