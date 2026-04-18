"""
NexaCommerce Analytics — Phase 2
SQL Schema, Views & KPI Queries
=====================================
Covers:
  1.  Schema inspection & index creation
  2.  Revenue KPIs  — monthly, by category, by channel
  3.  Customer KPIs — segments, LTV distribution
  4.  Retention     — cohort matrix (month-over-month)
  5.  Churn         — rate trend, at-risk segment
  6.  Funnel        — event conversion funnel
  7.  Product KPIs  — top products, margin leaders
  8.  Pre-built SQL Views saved to DB
  9.  All results exported to CSV
"""

import sqlite3
import pandas as pd
import os

DB_PATH    = r"D:\Python Projects\Project - 1\data\nexacommerce.db"
OUT_DIR    = r"D:\Python Projects\Project - 1\data\kpi_outputs"
SQL_FILE   = r"D:\Python Projects\Project - 1\data\phase2_queries.sql"
os.makedirs(OUT_DIR, exist_ok=True)

conn = sqlite3.connect(DB_PATH)

print("=" * 60)
print("  NexaCommerce — Phase 2: SQL Schema & KPI Queries")
print("=" * 60)


# ─────────────────────────────────────────────────────────────
# SECTION 1 — INDEXES  (speed up joins & group-bys)
# ─────────────────────────────────────────────────────────────
print("\n[1/8] Creating indexes...")

indexes = [
    "CREATE INDEX IF NOT EXISTS idx_orders_customer   ON orders(customer_id);",
    "CREATE INDEX IF NOT EXISTS idx_orders_date       ON orders(order_date);",
    "CREATE INDEX IF NOT EXISTS idx_orders_status     ON orders(status);",
    "CREATE INDEX IF NOT EXISTS idx_items_order       ON order_items(order_id);",
    "CREATE INDEX IF NOT EXISTS idx_items_product     ON order_items(product_id);",
    "CREATE INDEX IF NOT EXISTS idx_events_customer   ON events(customer_id);",
    "CREATE INDEX IF NOT EXISTS idx_events_type       ON events(event_type);",
    "CREATE INDEX IF NOT EXISTS idx_customers_segment ON customers(segment);",
    "CREATE INDEX IF NOT EXISTS idx_customers_churn   ON customers(churned);",
]
for idx in indexes:
    conn.execute(idx)
conn.commit()
print(f"   ✓ {len(indexes)} indexes created")


# ─────────────────────────────────────────────────────────────
# SECTION 2 — REVENUE KPIs
# ─────────────────────────────────────────────────────────────
print("\n[2/8] Revenue KPIs...")

# 2a. Monthly revenue trend
Q_MONTHLY_REVENUE = """
SELECT
    strftime('%Y-%m', order_date)          AS month,
    COUNT(DISTINCT customer_id)            AS unique_customers,
    COUNT(order_id)                        AS total_orders,
    ROUND(SUM(total), 2)                   AS gross_revenue,
    ROUND(SUM(total) / COUNT(order_id), 2) AS avg_order_value,
    ROUND(SUM(CASE WHEN status='refunded'
                   THEN total ELSE 0 END), 2) AS refunded_amount,
    ROUND(SUM(CASE WHEN status='completed'
                   THEN total ELSE 0 END), 2) AS net_revenue
FROM orders
GROUP BY month
ORDER BY month;
"""

# 2b. Revenue by product category
Q_REVENUE_BY_CATEGORY = """
SELECT
    p.category,
    COUNT(DISTINCT o.customer_id)          AS unique_buyers,
    COUNT(DISTINCT o.order_id)             AS total_orders,
    ROUND(SUM(oi.line_total), 2)           AS gross_revenue,
    ROUND(AVG(oi.unit_price), 2)           AS avg_unit_price,
    ROUND(SUM(oi.line_total) * 1.0 /
          (SELECT SUM(line_total) FROM order_items) * 100, 1) AS revenue_share_pct
FROM order_items oi
JOIN orders  o  ON oi.order_id   = o.order_id
JOIN products p ON oi.product_id = p.product_id
WHERE o.status = 'completed'
GROUP BY p.category
ORDER BY gross_revenue DESC;
"""

