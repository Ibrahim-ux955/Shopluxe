import json

with open('data.json', 'r') as f:
    products = json.load(f)

for p in products:
    if 'reviews' not in p:
        p['reviews'] = []

with open('data.json', 'w') as f:
    json.dump(products, f, indent=4)

print("✅ All products updated with 'reviews' field.")
