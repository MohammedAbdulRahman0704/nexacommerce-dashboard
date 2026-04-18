"""
NexaCommerce Analytics — Phase 1
Data Generation & Cleaning Pipeline
=====================================
Generates realistic synthetic e-commerce data:
  - customers    : 10,000 records
  - orders       : ~50,000 records
  - order_items  : ~120,000 records
  - products     : 200 records
  - events       : ~200,000 behaviour events
Then cleans, engineers features, and exports to CSV + SQLite.
"""

import pandas as pd
import numpy as np
import sqlite3
import os
import random
from datetime import datetime, timedelta
from faker import Faker

fake = Faker()
Faker.seed(42)
np.random.seed(42)
random.seed(42)

OUTPUT_DIR = "D:\Python Projects\Project - 1\data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

START_DATE = datetime(2022, 1, 1)
END_DATE   = datetime(2024, 3, 31)
DATE_RANGE = (END_DATE - START_DATE).days

print("=" * 55)
print("  NexaCommerce — Phase 1: Data Generation & Cleaning")
print("=" * 55)


# ── 1. PRODUCTS ──────────────────────────────────────────────
print("\n[1/6] Generating products...")

CATEGORIES = {
    "Smartphones":    (299,  1199, 0.22),
    "Laptops":        (499,  2499, 0.15),
    "Headphones":     (49,    399, 0.18),
    "Tablets":        (199,   999, 0.10),
    "Smartwatches":   (99,    599, 0.12),
    "Cameras":        (149,  1599, 0.07),
    "Gaming":         (29,    699, 0.10),
    "Accessories":    (5,      79, 0.06),
}

products = []
product_id = 1
for category, (price_min, price_max, _) in CATEGORIES.items():
    n_products = random.randint(20, 35)
    for _ in range(n_products):
        cost = round(random.uniform(price_min * 0.35, price_min * 0.65), 2)
        price = round(random.uniform(price_min, price_max), 2)
        products.append({
            "product_id":   product_id,
            "name":         f"{fake.company().split()[0]} {category[:-1] if category.endswith('s') else category} {fake.bothify('??-###').upper()}",
            "category":     category,
            "price":        price,
            "cost":         cost,
            "margin_pct":   round((price - cost) / price * 100, 1),
            "is_active":    random.choices([True, False], weights=[0.92, 0.08])[0],
            "launch_date":  fake.date_between(start_date="-3y", end_date="-6m"),
        })
        product_id += 1

df_products = pd.DataFrame(products)
print(f"   ✓ {len(df_products)} products across {df_products['category'].nunique()} categories")


# ── 2. CUSTOMERS ─────────────────────────────────────────────
print("\n[2/6] Generating customers...")

ACQUISITION_CHANNELS = ["organic_search", "paid_search", "social_media",
                         "email_campaign", "referral", "direct", "influencer"]
CHANNEL_WEIGHTS      = [0.28, 0.22, 0.18, 0.12, 0.10, 0.07, 0.03]

SEGMENTS = {
    "budget":    (0.30, 0.5, 1.5),   # (share, order_freq_mult, ltv_mult)
    "regular":   (0.45, 1.0, 1.0),
    "premium":   (0.20, 1.8, 2.5),
    "vip":       (0.05, 3.5, 6.0),
}
seg_names   = list(SEGMENTS.keys())
seg_weights = [v[0] for v in SEGMENTS.values()]

customers = []
for cid in range(1, 10_001):
    signup_offset = random.randint(0, DATE_RANGE - 30)
    signup_dt     = START_DATE + timedelta(days=signup_offset)
    segment       = random.choices(seg_names, weights=seg_weights)[0]
    
    # Intentionally introduce some dirty data (to be cleaned later)
    email = fake.email()
    if random.random() < 0.02:   email = None          # 2% missing
    if email and random.random() < 0.015:  email = email.upper() # wrong case

    customers.append({
        "customer_id":      cid,
        "email":            email,
        "first_name":       fake.first_name(),
        "last_name":        fake.last_name(),
        "country":          random.choices(
                                ["India", "USA", "UK", "Germany", "Australia", "Canada", "Singapore"],
                                weights=[0.35, 0.25, 0.12, 0.08, 0.07, 0.07, 0.06])[0],
        "city":             fake.city(),
        "signup_date":      signup_dt.date(),
        "acquisition_channel": random.choices(ACQUISITION_CHANNELS, weights=CHANNEL_WEIGHTS)[0],
        "segment":          segment,
        "age":              random.randint(18, 65) if random.random() > 0.05 else None,  # 5% missing
        "is_subscribed":    random.choices([True, False], weights=[0.65, 0.35])[0],
    })

df_customers = pd.DataFrame(customers)
print(f"   ✓ {len(df_customers):,} customers | dirty: {df_customers['email'].isna().sum()} missing emails, {df_customers['age'].isna().sum()} missing ages")


# ── 3. ORDERS ────────────────────────────────────────────────
print("\n[3/6] Generating orders (~50k)...")

