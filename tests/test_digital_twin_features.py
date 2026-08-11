import numpy as np

from src.hybrid_metering import HybridMeteringSystem
from src.ntl_injection import NTLInjectionEngine


class DummyLoadManager:
    def __init__(self):
        self.node_profiles = {"node1": {"load": 1.0}}

    def get_loads_at_time(self, day_of_year, hour):
        return {"node1": (10.0, 2.0)}


def test_operational_scenarios_support_real_world_event_types():
    np.random.seed(7)
    load_manager = DummyLoadManager()
    engine = NTLInjectionEngine(load_manager)

    events = engine.generate_realistic_operational_scenarios(
        sim_duration_days=3,
        realism_profile="utility",
        affected_nodes=["node1"],
    )

    event_types = {event["event_type"] for event in events}
    assert {"planned_outage", "unplanned_fault", "switching_event", "restoration"}.issubset(event_types)


def test_meter_recordings_include_uncertainty_and_quality_flags():
    system = HybridMeteringSystem(["node1"])
    system.deploy_meters(["node1"], [], meter_profile={
        "smart_accuracy_class": 0.5,
        "smart_communication_reliability": 0.95,
        "smart_communication_reliability_std": 0.01,
    })
    system.set_data_quality_profile({
        "missing_reading_probability": 0.1,
        "stale_reading_probability": 0.1,
        "noise_scale": 0.02,
    })

    df = system.record_all_measurements({"node1": (10.0, 2.0)}, time_interval_minutes=15)

    assert "measurement_uncertainty_pct" in df.columns
    assert "data_quality_flag" in df.columns
    assert df["measurement_uncertainty_pct"].notna().all()