# 2c. Revenue by acquisition channel
Q_REVENUE_BY_CHANNEL = """
SELECT
    c.acquisition_channel,
    COUNT(DISTINCT c.customer_id)          AS total_customers,
    COUNT(DISTINCT o.order_id)             AS total_orders,
    ROUND(SUM(o.total), 2)                 AS total_revenue,
    ROUND(SUM(o.total) / COUNT(DISTINCT c.customer_id), 2) AS revenue_per_customer
FROM customers c
LEFT JOIN orders o ON c.customer_id = o.customer_id
                   AND o.status = 'completed'
GROUP BY c.acquisition_channel
ORDER BY total_revenue DESC;
"""

# 2d. Month-over-month growth rate
Q_MOM_GROWTH = """
WITH monthly AS (
    SELECT
        strftime('%Y-%m', order_date) AS month,
        ROUND(SUM(total), 2)          AS revenue
    FROM orders
    WHERE status = 'completed'
    GROUP BY month
),
with_prev AS (
    SELECT
        month,
        revenue,
        LAG(revenue) OVER (ORDER BY month) AS prev_revenue
    FROM monthly
)
SELECT
    month,
    revenue,
    prev_revenue,
    CASE WHEN prev_revenue IS NOT NULL AND prev_revenue > 0
         THEN ROUND((revenue - prev_revenue) / prev_revenue * 100, 2)
         ELSE NULL
    END AS mom_growth_pct
FROM with_prev
ORDER BY month;
"""

df_monthly_rev   = pd.read_sql(Q_MONTHLY_REVENUE,     conn)
df_cat_rev       = pd.read_sql(Q_REVENUE_BY_CATEGORY, conn)
df_channel_rev   = pd.read_sql(Q_REVENUE_BY_CHANNEL,  conn)
df_mom           = pd.read_sql(Q_MOM_GROWTH,          conn)

df_monthly_rev.to_csv(f"{OUT_DIR}/revenue_monthly.csv",   index=False)
df_cat_rev.to_csv(f"{OUT_DIR}/revenue_by_category.csv",   index=False)
df_channel_rev.to_csv(f"{OUT_DIR}/revenue_by_channel.csv",index=False)
df_mom.to_csv(f"{OUT_DIR}/revenue_mom_growth.csv",        index=False)

total_rev = df_monthly_rev['net_revenue'].sum()
avg_mom   = df_mom['mom_growth_pct'].dropna().mean()
print(f"   ✓ Total net revenue   : ${total_rev:>12,.2f}")
print(f"   ✓ Avg MoM growth rate : {avg_mom:>+.1f}%")
print(f"   ✓ Top category        : {df_cat_rev.iloc[0]['category']} (${df_cat_rev.iloc[0]['gross_revenue']:,.0f})")


# ─────────────────────────────────────────────────────────────
# SECTION 3 — CUSTOMER KPIs
# ─────────────────────────────────────────────────────────────
print("\n[3/8] Customer KPIs...")

# 3a. Segment breakdown
Q_SEGMENT_STATS = """
SELECT
    segment,
    COUNT(*)                                AS total_customers,
    ROUND(COUNT(*) * 100.0 /
          (SELECT COUNT(*) FROM customers), 1) AS pct_of_base,
    ROUND(AVG(total_revenue), 2)            AS avg_ltv,
    ROUND(AVG(avg_order_value), 2)          AS avg_order_value,
    ROUND(AVG(total_orders), 1)             AS avg_orders,
    SUM(CASE WHEN churned=1 THEN 1 ELSE 0 END) AS churned_count,
    ROUND(SUM(CASE WHEN churned=1 THEN 1.0 ELSE 0 END)
          / COUNT(*) * 100, 1)              AS churn_rate_pct
FROM customers
GROUP BY segment
ORDER BY avg_ltv DESC;
"""

# 3b. LTV buckets
Q_LTV_BUCKETS = """
SELECT
    CASE
        WHEN total_revenue = 0         THEN '0 — No orders'
        WHEN total_revenue < 500       THEN '$1–$499'
        WHEN total_revenue < 1000      THEN '$500–$999'
        WHEN total_revenue < 2500      THEN '$1k–$2.5k'
        WHEN total_revenue < 5000      THEN '$2.5k–$5k'
        WHEN total_revenue < 10000     THEN '$5k–$10k'
        ELSE '$10k+'
    END AS ltv_bucket,
    COUNT(*)                           AS customers,
    ROUND(AVG(total_revenue), 2)       AS avg_ltv,
    ROUND(SUM(total_revenue), 2)       AS total_revenue
FROM customers
GROUP BY ltv_bucket
ORDER BY avg_ltv;
"""