ORDER_STATUSES = ["completed", "completed", "completed", "completed",
                  "refunded", "cancelled", "processing"]

orders       = []
order_items  = []
order_id     = 1
item_id      = 1

cat_list    = list(CATEGORIES.keys())
cat_weights = [v[2] for v in CATEGORIES.values()]

for _, cust in df_customers.iterrows():
    seg_info    = SEGMENTS[cust["segment"]]
    freq_mult   = seg_info[1]
    signup_days = (END_DATE.date() - cust["signup_date"]).days
    
    # Base number of orders for this customer
    avg_orders = max(1, int(np.random.exponential(3.5 * freq_mult)))
    # Introduce churn: ~28% of customers stop ordering after 90 days
    churned = random.random() < 0.28
    if churned:
        active_days = random.randint(1, 90)
    else:
        active_days = signup_days

    for _ in range(avg_orders):
        days_after_signup = random.randint(0, min(active_days, signup_days))
        order_date = cust["signup_date"] + timedelta(days=days_after_signup)
        if order_date > END_DATE.date():
            continue
        
        status    = random.choices(ORDER_STATUSES)[0]
        n_items   = random.choices([1,2,3,4,5], weights=[40,30,18,8,4])[0]
        discount  = round(random.choices([0,0,0,0.05,0.10,0.15,0.20],
                                          weights=[50,20,10,8,6,4,2])[0], 2)
        
        # Pick category then product
        chosen_cat  = random.choices(cat_list, weights=cat_weights)[0]
        cat_prods   = df_products[df_products["category"] == chosen_cat]
        
        subtotal    = 0
        order_items_batch = []
        for _ in range(n_items):
            prod        = cat_prods.sample(1).iloc[0]
            qty         = random.choices([1,2,3], weights=[70,22,8])[0]
            unit_price  = prod["price"] * (1 - discount)
            line_total  = round(unit_price * qty, 2)
            subtotal   += line_total
            order_items_batch.append({
                "item_id":    item_id,
                "order_id":   order_id,
                "product_id": prod["product_id"],
                "quantity":   qty,
                "unit_price": round(unit_price, 2),
                "line_total": line_total,
            })
            item_id += 1

        shipping = round(random.uniform(0, 12), 2) if subtotal < 100 else 0
        tax      = round(subtotal * 0.08, 2)
        total    = round(subtotal + shipping + tax, 2)

        orders.append({
            "order_id":        order_id,
            "customer_id":     cust["customer_id"],
            "order_date":      order_date,
            "status":          status,
            "subtotal":        round(subtotal, 2),
            "discount_pct":    discount * 100,
            "shipping":        shipping,
            "tax":             tax,
            "total":           total,
            "payment_method":  random.choices(["card","upi","netbanking","wallet","cod"],
                                               weights=[45,25,15,10,5])[0],
        })
        order_items.extend(order_items_batch)
        order_id += 1

df_orders      = pd.DataFrame(orders)
df_order_items = pd.DataFrame(order_items)
print(f"   ✓ {len(df_orders):,} orders | {len(df_order_items):,} order items")


# ── 4. EVENTS ────────────────────────────────────────────────
print("\n[4/6] Generating behaviour events (~200k)...")

EVENT_TYPES = ["page_view","product_view","add_to_cart","remove_from_cart",
               "checkout_start","checkout_complete","search","wishlist_add"]
EVENT_W     = [30, 25, 15, 5, 8, 7, 7, 3]

events = []
for _, cust in df_customers.sample(frac=0.80).iterrows():   # 80% of customers have events
    n_events = random.randint(3, 60)
    signup_days = (END_DATE.date() - cust["signup_date"]).days
    for _ in range(n_events):
        evt_date = cust["signup_date"] + timedelta(days=random.randint(0, signup_days))
        events.append({
            "event_id":    len(events) + 1,
            "customer_id": cust["customer_id"],
            "event_type":  random.choices(EVENT_TYPES, weights=EVENT_W)[0],
            "event_date":  evt_date,
            "session_id":  fake.uuid4()[:8],
            "product_id":  random.choice(df_products["product_id"].tolist()) if random.random() > 0.4 else None,
            "device":      random.choices(["mobile","desktop","tablet"], weights=[55,38,7])[0],
        })

df_events = pd.DataFrame(events)
print(f"   ✓ {len(df_events):,} events generated")


# ── 5. DATA CLEANING ─────────────────────────────────────────
print("\n[5/6] Cleaning data...")

## Customers
before = len(df_customers)
# Fix email casing
df_customers["email"] = df_customers["email"].str.lower()
# Fill missing emails with placeholder
df_customers["email"] = df_customers["email"].fillna("unknown@nexacommerce.com")
# Fill missing ages with median
median_age = int(df_customers["age"].median())
df_customers["age"] = df_customers["age"].fillna(median_age)
df_customers["age"] = df_customers["age"].astype(int)
# Remove duplicate emails (keep first)
df_customers.drop_duplicates(subset="email", keep="first", inplace=True)
after = len(df_customers)
print(f"   ✓ Customers: fixed {before - after} duplicate emails, filled nulls, normalised case")

