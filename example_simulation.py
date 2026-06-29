"""
Example Simulation Script
=========================
Demonstrates how to set up and run a complete hybrid grid digital twin simulation
with OpenDSS, load profiles, hybrid metering, and NTL injection.

Run this script to generate a realistic simulation dataset for NTL detection research.
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

# Import simulation modules
from src.opendsss_interface import OpenDSSInterface
from src.hybrid_metering import HybridMeteringSystem
from src.load_profiles import HybridGridLoadManager, CustomerType
from src.ntl_injection import NTLInjectionEngine, NTLType
from src.simulation_engine import HybridGridDigitalTwin, SimulationConfig


def example_ieee13_simulation():
    """
    Example: IEEE 13-bus feeder with hybrid metering and NTL scenarios.
    """
    
    print("\n" + "="*70)
    print("EXAMPLE 1: IEEE 13-Bus Feeder Digital Twin Simulation")
    print("="*70)
    
    # Step 1: Configure simulation
    config = SimulationConfig()
    config.feeder_name = "IEEE13"
    config.simulation_days = 7  # 1 week simulation
    config.time_step_minutes = 15
    config.smart_meter_penetration = 0.6  # 60% smart meters
    config.num_ntl_nodes = 2
    config.seed = 42
    
    print("\n[Step 1] Configuration:")
    print(f"  Feeder: {config.feeder_name}")
    print(f"  Duration: {config.simulation_days} days")
    print(f"  Time step: {config.time_step_minutes} minutes")
    print(f"  Smart meter penetration: {config.smart_meter_penetration*100:.0f}%")
    
    # Step 2: Initialize components
    print("\n[Step 2] Initializing components...")
    
    feeder_path = (
        "ieee_feeders/electricdss-code-r4166-trunk-Distrib-IEEETestCases-13Bus/"
        "electricdss-code-r4166-trunk-Distrib-IEEETestCases-13Bus/IEEE13Nodeckt.dss"
    )
    
    # Create OpenDSS interface
    opendss = OpenDSSInterface(feeder_path, config.feeder_name)
    
    # Create load manager
    load_manager = HybridGridLoadManager()
    
    # Add representative loads from IEEE 13 feeder.
    # Use actual OpenDSS load element names (not raw bus IDs).
    ieee13_loads = [
        ('634a', CustomerType.RESIDENTIAL, 3500),   # Light load (residential)
        ('634b', CustomerType.RESIDENTIAL, 3200),   # Light load (residential)
        ('645', CustomerType.COMMERCIAL, 12000),    # Medium load (commercial)
        ('646', CustomerType.COMMERCIAL, 8000),     # Medium load
        ('652', CustomerType.RESIDENTIAL, 4000),    # Light load
        ('671', CustomerType.INDUSTRIAL, 35000),    # Heavy load (industrial)
        ('670a', CustomerType.RESIDENTIAL, 5000),   # Light load
    ]
    load_manager.add_load_nodes_bulk(ieee13_loads)
    
    # Create metering system
    metering_system = HybridMeteringSystem([node[0] for node in ieee13_loads])
    metering_system.deploy_meters_by_penetration(config.smart_meter_penetration)
    
    # Create NTL engine
    ntl_engine = NTLInjectionEngine(load_manager)
    
    # Step 3: Create digital twin
    print("\n[Step 3] Creating digital twin...")
    digital_twin = HybridGridDigitalTwin(config)
    digital_twin.setup_feeder(opendss)
    digital_twin.setup_load_profiles(load_manager)
    digital_twin.setup_metering_system(metering_system)
    digital_twin.setup_ntl_engine(ntl_engine)
    
    # Step 4: Configure NTL scenarios
    print("\n[Step 4] Scheduling NTL events...")
    
    # Scenario 1: Partial meter bypass at node 652 (residential)
    ntl_engine.schedule_ntl_event(
        node_name='652',
        ntl_type=NTLType.PARTIAL_METER_BYPASS,
        start_day=2,
        start_hour=18.0,
        duration_hours=6.0,
        intensity=0.35,
        description="Partial bypass at residential node 652"
    )
    
    # Scenario 2: Meter tampering at node 671 (industrial)
    ntl_engine.schedule_ntl_event(
        node_name='671',
        ntl_type=NTLType.METER_TAMPERING,
        start_day=3,
        start_hour=8.0,
        duration_hours=12.0,
        intensity=0.30,
        description="Meter tampering at industrial node 671"
    )
    
    # Step 5: Run simulation
    print("\n[Step 5] Running simulation...")
    
    def progress_callback(current, total):
        if current % 96 == 0:  # Log every 24 hours
            pct = (current / total) * 100
            print(f"  Progress: {pct:.1f}% ({current}/{total} timesteps)")
    
    try:
        results_df = digital_twin.run_simulation(progress_callback=progress_callback)
        print(f"\n  Simulation completed: {len(results_df)} measurements recorded")
    except Exception as e:
        print(f"\n  ERROR: Simulation failed - {str(e)}")
        print("  NOTE: This may be due to missing IEEE feeder .dss file.")
        print("  Download from: https://sourceforge.net/p/electricdss/code/HEAD/tree/trunk/Distrib/IEEETestCases/")
        return
    
    # Step 6: Print summary
    print("\n[Step 6] Simulation Results:")
    digital_twin.print_summary()
    
    # Step 7: Export results
    print("\n[Step 7] Exporting results...")
    project_root = Path(__file__).resolve().parent
    output_dir = str(project_root / "results" / "ieee13_example")
    digital_twin.export_results(output_dir)
    print(f"  Results exported to: {output_dir}")
    
    # Step 8: Display sample data
    print("\n[Step 8] Sample Measurements (first 20 rows):")
    print(results_df.head(20).to_string())
    
    # Step 9: Analyze NTL statistics
    print("\n[Step 9] NTL Statistics by Node:")
    ntl_stats = digital_twin._compute_ntl_statistics()
    print(ntl_stats.to_string())
    
    return results_df, digital_twin


def example_with_realistic_profiles():
    """
    Example: Load profiles with real-world characteristics.
    """
    
    print("\n" + "="*70)
    print("EXAMPLE 2: Load Profile Generation with Real-World Patterns")
    print("="*70)
    
    from src.load_profiles import LoadProfileGenerator
    
    print("\n[Step 1] Generating load profiles for different customer types...")
    
    # Residential profile
    residential = LoadProfileGenerator(CustomerType.RESIDENTIAL, annual_consumption_kwh=4000)
    res_day1 = residential.get_hourly_profile(day_of_year=1)
    res_day180 = residential.get_hourly_profile(day_of_year=180)  # Summer
    
    # Commercial profile
    commercial = LoadProfileGenerator(CustomerType.COMMERCIAL, annual_consumption_kwh=50000)
    com_day1 = commercial.get_hourly_profile(day_of_year=1)
    com_day180 = commercial.get_hourly_profile(day_of_year=180)
    
    # Industrial profile
    industrial = LoadProfileGenerator(CustomerType.INDUSTRIAL, annual_consumption_kwh=200000)
    ind_day1 = industrial.get_hourly_profile(day_of_year=1)
    ind_day180 = industrial.get_hourly_profile(day_of_year=180)
    
    print("\n[Step 2] Profile Summary:")
    print(f"  Residential   - Day 1 avg load: {res_day1.mean():.2f}pu, "
          f"Day 180 avg: {res_day180.mean():.2f}pu (seasonal variation)")
    print(f"  Commercial    - Day 1 avg load: {com_day1.mean():.2f}pu, "
          f"Day 180 avg: {com_day180.mean():.2f}pu (seasonal variation)")
    print(f"  Industrial    - Day 1 avg load: {ind_day1.mean():.2f}pu, "
          f"Day 180 avg: {ind_day180.mean():.2f}pu (flat consumption)")
    
    # Export profiles to CSV
    hours = np.arange(24)
    profiles_df = pd.DataFrame({
        'Hour': hours,
        'Residential_Winter': res_day1,
        'Residential_Summer': res_day180,
        'Commercial_Winter': com_day1,
        'Commercial_Summer': com_day180,
        'Industrial_Winter': ind_day1,
        'Industrial_Summer': ind_day180,
    })
    
    Path("results").mkdir(exist_ok=True)
    profiles_df.to_csv("results/load_profiles.csv", index=False)
    print(f"\n  Exported load profiles to: results/load_profiles.csv")
    
    return profiles_df


def example_ntl_scenarios():
    """
    Example: Demonstrate various NTL scenario types.
    """
    
    print("\n" + "="*70)
    print("EXAMPLE 3: NTL Scenario Types and Detection Features")
    print("="*70)
    
    from src.load_profiles import HybridGridLoadManager, CustomerType
    from src.ntl_injection import NTLInjectionEngine, NTLType
    
    # Create load manager with dummy loads
    load_manager = HybridGridLoadManager()
    load_manager.add_load_nodes_bulk([
        ('node1', CustomerType.RESIDENTIAL, 4000),
        ('node2', CustomerType.COMMERCIAL, 50000),
    ])
    
    # Create NTL engine
    ntl_engine = NTLInjectionEngine(load_manager)
    
    # Schedule various NTL scenarios
    scenarios = [
        (NTLType.FULL_METER_BYPASS, 'node1', 1, 0, 24, 1.0),
        (NTLType.PARTIAL_METER_BYPASS, 'node2', 1, 8, 12, 0.4),
        (NTLType.METER_TAMPERING, 'node1', 1, 20, 4, 0.3),
        (NTLType.ILLEGAL_CONNECTION, 'node2', 1, 0, 24, 0.5),
        (NTLType.LOAD_MANIPULATION, 'node1', 1, 12, 6, 0.2),
        (NTLType.METER_FREEZING, 'node2', 1, 16, 8, 0.3),
    ]
    
    for ntl_type, node, day, hour, duration, intensity in scenarios:
        ntl_engine.schedule_ntl_event(node, ntl_type, day, hour, duration, intensity)
    
    print("\n[Step 1] Scheduled NTL Scenarios:")
    events_df = ntl_engine.export_event_schedule()
    print(events_df.to_string())
    
    # Simulate a 24-hour period with NTL
    print("\n[Step 2] Simulated Power Flows at Different Times:")
    
    times_to_check = [(1, 0), (1, 8), (1, 12), (1, 20)]
    
    for day, hour in times_to_check:
        all_data = ntl_engine.get_all_nodes_with_ntl(day, hour)
        summary = ntl_engine.get_ntl_summary(day, hour)
        
        print(f"\n  Time: Day {day}, Hour {hour}")
        print(f"    Total actual load:   {summary['total_actual_kw']:.1f} kW")
        print(f"    Total metered load:  {summary['total_metered_kw']:.1f} kW")
        print(f"    NTL loss:            {summary['total_ntl_loss_kw']:.1f} kW")
        print(f"    NTL percentage:      {summary['ntl_percentage']:.2f}%")
        print(f"    Affected nodes:      {summary['affected_nodes']}")
        
        for node, data in all_data.items():
            if data['ntl_type'] is not None:
                print(f"      - {node}: {data['ntl_type'].value}, "
                      f"loss={data['ntl_loss'][0]:.1f}kW")
    
    return events_df, ntl_engine


def main():
    """Run all examples."""
    
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  HYBRID GRID DIGITAL TWIN SIMULATION - COMPREHENSIVE EXAMPLES".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)
    
    # Example 1: Load profiles
    try:
        example_with_realistic_profiles()
    except Exception as e:
        print(f"\nExample 2 error: {str(e)}")
    
    # Example 2: NTL scenarios
    try:
        example_ntl_scenarios()
    except Exception as e:
        print(f"\nExample 3 error: {str(e)}")
    
    # Example 3: Full simulation (optional - requires IEEE feeder files)
    try:
        # example_ieee13_simulation()
        print("\n" + "="*70)
        print("NOTE: Full IEEE 13 simulation requires extracted feeder folders and valid entry files.")
        print("Download from: https://sourceforge.net/p/electricdss/code/HEAD/tree/trunk/Distrib/IEEETestCases/")
        print("Example entry: ieee_feeders/.../IEEE13Nodeckt.dss")
        print("Then uncomment 'example_ieee13_simulation()' in main()")
        print("="*70)
    except Exception as e:
        print(f"\nExample 1 error: {str(e)}")
    
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  Examples completed. Check results/ directory for outputs.".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70 + "\n")


if __name__ == "__main__":
    main()
