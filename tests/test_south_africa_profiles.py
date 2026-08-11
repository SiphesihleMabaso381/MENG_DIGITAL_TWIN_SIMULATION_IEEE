import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.hybrid_metering import HybridMeteringSystem
from src.load_profiles import (
    CustomerType,
    HybridGridLoadManager,
    LoadProfileGenerator,
    WeatherProfile,
    get_recommended_customer_types,
)
from src.ntl_injection import NTLInjectionEngine, NTLType
from src.simulation_engine import HybridGridDigitalTwin, SimulationConfig


class SouthAfricaProfileTests(unittest.TestCase):
    def test_recommended_customer_types_stay_simple(self):
        recommended = get_recommended_customer_types()

        self.assertEqual(
            recommended,
            [
                CustomerType.RESIDENTIAL,
                CustomerType.COMMERCIAL,
                CustomerType.INDUSTRIAL,
                CustomerType.AGRICULTURAL,
                CustomerType.PUBLIC_MUNICIPAL,
                CustomerType.INSTITUTIONAL,
                CustomerType.BULK,
            ],
        )

    def test_hot_weather_profiles_shift_peak_towards_evening(self):
        generator = LoadProfileGenerator(
            CustomerType.RESIDENTIAL,
            annual_consumption_kwh=4000,
            weather_profile=WeatherProfile.HOT,
        )
        profile = generator.get_hourly_profile(day_of_year=1)

        self.assertGreater(profile[18], profile[2])

    def test_meter_data_quality_can_mark_missing_readings(self):
        metering = HybridMeteringSystem(["node1"])
        metering.deploy_meters(["node1"], meter_profile={"smart_accuracy_class": 0.5})
        metering.data_quality_profile = {"missing_reading_probability": 1.0}

        result = metering.record_all_measurements({"node1": (10.0, 2.0)}, time_interval_minutes=15)

        self.assertTrue(result["missing_reading"].iloc[0])

    def test_operational_events_are_tracked_separately_from_ntl(self):
        load_manager = HybridGridLoadManager()
        load_manager.add_load_node("node1", CustomerType.RESIDENTIAL, 4000)

        engine = NTLInjectionEngine(load_manager)
        engine.schedule_ntl_event("node1", NTLType.PARTIAL_METER_BYPASS, 1, 12.0, 2.0, 0.3, "theft")
        engine.schedule_operational_event("node1", "load_shedding", 1, 12.0, 2.0, 0.8, "outage")

        result = engine.get_node_power_with_ntl("node1", 1, 12.5)

        self.assertEqual(result["ntl_type"], NTLType.PARTIAL_METER_BYPASS)
        self.assertEqual(result["operational_event_type"], "load_shedding")

    def test_feeder_realism_reduces_load_under_high_stress(self):
        config = SimulationConfig()
        twin = HybridGridDigitalTwin(config)
        twin._feeder_baseline_kw = 100.0

        metered_loads = {"node1": (80.0, 10.0), "node2": (90.0, 12.0)}
        adjusted = twin._apply_feeder_realism(metered_loads, day=1, hour=19.0)

        self.assertLess(adjusted["node1"][0], 80.0)
        self.assertLess(adjusted["node2"][0], 90.0)

    def test_export_results_writes_realism_report(self):
        config = SimulationConfig()
        twin = HybridGridDigitalTwin(config)
        twin.simulation_results = [{
            'day': 1,
            'hour': 0.0,
            'timestep': 0,
            'convergence': True,
            'source_p_kw': 10.0,
            'metered_total_kw': 8.0,
            'actual_total_kw': 10.0,
            'meter_readings': pd.DataFrame([
                {'node_name': 'node1', 'meter_type': 'smart', 'measured_p_kw': 4.0, 'actual_p_kw': 5.0, 'ntl_loss_kw': 1.0}
            ]),
            'ntl_data': {},
            'calibration_summary': {'gap_pct': 2.0, 'stress_factor': 1.1},
        }]
        twin.ntl_engine = type('DummyEngine', (), {'export_event_schedule': lambda self: pd.DataFrame()})()
        twin.metering_system = type('DummyMetering', (), {'get_metering_statistics': lambda self: {'total_meters': 1, 'smart_meters': 1, 'legacy_meters': 0}})()

        with tempfile.TemporaryDirectory() as tmpdir:
            twin.export_results(tmpdir)
            self.assertTrue(Path(tmpdir, 'realism_report.csv').exists())
            self.assertTrue(Path(tmpdir, 'simulation_results.csv').exists())


if __name__ == "__main__":
    unittest.main()
