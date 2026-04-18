import sqlite3
import pandas as pd
import json

conn = sqlite3.connect(r"D:/Python Projects/Project - 1/data/nexacommerce.db")

# Revenue
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
rev_json = rev.fillna(0).to_dict(orient='records')

# Cohort
cohort_raw = pd.read_sql(""" 
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

cohort_list = []
for cm, grp in cohort_raw.groupby('cm'):
    row = {'cohort': cm, 'size': int(grp.iloc[0]['sz']), 'periods': {}}
    for _, r in grp.iterrows():
        row['periods'][int(r['p'])] = float(r['pct']) if pd.notna(r['pct']) else None
    cohort_list.append(row)

# Segments
seg = pd.read_sql("""
SELECT segment, COUNT(*) as n,
ROUND(AVG(total_revenue),0) as avg_ltv,
ROUND(SUM(churned)*100.0/COUNT(*),1) as churn_rate
FROM customers
GROUP BY segment
ORDER BY avg_ltv DESC
""", conn)

seg_json = seg.to_dict(orient='records')

# Funnel
funnel = pd.read_sql("""
SELECT event_type, COUNT(DISTINCT customer_id) as users
FROM events
WHERE event_type IN ('page_view','product_view','add_to_cart','checkout_start','checkout_complete')
GROUP BY event_type
""", conn)

order_map = {
    'page_view':0,'product_view':1,'add_to_cart':2,
    'checkout_start':3,'checkout_complete':4
}

funnel['order'] = funnel['event_type'].map(order_map)
funnel = funnel.sort_values('order')
funnel_json = funnel[['event_type','users']].to_dict(orient='records')

# Category revenue
cat = pd.read_sql("""
SELECT p.category, ROUND(SUM(oi.line_total),0) as revenue
FROM order_items oi
JOIN products p ON oi.product_id=p.product_id
JOIN orders o ON oi.order_id=o.order_id
WHERE o.status='completed'
GROUP BY p.category
ORDER BY revenue DESC
""", conn)

cat_json = cat.to_dict(orient='records')

# Churn by channel
churn_chan = pd.read_sql("""
SELECT acquisition_channel, COUNT(*) as total,
ROUND(SUM(churned)*100.0/COUNT(*),1) as churn_rate
FROM customers
GROUP BY acquisition_channel
ORDER BY churn_rate DESC
""", conn)

churn_chan_json = churn_chan.to_dict(orient='records')

# Top products
top_prods = pd.read_sql("""
SELECT p.name, p.category, ROUND(SUM(oi.line_total),0) as revenue
FROM order_items oi
JOIN products p ON oi.product_id=p.product_id
JOIN orders o ON oi.order_id=o.order_id
WHERE o.status='completed'
GROUP BY p.product_id
ORDER BY revenue DESC
LIMIT 8
""", conn)

top_prods_json = top_prods.to_dict(orient='records')

conn.close()

data = {
    'revenue': rev_json,
    'cohort': cohort_list,
    'segments': seg_json,
    'funnel': funnel_json,
    'categories': cat_json,
    'churn_by_channel': churn_chan_json,
    'top_products': top_prods_json
}

with open(r"D:/Python Projects/Project - 1/data/dashboard_data.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print("JSON generated successfully")