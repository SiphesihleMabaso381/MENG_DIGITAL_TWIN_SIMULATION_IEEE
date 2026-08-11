import pandas as pd

from src.load_profiles import CustomerType
from src.ntl_injection import NTLInjectionEngine
from src.simulation_engine import HybridGridDigitalTwin, SimulationConfig


class DummyLoadManager:
    def __init__(self):
        self.node_profiles = {"node1": {"customer_type": CustomerType.RESIDENTIAL}}

    def get_loads_at_time(self, day_of_year, hour):
        return {"node1": (5.0, 2.0)}


def test_operational_scenarios_include_recovery_sequences():
    engine = NTLInjectionEngine(DummyLoadManager())
    events = engine.generate_realistic_operational_scenarios(
        sim_duration_days=7,
        realism_profile="utility",
        affected_nodes=["node1"],
    )

    assert any(event["event_type"] == "restoration" for event in events)
    assert any("recovery" in event["description"].lower() for event in events)


def test_engine_builds_labeling_ready_output():
    config = SimulationConfig()
    engine = HybridGridDigitalTwin(config)
    engine.simulation_results = [
        {
            "day": 1,
            "hour": 0.0,
            "timestep": 0,
            "convergence": True,
            "source_p_kw": 10.0,
            "metered_total_kw": 8.0,
            "actual_total_kw": 9.0,
            "meter_readings": pd.DataFrame(
                [
                    {
                        "meter_id": "M1",
                        "node_name": "node1",
                        "measured_p_kw": 7.0,
                        "actual_p_kw": 9.0,
                        "meter_type": "smart",
                        "communication_loss": False,
                        "measurement_error_factor": 1.0,
                        "ntl_loss_kw": 1.0,
                        "ntl_type": "meter_tampering",
                    }
                ]
            ),
            "ntl_data": {
                "node1": {
                    "actual_power": (9.0, 0.0),
                    "metered_power": (7.0, 0.0),
                    "ntl_loss": (2.0, 0.0),
                    "ntl_type": "meter_tampering",
                }
            },
            "calibration_summary": {"gap_pct": 10.0, "stress_factor": 1.1},
        }
    ]

    results_df = engine._compile_results_dataframe()
    labeling_df = engine._build_labeling_ready_dataframe(results_df)

    assert {"scenario_label", "confidence_score", "reason_code"}.issubset(labeling_df.columns)
    assert not labeling_df.empty
