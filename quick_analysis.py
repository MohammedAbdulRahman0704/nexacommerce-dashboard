import sqlite3
import pandas as pd
import json

conn = sqlite3.connect(r"D:/Python Projects/Project - 1/data/nexacommerce.db")

# Revenue monthly with MoM
rev = pd.read_sql("""
SELECT substr(order_date,1,7) as month,
ROUND(SUM(CASE WHEN status='completed' THEN total ELSE 0 END),0) as revenue,
COUNT(DISTINCT customer_id) as buyers,
COUNT(order_id) as orders
FROM orders
GROUP BY month
ORDER BY month
""", conn)

rev['mom'] = rev['revenue'].pct_change().mul(100).round(1)
print(json.dumps(rev.fillna(0).to_dict(orient='records')[:5], indent=2))


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

pivot = cohort.pivot_table(index='cm', columns='p', values='pct', aggfunc='first')
pivot = pivot.reset_index()

print("Cohort pivot shape:", pivot.shape)
print(pivot.head(2).to_string())

conn.close()