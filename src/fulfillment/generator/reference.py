"""Reference data for the simulation: Indian states, fulfilment hubs, couriers, catalogue.

`order_weight` approximates each state's share of e-commerce orders. `remoteness`
(1 = well connected, 3 = hard to reach) drives last-mile transit time. The same state
list is shipped to dbt as a seed (dbt/seeds/ref_states.csv), so the generator and the
warehouse agree on geography.
"""

from __future__ import annotations

# name, code, region, remoteness, order_weight
STATES: list[tuple[str, str, str, int, float]] = [
    ("Maharashtra", "MH", "West", 1, 13.0),
    ("Karnataka", "KA", "South", 1, 9.5),
    ("Delhi", "DL", "North", 1, 9.0),
    ("Tamil Nadu", "TN", "South", 1, 7.5),
    ("Uttar Pradesh", "UP", "North", 2, 8.5),
    ("Telangana", "TS", "South", 1, 5.5),
    ("Gujarat", "GJ", "West", 1, 5.5),
    ("West Bengal", "WB", "East", 2, 5.5),
    ("Haryana", "HR", "North", 1, 4.0),
    ("Rajasthan", "RJ", "North", 2, 3.8),
    ("Kerala", "KL", "South", 2, 3.5),
    ("Andhra Pradesh", "AP", "South", 2, 3.2),
    ("Madhya Pradesh", "MP", "Central", 2, 3.2),
    ("Punjab", "PB", "North", 2, 2.4),
    ("Bihar", "BR", "East", 3, 2.6),
    ("Odisha", "OD", "East", 2, 1.8),
    ("Assam", "AS", "North-East", 3, 1.4),
    ("Jharkhand", "JH", "East", 3, 1.2),
    ("Chhattisgarh", "CG", "Central", 2, 1.0),
    ("Uttarakhand", "UK", "North", 2, 0.9),
    ("Jammu and Kashmir", "JK", "North", 3, 0.7),
    ("Himachal Pradesh", "HP", "North", 3, 0.6),
    ("Goa", "GA", "West", 1, 0.6),
    ("Chandigarh", "CH", "North", 1, 0.5),
    ("Puducherry", "PY", "South", 2, 0.25),
    ("Tripura", "TR", "North-East", 3, 0.2),
    ("Meghalaya", "ML", "North-East", 3, 0.15),
    ("Manipur", "MN", "North-East", 3, 0.12),
    ("Nagaland", "NL", "North-East", 3, 0.08),
    ("Arunachal Pradesh", "AR", "North-East", 3, 0.07),
    ("Mizoram", "MZ", "North-East", 3, 0.06),
    ("Sikkim", "SK", "North-East", 3, 0.06),
    ("Ladakh", "LA", "North", 3, 0.03),
]

# Messy spellings seen in the "source system" (customer-entered addresses).
STATE_ALIASES: dict[str, list[str]] = {
    "Tamil Nadu": ["Tamilnadu", "TAMIL NADU", "TN"],
    "Delhi": ["New Delhi", "NCT of Delhi", "DELHI"],
    "Maharashtra": ["Maharastra", "MH", "maharashtra"],
    "Karnataka": ["Karnatka", "KA", "Bengaluru Karnataka"],
    "Uttar Pradesh": ["UP", "Uttarpradesh", "U.P."],
    "West Bengal": ["WestBengal", "W.B.", "west bengal"],
    "Telangana": ["Telengana", "TS"],
    "Odisha": ["Orissa"],
    "Puducherry": ["Pondicherry"],
    "Jammu and Kashmir": ["Jammu & Kashmir", "J&K"],
    "Gujarat": ["Gujrat"],
    "Chhattisgarh": ["Chattisgarh"],
}

# Fulfilment hubs: (hub_id, state, region)
HUBS: list[tuple[str, str, str]] = [
    ("HUB-BHI", "Maharashtra", "West"),
    ("HUB-BLR", "Karnataka", "South"),
    ("HUB-GGN", "Haryana", "North"),
    ("HUB-KOL", "West Bengal", "East"),
    ("HUB-HYD", "Telangana", "South"),
    ("HUB-AMD", "Gujarat", "West"),
    ("HUB-LKO", "Uttar Pradesh", "North"),
]

# Transit "zone distance" between regions (0 = same region).
REGIONS = ["North", "South", "East", "West", "Central", "North-East"]
_REGION_XY = {
    "North": (0, 2),
    "Central": (0, 1),
    "West": (-1, 0.5),
    "South": (0, -1),
    "East": (1.2, 1),
    "North-East": (2.5, 1.6),
}


def region_distance(a: str, b: str) -> float:
    (x1, y1), (x2, y2) = _REGION_XY[a], _REGION_XY[b]
    return ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5


# Fictional courier partners: (name, speed_factor, reliability)
COURIERS: list[tuple[str, float, float]] = [
    ("SwiftShip", 0.85, 0.97),
    ("BharatExpress", 1.00, 0.95),
    ("PinPoint Logistics", 0.95, 0.96),
    ("TrailBlaze Couriers", 1.15, 0.92),
    ("ParcelPath", 1.05, 0.94),
]

# category, share, min_price_inr, max_price_inr, weight_kg
CATEGORIES: list[tuple[str, float, int, int, float]] = [
    ("Men's Apparel", 0.22, 399, 3499, 0.5),
    ("Women's Apparel", 0.26, 449, 4999, 0.5),
    ("Ethnic Wear", 0.12, 799, 8999, 0.9),
    ("Footwear", 0.14, 599, 6999, 1.1),
    ("Accessories", 0.10, 199, 2999, 0.3),
    ("Kids", 0.07, 299, 1999, 0.4),
    ("Beauty", 0.05, 149, 1999, 0.3),
    ("Home", 0.04, 299, 4999, 1.8),
]

PAYMENT_METHODS: list[tuple[str, float]] = [
    ("UPI", 0.42),
    ("COD", 0.27),
    ("Credit Card", 0.13),
    ("Debit Card", 0.09),
    ("Wallet", 0.05),
    ("Net Banking", 0.04),
]

# Sale events that spike volume and congest logistics: (name, month, start_day, days, uplift)
SALE_EVENTS: list[tuple[str, int, int, int, float]] = [
    ("End of Season Sale - Winter", 1, 5, 10, 1.8),
    ("End of Season Sale - Summer", 7, 1, 12, 1.9),
    ("Festive Sale", 10, 3, 9, 3.2),
    ("Diwali Week", 10, 28, 7, 2.4),
    ("Black Friday", 11, 24, 4, 1.7),
]
