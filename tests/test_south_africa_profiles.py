import unittest

from src.hybrid_metering import HybridMeteringSystem
from src.load_profiles import (
    CustomerType,
    HybridGridLoadManager,
    LoadProfileGenerator,
    WeatherProfile,
    get_recommended_customer_types,
)
from src.ntl_injection import NTLInjectionEngine, NTLType


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


if __name__ == "__main__":
    unittest.main()
