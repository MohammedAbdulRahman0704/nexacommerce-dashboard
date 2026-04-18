import sqlite3
import pandas as pd

conn = sqlite3.connect(r"D:\Python Projects\Project - 1\data\nexacommerce.db")

# Revenue monthly
rev = pd.read_sql("""
SELECT substr(order_date,1,7) as month,
ROUND(SUM(CASE WHEN status='completed' THEN total ELSE 0 END),0) as revenue,
COUNT(DISTINCT customer_id) as buyers
FROM orders
GROUP BY month
ORDER BY month
""", conn)

print("Revenue months:", len(rev))


# Cohort matrix
cohort = pd.read_sql("""
WITH fo AS (
    SELECT customer_id, MIN(substr(order_date,1,7)) AS cm
    FROM orders WHERE status='completed'
    GROUP BY customer_id
),
op AS (
    SELECT o.customer_id, fo.cm,
    (CAST(substr(o.order_date,1,4) AS INT)-CAST(substr(fo.cm,1,4) AS INT))*12 +
    (CAST(substr(o.order_date,6,2) AS INT)-CAST(substr(fo.cm,6,2) AS INT)) AS p
    FROM orders o
    JOIN fo ON o.customer_id=fo.customer_id
    WHERE o.status='completed'
),
cs AS (
    SELECT cm, COUNT(DISTINCT customer_id) AS sz FROM fo GROUP BY cm
),
r AS (
    SELECT cm, p, COUNT(DISTINCT customer_id) AS rc FROM op GROUP BY cm,p
)
SELECT r.cm, cs.sz, r.p,
ROUND(r.rc*100.0/cs.sz,1) AS pct
FROM r JOIN cs ON r.cm=cs.cm
WHERE r.p<=12
ORDER BY r.cm, r.p
""", conn)

print("Cohort rows:", len(cohort))


# Segments
seg = pd.read_sql("""
SELECT segment,
COUNT(*) as n,
ROUND(AVG(total_revenue),0) as avg_ltv,
ROUND(SUM(churned)*100.0/COUNT(*),1) as churn_rate
FROM customers
GROUP BY segment
""", conn)

print(seg)


# KPI summary
kpi = pd.read_sql("""
SELECT ROUND(SUM(CASE WHEN status='completed' THEN total ELSE 0 END),0) as total_rev,
COUNT(DISTINCT customer_id) as customers
FROM orders
""", conn)

print(kpi)


# Funnel
funnel = pd.read_sql("""
SELECT event_type,
COUNT(DISTINCT customer_id) as users
FROM events
WHERE event_type IN ('page_view','product_view','add_to_cart','checkout_start','checkout_complete')
GROUP BY event_type
""", conn)

print(funnel)


# Category revenue
cat = pd.read_sql("""
SELECT p.category,
ROUND(SUM(oi.line_total),0) as revenue
FROM order_items oi
JOIN products p ON oi.product_id=p.product_id
JOIN orders o ON oi.order_id=o.order_id
WHERE o.status='completed'
GROUP BY p.category
ORDER BY revenue DESC
""", conn)

print(cat)

conn.close()