from decimal import Decimal, ROUND_HALF_UP


def d(value):
    return Decimal(str(value))


def money(value):
    return d(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_part(part: dict, material_rate: dict, machine_rate: dict, volumes: list[int],
                   route_rates: list[dict] | None = None) -> list[dict]:
    weight = d(part["gross_weight_kg"])
    scrap = d(part.get("scrap_pct", 0)) / 100
    margin = d(part.get("margin_pct", 0)) / 100
    cycle = d(part["cycle_time_min"])
    routes = route_rates or [{"cycle_time_min": cycle, "amount": machine_rate["amount"]}]
    if weight <= 0 or cycle < 0 or not routes or not 0 <= scrap < 1 or not 0 <= margin < 1:
        raise ValueError("Check weight, cycle time, scrap, and margin values.")
    if d(material_rate["amount"]) < 0 or any(d(route["amount"]) < 0 or d(route["cycle_time_min"]) < 0 for route in routes):
        raise ValueError("Rates cannot be negative.")
    material = weight * d(material_rate["amount"]) / (1 - scrap)
    process = sum(d(route["cycle_time_min"]) / 60 * d(route["amount"]) for route in routes)
    fixed = sum(d(part.get(k, 0)) for k in ("overhead_per_part", "freight_per_part", "packing_per_part"))
    cost = material + process + fixed
    results = []
    for volume in volumes:
        if int(volume) != volume or int(volume) <= 0:
            raise ValueError("Volumes must be positive whole numbers.")
        price = cost * (1 + margin)
        results.append({
            "volume": int(volume),
            "material": float(money(material)),
            "processing": float(money(process)),
            "overhead": float(money(part.get("overhead_per_part", 0))),
            "freight": float(money(part.get("freight_per_part", 0))),
            "packing": float(money(part.get("packing_per_part", 0))),
            "unit_cost": float(money(cost)),
            "unit_price": float(money(price)),
            "annual_value": float(money(price * int(volume))),
        })
    return results
