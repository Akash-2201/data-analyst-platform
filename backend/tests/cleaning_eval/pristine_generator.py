"""
Pristine synthetic dataset generator.
100 clean rows, every column type, with tricky-but-valid values:
- McDonald, O'Brien, De Silva, Mary-Jane (valid mixed-case / apostrophe / hyphen names)
- Valid emails with plus signs (user+tag@gmail.com, test.name@sub.domain.org)
- Normalized 10-digit Indian phones (text: "9876543210", "6123456789")
- Canonical cities (Bengaluru, Chennai, Delhi, Hyderabad, Mumbai, Pune)
- Canonical categories (Clothing, Electronics, Furniture, Groceries)
- Clean ISO dates (2026-01-15, 2026-05-20)
- Valid ages (21, 45, 80) as nullable Int64
- Valid positive amounts (1200.50, 450.00)
- Valid quantities (1, 5, 12)
- Valid coordinates (lat 12.9716, lon 77.5946, etc.)
The cleaning pipeline must change ZERO cells and add ZERO flags on this dataset.
"""
import pandas as pd


def generate_pristine_dataset(n_rows: int = 100) -> pd.DataFrame:
    names = [
        "McDonald", "O'Brien", "De Silva", "Mary-Jane", "Jean-Luc",
        "Aarav Patel", "Diya Sharma", "Aditya Rao", "Pooja Verma", "Vikram Singh"
    ]
    emails = [
        "user+tag@gmail.com", "test.name@sub.domain.org", "first.last@company.com",
        "alex.o'connor@domain.co.in", "customer+support@shop.net"
    ]
    phones = [
        "9876543210", "9123456789", "8987654321", "7890123456", "6789012345"
    ]
    cities = ["Bengaluru", "Chennai", "Delhi", "Hyderabad", "Mumbai", "Pune"]
    categories = ["Clothing", "Electronics", "Furniture", "Groceries"]
    dates = ["2026-01-15", "2026-02-20", "2026-03-10", "2026-04-05", "2026-05-12"]

    rows = []
    for i in range(n_rows):
        rid = f"REC-{2000 + i}"
        name = names[i % len(names)]
        email = f"user{i}+{emails[i % len(emails)]}"
        phone = phones[i % len(phones)]
        city = cities[i % len(cities)]
        category = categories[i % len(categories)]
        date = dates[i % len(dates)]
        age = 20 + (i % 60)
        amount = round(100.0 + (i * 15.75) % 5000, 2)
        quantity = 1 + (i % 10)
        lat = round(12.0 + (i * 0.1) % 15.0, 6)
        lon = round(75.0 + (i * 0.1) % 15.0, 6)

        rows.append({
            "Record_ID": rid,
            "Customer_Name": name,
            "Age": age,
            "Email": email,
            "Phone": phone,
            "City": city,
            "Category": category,
            "Amount": amount,
            "Quantity": quantity,
            "Purchase_Date": date,
            "Latitude": lat,
            "Longitude": lon,
        })

    df = pd.DataFrame(rows)
    # Ensure types
    df["Age"] = df["Age"].astype("Int64")
    df["Quantity"] = df["Quantity"].astype("Int64")
    df["Phone"] = df["Phone"].astype(str)
    return df


if __name__ == "__main__":
    df = generate_pristine_dataset(100)
    print(f"Generated pristine dataset shape: {df.shape}")
    print(df.head(5))