# 3c. New customers per month
Q_NEW_CUSTOMERS = """
SELECT
    strftime('%Y-%m', signup_date)     AS month,
    COUNT(*)                           AS new_customers,
    SUM(COUNT(*)) OVER (ORDER BY strftime('%Y-%m', signup_date)) AS cumulative_customers
FROM customers
GROUP BY month
ORDER BY month;
"""

df_segments    = pd.read_sql(Q_SEGMENT_STATS,  conn)
df_ltv_buckets = pd.read_sql(Q_LTV_BUCKETS,   conn)
df_new_custs   = pd.read_sql(Q_NEW_CUSTOMERS,  conn)

df_segments.to_csv(f"{OUT_DIR}/customer_segments.csv",   index=False)
df_ltv_buckets.to_csv(f"{OUT_DIR}/customer_ltv_buckets.csv", index=False)
df_new_custs.to_csv(f"{OUT_DIR}/new_customers_monthly.csv",  index=False)

print(f"   ✓ Segments analysed   : {len(df_segments)}")
print(f"   ✓ VIP avg LTV         : ${df_segments[df_segments['segment']=='vip']['avg_ltv'].values[0]:,.2f}")
print(f"   ✓ Budget avg LTV      : ${df_segments[df_segments['segment']=='budget']['avg_ltv'].values[0]:,.2f}")


# ─────────────────────────────────────────────────────────────
# SECTION 4 — RETENTION COHORT MATRIX
# ─────────────────────────────────────────────────────────────
print("\n[4/8] Building cohort retention matrix...")

Q_COHORT_BASE = """
WITH first_orders AS (
    SELECT
        customer_id,
        MIN(substr(order_date,1,7)) AS cohort_month
    FROM orders
    WHERE status = 'completed'
    GROUP BY customer_id
),
order_periods AS (
    SELECT
        o.customer_id,
        fo.cohort_month,
        substr(o.order_date,1,7) AS order_month,
        (CAST(substr(o.order_date,1,4) AS INT) - CAST(substr(fo.cohort_month,1,4) AS INT)) * 12
        + (CAST(substr(o.order_date,6,2) AS INT) - CAST(substr(fo.cohort_month,6,2) AS INT))
        AS period_number
    FROM orders o
    JOIN first_orders fo ON o.customer_id = fo.customer_id
    WHERE o.status = 'completed'
),
cohort_sizes AS (
    SELECT cohort_month, COUNT(DISTINCT customer_id) AS cohort_size
    FROM first_orders
    GROUP BY cohort_month
),
retained AS (
    SELECT
        cohort_month,
        period_number,
        COUNT(DISTINCT customer_id) AS retained_customers
    FROM order_periods
    GROUP BY cohort_month, period_number
)
SELECT
    r.cohort_month,
    cs.cohort_size,
    r.period_number,
    r.retained_customers,
    ROUND(r.retained_customers * 100.0 / cs.cohort_size, 1) AS retention_pct
FROM retained r
JOIN cohort_sizes cs ON r.cohort_month = cs.cohort_month
ORDER BY r.cohort_month, r.period_number;
"""

df_cohort_raw = pd.read_sql(Q_COHORT_BASE, conn)
df_cohort_raw.to_csv(f"{OUT_DIR}/cohort_raw.csv", index=False)

# Pivot into a heatmap matrix
df_cohort_matrix = df_cohort_raw.pivot_table(
    index="cohort_month",
    columns="period_number",
    values="retention_pct",
    aggfunc="first"
)
df_cohort_matrix.columns = [f"Month {c}" for c in df_cohort_matrix.columns]
df_cohort_matrix.index.name = "Cohort"
df_cohort_matrix.to_csv(f"{OUT_DIR}/cohort_matrix.csv")

