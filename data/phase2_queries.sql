-- ============================================================
-- NexaCommerce Analytics — Phase 2: KPI Query Library
-- Run against: nexacommerce.db
-- Generated  : Phase 2 pipeline
-- ============================================================


-- ── INDEXES ──────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_orders_customer   ON orders(customer_id);CREATE INDEX IF NOT EXISTS idx_orders_date       ON orders(order_date);CREATE INDEX IF NOT EXISTS idx_orders_status     ON orders(status);CREATE INDEX IF NOT EXISTS idx_items_order       ON order_items(order_id);CREATE INDEX IF NOT EXISTS idx_items_product     ON order_items(product_id);CREATE INDEX IF NOT EXISTS idx_events_customer   ON events(customer_id);CREATE INDEX IF NOT EXISTS idx_events_type       ON events(event_type);CREATE INDEX IF NOT EXISTS idx_customers_segment ON customers(segment);CREATE INDEX IF NOT EXISTS idx_customers_churn   ON customers(churned);


-- ── REVENUE: Monthly trend ────────────────────────────────────
-- vw_monthly_revenue

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


-- ── REVENUE: By category ─────────────────────────────────────
-- vw_revenue_by_category

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


-- ── REVENUE: By acquisition channel ──────────────────────────
-- vw_revenue_by_channel (not a view, run ad-hoc)

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


-- ── REVENUE: Month-over-month growth ─────────────────────────
-- vw_mom_growth

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


-- ── CUSTOMERS: Segment breakdown ─────────────────────────────
-- vw_segment_stats

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


-- ── CUSTOMERS: LTV buckets ───────────────────────────────────

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


-- ── CUSTOMERS: New per month ─────────────────────────────────

SELECT
    strftime('%Y-%m', signup_date)     AS month,
    COUNT(*)                           AS new_customers,
    SUM(COUNT(*)) OVER (ORDER BY strftime('%Y-%m', signup_date)) AS cumulative_customers
FROM customers
GROUP BY month
ORDER BY month;


-- ── RETENTION: Cohort matrix ─────────────────────────────────
-- vw_cohort_retention

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


-- ── CHURN: By segment ────────────────────────────────────────
-- vw_churn_by_segment

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


-- ── CHURN: By acquisition channel ────────────────────────────

SELECT
    acquisition_channel,
    COUNT(*)                                          AS total,
    SUM(CASE WHEN churned=1 THEN 1 ELSE 0 END)        AS churned,
    ROUND(SUM(CASE WHEN churned=1 THEN 1.0 ELSE 0 END)
          / COUNT(*) * 100, 1)                        AS churn_rate_pct
FROM customers
GROUP BY acquisition_channel
ORDER BY churn_rate_pct DESC;


-- ── CHURN: At-risk customers (active, 45-90 days idle) ───────

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


-- ── FUNNEL: Conversion ───────────────────────────────────────
-- vw_funnel

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


-- ── PRODUCTS: Top 20 by revenue ──────────────────────────────
-- vw_top_products

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


-- ── PRODUCTS: Category margins ───────────────────────────────

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

