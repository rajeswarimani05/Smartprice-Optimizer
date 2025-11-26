# train_model.py
import random
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
import joblib

RANDOM_SEED = 42
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

products = [
    {"name":"LED TV","base_price":5089.66,"competitor":5200},
    {"name":"Wireless Headphones","base_price":1948.91,"competitor":1950},
    {"name":"Coffee Maker","base_price":3013.08,"competitor":3000},
    {"name":"Bluetooth Speaker","base_price":2405.17,"competitor":2450},
    {"name":"Smartphone","base_price":15000,"competitor":14900},
    {"name":"Laptop","base_price":42000,"competitor":41500},
    {"name":"Smartwatch","base_price":5000,"competitor":4900},
    {"name":"Microwave Oven","base_price":7000,"competitor":6900},
    {"name":"Refrigerator","base_price":22000,"competitor":21800},
    {"name":"Air Conditioner","base_price":28000,"competitor":28500}
]

rows = []
for _ in range(5000):
    p = random.choice(products)
    base = p["base_price"]
    comp = p["competitor"] * (1 + np.random.normal(0, 0.02))
    demand = max(1, int(np.random.beta(2, 5) * 100))
    stock = max(0, int(np.random.poisson(20)))
    month = random.randint(1, 12)
    weekday = random.randint(0, 6)

    price = base
    price *= (1 + (demand - 50) / 1000.0)           # demand effect
    price *= (1 - max(0, (stock - 30)) / 1000.0)    # high stock -> small decrease
    if month in (10,11,12):
        price *= 1.04
    price = 0.6 * price + 0.4 * comp
    price *= (1 + np.random.normal(0, 0.01))

    rows.append({
        "base_price": base,
        "competitor_price": round(comp,2),
        "demand": demand,
        "stock": stock,
        "month": month,
        "weekday": weekday,
        "final_price": round(price, 2)
    })

df = pd.DataFrame(rows)
X = df[["base_price","competitor_price","demand","stock","month","weekday"]]
y = df["final_price"]

X_train, X_test, y_train, y_test = train_test_split(X,y,test_size=0.2, random_state=RANDOM_SEED)

model = RandomForestRegressor(n_estimators=200, random_state=RANDOM_SEED, n_jobs=-1)
model.fit(X_train, y_train)

print("Train R^2:", model.score(X_train, y_train))
print("Test  R^2:", model.score(X_test, y_test))

joblib.dump(model, "model.pkl")
print("Saved model.pkl")