# Key finding: Month-3 retention drop
if 1 in df_cohort_raw["period_number"].values and 3 in df_cohort_raw["period_number"].values:
    m1 = df_cohort_raw[df_cohort_raw["period_number"]==1]["retention_pct"].mean()
    m3 = df_cohort_raw[df_cohort_raw["period_number"]==3]["retention_pct"].mean()
    drop = m1 - m3
    print(f"   ✓ Avg Month-1 retention : {m1:.1f}%")
    print(f"   ✓ Avg Month-3 retention : {m3:.1f}%")
    print(f"   ✓ DROP identified       : -{drop:.1f}pp  ← THE PROBLEM")
else:
    print(f"   ✓ Cohort matrix built: {df_cohort_matrix.shape[0]} cohorts x {df_cohort_matrix.shape[1]} periods")


# ─────────────────────────────────────────────────────────────
# SECTION 5 — CHURN KPIs
# ─────────────────────────────────────────────────────────────
print("\n[5/8] Churn analysis...")

# 5a. Overall churn by segment
Q_CHURN_BY_SEGMENT = """
SELECT
    segment,
    COUNT(*)                                          AS total,
    SUM(CASE WHEN churned=1 THEN 1 ELSE 0 END)        AS churned,
    ROUND(SUM(CASE WHEN churned=1 THEN 1.0 ELSE 0 END)
          / COUNT(*) * 100, 1)                        AS churn_rate_pct,
    ROUND(AVG(CASE WHEN churned=0 THEN total_revenue END), 2) AS active_avg_ltv,
    ROUND(AVG(CASE WHEN churned=1 THEN total_revenue END), 2) AS churned_avg_ltv
FROM customers
GROUP BY segment
ORDER BY churn_rate_pct DESC;
"""

# 5b. Churn by acquisition channel
Q_CHURN_BY_CHANNEL = """
SELECT
    acquisition_channel,
    COUNT(*)                                          AS total,
    SUM(CASE WHEN churned=1 THEN 1 ELSE 0 END)        AS churned,
    ROUND(SUM(CASE WHEN churned=1 THEN 1.0 ELSE 0 END)
          / COUNT(*) * 100, 1)                        AS churn_rate_pct
FROM customers
GROUP BY acquisition_channel
ORDER BY churn_rate_pct DESC;
"""

# 5c. At-risk customers (active but showing churn signals)
Q_AT_RISK = """
SELECT
    customer_id,
    segment,
    total_revenue,
    total_orders,
    last_order,
    CAST(julianday('2024-03-31') - julianday(last_order) AS INTEGER) AS days_since_last_order,
    CASE
        WHEN CAST(julianday('2024-03-31') - julianday(last_order) AS INTEGER) BETWEEN 60 AND 90
             THEN 'High risk'
        WHEN CAST(julianday('2024-03-31') - julianday(last_order) AS INTEGER) BETWEEN 45 AND 59
             THEN 'Medium risk'
        ELSE 'Watch'
    END AS risk_level
FROM customers
WHERE churned = 0
  AND last_order IS NOT NULL
  AND CAST(julianday('2024-03-31') - julianday(last_order) AS INTEGER) >= 45
ORDER BY total_revenue DESC
LIMIT 500;
"""

df_churn_seg  = pd.read_sql(Q_CHURN_BY_SEGMENT, conn)
df_churn_chan = pd.read_sql(Q_CHURN_BY_CHANNEL,  conn)
df_at_risk    = pd.read_sql(Q_AT_RISK,           conn)

df_churn_seg.to_csv(f"{OUT_DIR}/churn_by_segment.csv",  index=False)
df_churn_chan.to_csv(f"{OUT_DIR}/churn_by_channel.csv",  index=False)
df_at_risk.to_csv(f"{OUT_DIR}/at_risk_customers.csv",    index=False)

overall_churn = pd.read_sql(
    "SELECT ROUND(AVG(churned)*100,1) AS rate FROM customers", conn
).iloc[0,0]
high_risk_rev = df_at_risk[df_at_risk["risk_level"]=="High risk"]["total_revenue"].sum()
print(f"   ✓ Overall churn rate    : {overall_churn}%")
print(f"   ✓ At-risk customers     : {len(df_at_risk):,}")
print(f"   ✓ High-risk revenue     : ${high_risk_rev:,.2f} at stake")
print(f"   ✓ Highest churn channel : {df_churn_chan.iloc[0]['acquisition_channel']} ({df_churn_chan.iloc[0]['churn_rate_pct']}%)")


