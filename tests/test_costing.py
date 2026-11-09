import pytest

from backend.costing import calculate_part


def test_sample_process_component_and_complete_cost():
    results = calculate_part(
        {"gross_weight_kg": 0.61, "cycle_time_min": 3.2, "scrap_pct": 0,
         "margin_pct": 0, "overhead_per_part": 0, "freight_per_part": 0, "packing_per_part": 0},
        {"amount": 100}, {"amount": 850}, [1000, 180000],
    )
    assert results[0]["processing"] == 45.33
    assert results[0]["unit_cost"] == 106.33
    assert results[-1]["annual_value"] == 19_140_000.00


@pytest.mark.parametrize(
    "part,volumes",
    [
        ({"gross_weight_kg": 0, "cycle_time_min": 1, "scrap_pct": 0, "margin_pct": 0}, [1, 2]),
        ({"gross_weight_kg": 1, "cycle_time_min": 1, "scrap_pct": 100, "margin_pct": 0}, [1, 2]),
        ({"gross_weight_kg": 1, "cycle_time_min": 1, "scrap_pct": 0, "margin_pct": 100}, [1, 2]),
    ],
)
def test_invalid_boundaries_fail(part, volumes):
    with pytest.raises(ValueError):
        calculate_part(part, {"amount": 10}, {"amount": 10}, volumes)


def test_invalid_volume_fails():
    part = {"gross_weight_kg": 1, "cycle_time_min": 1, "scrap_pct": 0, "margin_pct": 0}
    with pytest.raises(ValueError):
        calculate_part(part, {"amount": 10}, {"amount": 10}, [1, 0])


def test_multiple_routing_operations_sum_process_cost():
    part = {"gross_weight_kg": 1, "cycle_time_min": 3.2, "scrap_pct": 0, "margin_pct": 0}
    results = calculate_part(part, {"amount": 0}, {"amount": 850}, [1000], route_rates=[
        {"cycle_time_min": 3.2, "amount": 850},
        {"cycle_time_min": 1.5, "amount": 950},
    ])
    assert results[0]["processing"] == 69.08