## Orders
# Remove orders with total <= 0 (data error)
bad_orders = (df_orders["total"] <= 0).sum()
df_orders   = df_orders[df_orders["total"] > 0].copy()
# Ensure dates are datetime
df_orders["order_date"] = pd.to_datetime(df_orders["order_date"])
# Add month column for cohort analysis
df_orders["order_month"] = df_orders["order_date"].dt.to_period("M")
print(f"   ✓ Orders: removed {bad_orders} zero/negative rows, parsed dates, added order_month")

## Events
df_events["event_date"] = pd.to_datetime(df_events["event_date"])
df_events.drop_duplicates(inplace=True)
print(f"   ✓ Events: removed duplicates, parsed dates")


# ── 6. FEATURE ENGINEERING ───────────────────────────────────
print("\n[6/6] Engineering features...")

completed = df_orders[df_orders["status"] == "completed"].copy()

# Customer-level aggregates
cust_stats = completed.groupby("customer_id").agg(
    total_orders    = ("order_id", "count"),
    total_revenue   = ("total", "sum"),
    avg_order_value = ("total", "mean"),
    first_order     = ("order_date", "min"),
    last_order      = ("order_date", "max"),
).reset_index()

cust_stats["ltv"]         = cust_stats["total_revenue"].round(2)
cust_stats["avg_order_value"] = cust_stats["avg_order_value"].round(2)
cust_stats["days_active"] = (cust_stats["last_order"] - cust_stats["first_order"]).dt.days
cust_stats["order_freq_days"] = np.where(
    cust_stats["total_orders"] > 1,
    (cust_stats["days_active"] / (cust_stats["total_orders"] - 1)).round(1),
    np.nan
)

# Churn flag: no order in last 90 days
cutoff = pd.Timestamp(END_DATE)
cust_stats["churned"] = (cutoff - cust_stats["last_order"]).dt.days > 90

# Signup cohort (month of first order)
cust_stats["cohort_month"] = cust_stats["first_order"].dt.to_period("M")

# Merge back to customers
df_customers = df_customers.merge(cust_stats, on="customer_id", how="left")
df_customers["total_orders"]   = df_customers["total_orders"].fillna(0).astype(int)
df_customers["total_revenue"]  = df_customers["total_revenue"].fillna(0)
df_customers["churned"]        = df_customers["churned"].fillna(True)  # never ordered = churned

churn_rate = df_customers["churned"].mean() * 100
print(f"   ✓ Feature engineering complete")
print(f"   ✓ Overall churn rate: {churn_rate:.1f}%")
print(f"   ✓ Avg LTV (active): ${cust_stats[~cust_stats['churned']]['ltv'].mean():.2f}")


# ── EXPORT ───────────────────────────────────────────────────
print("\n── Exporting to CSV and SQLite ──")

df_customers.to_csv(f"{OUTPUT_DIR}/customers.csv", index=False)
df_orders.to_csv(f"{OUTPUT_DIR}/orders.csv", index=False)
df_order_items.to_csv(f"{OUTPUT_DIR}/order_items.csv", index=False)
df_products.to_csv(f"{OUTPUT_DIR}/products.csv", index=False)
df_events.to_csv(f"{OUTPUT_DIR}/events.csv", index=False)


# Convert Period columns to string for SQLite compatibility
df_orders['order_month'] = df_orders['order_month'].astype(str)
if 'cohort_month' in df_customers.columns:
    df_customers['cohort_month'] = df_customers['cohort_month'].astype(str)
# SQLite
conn = sqlite3.connect(f"{OUTPUT_DIR}/nexacommerce.db")
df_customers.to_sql("customers", conn, if_exists="replace", index=False)
df_orders.to_sql("orders", conn, if_exists="replace", index=False)
df_order_items.to_sql("order_items", conn, if_exists="replace", index=False)
df_products.to_sql("products", conn, if_exists="replace", index=False)
df_events.to_sql("events", conn, if_exists="replace", index=False)
conn.close()

print(f"   ✓ CSVs saved to {OUTPUT_DIR}/")
print(f"   ✓ SQLite DB saved to {OUTPUT_DIR}/nexacommerce.db")

# ── SUMMARY ──────────────────────────────────────────────────
print("\n" + "=" * 55)
print("  PHASE 1 COMPLETE — Dataset Summary")
print("=" * 55)
print(f"  customers    : {len(df_customers):>8,} rows")
print(f"  orders       : {len(df_orders):>8,} rows")
print(f"  order_items  : {len(df_order_items):>8,} rows")
print(f"  products     : {len(df_products):>8,} rows")
print(f"  events       : {len(df_events):>8,} rows")
print(f"  churn rate   : {churn_rate:>7.1f}%")
print(f"  date range   : 2022-01-01 → 2024-03-31")
print("=" * 55)
print("\n  Next → Phase 2: SQL schema & KPI queries")