# ─────────────────────────────────────────────────────────────
# SECTION 6 — EVENT FUNNEL
# ─────────────────────────────────────────────────────────────
print("\n[6/8] Conversion funnel...")

Q_FUNNEL = """
SELECT
    event_type,
    COUNT(DISTINCT customer_id)  AS unique_users,
    COUNT(*)                     AS total_events
FROM events
WHERE event_type IN (
    'page_view','product_view','add_to_cart',
    'checkout_start','checkout_complete'
)
GROUP BY event_type
ORDER BY
    CASE event_type
        WHEN 'page_view'          THEN 1
        WHEN 'product_view'       THEN 2
        WHEN 'add_to_cart'        THEN 3
        WHEN 'checkout_start'     THEN 4
        WHEN 'checkout_complete'  THEN 5
    END;
"""

df_funnel = pd.read_sql(Q_FUNNEL, conn)
# Add conversion rates
top = df_funnel["unique_users"].iloc[0]
df_funnel["conv_from_top_pct"] = (df_funnel["unique_users"] / top * 100).round(1)
df_funnel["step_conv_pct"]     = (
    df_funnel["unique_users"] / df_funnel["unique_users"].shift(1) * 100
).round(1)
df_funnel.to_csv(f"{OUT_DIR}/funnel_conversion.csv", index=False)

cart_to_checkout = df_funnel[df_funnel["event_type"]=="checkout_start"]["unique_users"].values[0]
add_to_cart      = df_funnel[df_funnel["event_type"]=="add_to_cart"]["unique_users"].values[0]
abandon_rate     = round((1 - cart_to_checkout / add_to_cart) * 100, 1)
print(f"   ✓ Funnel steps         : {len(df_funnel)}")
print(f"   ✓ Cart abandon rate    : {abandon_rate}%  ← friction point")
print(df_funnel[["event_type","unique_users","conv_from_top_pct"]].to_string(index=False))


# ─────────────────────────────────────────────────────────────
# SECTION 7 — PRODUCT KPIs
# ─────────────────────────────────────────────────────────────
print("\n[7/8] Product KPIs...")

Q_TOP_PRODUCTS = """
SELECT
    p.product_id,
    p.name,
    p.category,
    p.price,
    p.margin_pct,
    COUNT(DISTINCT oi.order_id)        AS orders_count,
    SUM(oi.quantity)                   AS units_sold,
    ROUND(SUM(oi.line_total), 2)       AS total_revenue,
    ROUND(SUM(oi.line_total) * p.margin_pct / 100, 2) AS gross_profit
FROM order_items oi
JOIN products p ON oi.product_id = p.product_id
JOIN orders   o ON oi.order_id   = o.order_id
WHERE o.status = 'completed'
GROUP BY p.product_id
ORDER BY total_revenue DESC
LIMIT 20;
"""

Q_CATEGORY_MARGIN = """
SELECT
    p.category,
    ROUND(AVG(p.margin_pct), 1)         AS avg_margin_pct,
    ROUND(SUM(oi.line_total), 2)         AS total_revenue,
    ROUND(SUM(oi.line_total * p.margin_pct / 100), 2) AS total_gross_profit
FROM order_items oi
JOIN products p ON oi.product_id = p.product_id
JOIN orders   o ON oi.order_id   = o.order_id
WHERE o.status = 'completed'
GROUP BY p.category
ORDER BY total_gross_profit DESC;
"""

df_top_products  = pd.read_sql(Q_TOP_PRODUCTS,    conn)
df_cat_margin    = pd.read_sql(Q_CATEGORY_MARGIN,  conn)

df_top_products.to_csv(f"{OUT_DIR}/top_products.csv",    index=False)
df_cat_margin.to_csv(f"{OUT_DIR}/category_margins.csv",  index=False)

print(f"   ✓ Top product          : {df_top_products.iloc[0]['name']} (${df_top_products.iloc[0]['total_revenue']:,.0f})")
print(f"   ✓ Best margin category : {df_cat_margin.iloc[0]['category']} ({df_cat_margin.iloc[0]['avg_margin_pct']}%)")


# ─────────────────────────────────────────────────────────────
# SECTION 8 — CREATE SQL VIEWS IN DB
# ─────────────────────────────────────────────────────────────
print("\n[8/8] Creating SQL views in database...")

VIEWS = {
    "vw_monthly_revenue": Q_MONTHLY_REVENUE,
    "vw_revenue_by_category": Q_REVENUE_BY_CATEGORY,
    "vw_segment_stats": Q_SEGMENT_STATS,
    "vw_cohort_retention": Q_COHORT_BASE,
    "vw_churn_by_segment": Q_CHURN_BY_SEGMENT,
    "vw_funnel": Q_FUNNEL,
    "vw_top_products": Q_TOP_PRODUCTS.replace("LIMIT 20", ""),
    "vw_mom_growth": Q_MOM_GROWTH,
}

for view_name, query in VIEWS.items():
    conn.execute(f"DROP VIEW IF EXISTS {view_name};")
    conn.execute(f"CREATE VIEW {view_name} AS {query}")
conn.commit()
print(f"   ✓ {len(VIEWS)} views created in nexacommerce.db")
print(f"   ✓ Views: {', '.join(VIEWS.keys())}")


# ─────────────────────────────────────────────────────────────
# EXPORT ALL QUERIES TO .SQL FILE
# ─────────────────────────────────────────────────────────────
sql_content = f"""-- ============================================================
-- NexaCommerce Analytics — Phase 2: KPI Query Library
-- Run against: nexacommerce.db
-- Generated  : Phase 2 pipeline
-- ============================================================


-- ── INDEXES ──────────────────────────────────────────────────
{"".join(indexes)}


-- ── REVENUE: Monthly trend ────────────────────────────────────
-- vw_monthly_revenue
{Q_MONTHLY_REVENUE}

-- ── REVENUE: By category ─────────────────────────────────────
-- vw_revenue_by_category
{Q_REVENUE_BY_CATEGORY}

-- ── REVENUE: By acquisition channel ──────────────────────────
-- vw_revenue_by_channel (not a view, run ad-hoc)
{Q_REVENUE_BY_CHANNEL}

-- ── REVENUE: Month-over-month growth ─────────────────────────
-- vw_mom_growth
{Q_MOM_GROWTH}

-- ── CUSTOMERS: Segment breakdown ─────────────────────────────
-- vw_segment_stats
{Q_SEGMENT_STATS}

-- ── CUSTOMERS: LTV buckets ───────────────────────────────────
{Q_LTV_BUCKETS}

-- ── CUSTOMERS: New per month ─────────────────────────────────
{Q_NEW_CUSTOMERS}

-- ── RETENTION: Cohort matrix ─────────────────────────────────
-- vw_cohort_retention
{Q_COHORT_BASE}

-- ── CHURN: By segment ────────────────────────────────────────
-- vw_churn_by_segment
{Q_CHURN_BY_SEGMENT}

-- ── CHURN: By acquisition channel ────────────────────────────
{Q_CHURN_BY_CHANNEL}

-- ── CHURN: At-risk customers (active, 45-90 days idle) ───────
{Q_AT_RISK}

-- ── FUNNEL: Conversion ───────────────────────────────────────
-- vw_funnel
{Q_FUNNEL}

-- ── PRODUCTS: Top 20 by revenue ──────────────────────────────
-- vw_top_products
{Q_TOP_PRODUCTS}

-- ── PRODUCTS: Category margins ───────────────────────────────
{Q_CATEGORY_MARGIN}
"""

with open(SQL_FILE, "w", encoding="utf-8") as f:
    f.write(sql_content)

conn.close()

# ─────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  PHASE 2 COMPLETE")
print("=" * 60)
print(f"  SQL views created     : {len(VIEWS)}")
print(f"  CSV exports           : {len(os.listdir(OUT_DIR))}")
print(f"  Query library saved   : phase2_queries.sql")
print(f"\n  Key findings:")
print(f"    • Total net revenue  : ${total_rev:,.0f}")
print(f"    • Avg MoM growth     : {avg_mom:+.1f}%")
print(f"    • Overall churn rate : {overall_churn}%")
print(f"    • Cart abandon rate  : {abandon_rate}%")
print(f"    • At-risk customers  : {len(df_at_risk):,}")
print("=" * 60)
print("\n  Next → Phase 3: KPI analysis & Problem→Solution→Impact")