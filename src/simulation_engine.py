"""
Main Simulation Engine
======================
Orchestrates the complete digital twin simulation combining OpenDSS power flow,
load profiles, hybrid metering, and NTL injection.

Author: MENG Digital Twin Simulation
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Callable, Tuple
from datetime import datetime, timedelta
import logging
from pathlib import Path
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimulationConfig:
    """Configuration for simulation parameters."""
    
    def __init__(self):
        self.feeder_path: str = ""
        self.feeder_name: str = "IEEE13"
        self.simulation_days: int = 30
        self.time_step_minutes: int = 15
        self.smart_meter_penetration: float = 0.5
        self.num_ntl_nodes: int = 3
        self.ntl_intensity_range: tuple = (0.2, 0.6)
        self.seed: int = 42
        self.realism_profile: str = "benchmark"
        
    def to_dict(self) -> Dict:
        """Convert configuration to dictionary."""
        return {
            'feeder_path': self.feeder_path,
            'feeder_name': self.feeder_name,
            'simulation_days': self.simulation_days,
            'time_step_minutes': self.time_step_minutes,
            'smart_meter_penetration': self.smart_meter_penetration,
            'num_ntl_nodes': self.num_ntl_nodes,
            'ntl_intensity_range': self.ntl_intensity_range,
            'seed': self.seed,
            'realism_profile': self.realism_profile,
        }

    @staticmethod
    def from_dict(config_dict: Dict) -> 'SimulationConfig':
        """Create configuration from dictionary."""
        config = SimulationConfig()
        for key, value in config_dict.items():
            if hasattr(config, key):
                setattr(config, key, value)
        return config


class HybridGridDigitalTwin:
    """
    Complete digital twin simulator for hybrid power distribution networks.
    Integrates OpenDSS, load profiles, metering, and NTL scenarios.
    """
    
    def __init__(self, config: SimulationConfig):
        """
        Initialize the digital twin.

        Args:
            config: SimulationConfig object
        """
        self.config = config
        self.opendss_interface = None
        self.load_manager = None
        self.metering_system = None
        self.ntl_engine = None
        
        self.simulation_results = []
        self.is_running = False
        self._feeder_baseline_kw = 0.0
        self._feeder_realism_state = {}
        
        np.random.seed(config.seed)
        
        logger.info(f"Initialized Digital Twin for {config.feeder_name} feeder")

    def setup_feeder(self, opendss_interface):
        """
        Set up the OpenDSS feeder interface.

        Args:
            opendss_interface: OpenDSSInterface instance
        """
        self.opendss_interface = opendss_interface
        
        if not self.opendss_interface.load_circuit():
            raise RuntimeError("Failed to load circuit")
        
        logger.info(f"Feeder loaded: {len(self.opendss_interface.buses)} buses, "
                   f"{len(self.opendss_interface.loads)} loads")

    def setup_load_profiles(self, load_manager):
        """
        Set up load profile manager.

        Args:
            load_manager: HybridGridLoadManager instance
        """
        self.load_manager = load_manager
        logger.info(f"Load manager configured with {len(load_manager.node_profiles)} nodes")

    def setup_metering_system(self, metering_system):
        """
        Set up hybrid metering system.

        Args:
            metering_system: HybridMeteringSystem instance
        """
        self.metering_system = metering_system
        logger.info("Hybrid metering system configured")

    def setup_ntl_engine(self, ntl_engine):
        """
        Set up NTL injection engine.

        Args:
            ntl_engine: NTLInjectionEngine instance
        """
        self.ntl_engine = ntl_engine
        logger.info("NTL injection engine configured")

    def validate_configuration(self) -> bool:
        """Validate that all components are configured."""
        if self.opendss_interface is None:
            logger.error("OpenDSS interface not configured")
            return False
        if self.load_manager is None:
            logger.error("Load manager not configured")
            return False
        if self.metering_system is None:
            logger.error("Metering system not configured")
            return False
        if self.ntl_engine is None:
            logger.error("NTL engine not configured")
            return False
        return True

    def _apply_feeder_realism(self, metered_loads: Dict[str, Tuple[float, float]], day: int, hour: float) -> Dict[str, Tuple[float, float]]:
        """Apply simple feeder-level realism to make synthetic loads behave more like a stressed distribution network."""
        adjusted = {}
        baseline_kw = max(sum(p for p, _ in metered_loads.values()), 1.0)
        self._feeder_baseline_kw = baseline_kw

        if hour >= 18.0:
            stress_factor = 0.92
        elif hour <= 6.0:
            stress_factor = 0.98
        else:
            stress_factor = 0.97

        for node_name, (p_kw, q_kvar) in metered_loads.items():
            prior_state = self._feeder_realism_state.get(node_name, 0.0)
            node_stress = stress_factor * (1.0 + 0.002 * max(prior_state, 0.0))
            if node_name.endswith(("1", "2", "3")):
                node_stress *= 0.995
            if day >= 4:
                node_stress *= 0.995

            adjusted[node_name] = (p_kw * node_stress, q_kvar * node_stress)

        return adjusted

    def _compute_calibration_summary(self, metered_loads: Dict[str, Tuple[float, float]], actual_loads: Dict[str, Tuple[float, float]]) -> Dict[str, float]:
        """Provide simple calibration targets for synthetic realism without real data."""
        total_metered = sum(p for p, _ in metered_loads.values())
        total_actual = sum(p for p, _ in actual_loads.values())
        gap_pct = ((total_actual - total_metered) / max(total_actual, 1e-9)) * 100.0 if total_actual > 0 else 0.0
        return {
            "metered_load_kw": float(total_metered),
            "actual_load_kw": float(total_actual),
            "gap_pct": float(gap_pct),
            "stress_factor": float(self._feeder_baseline_kw / max(total_metered, 1e-9)) if total_metered > 0 else 1.0,
        }

    def run_simulation(self, progress_callback: Optional[Callable] = None) -> pd.DataFrame:
        """
        Run complete digital twin simulation.

        Args:
            progress_callback: Optional callback(current_step, total_steps) for progress

        Returns:
            DataFrame with simulation results
        """
        if not self.validate_configuration():
            raise RuntimeError("Simulation not properly configured")
        
        logger.info(f"Starting simulation: {self.config.simulation_days} days, "
                   f"{self.config.time_step_minutes}-minute timesteps")
        
        self.is_running = True
        self.simulation_results = []
        
        num_steps_per_day = int(24 * 60 / self.config.time_step_minutes)
        total_steps = self.config.simulation_days * num_steps_per_day
        
        try:
            for day in range(1, self.config.simulation_days + 1):
                for step_in_day in range(num_steps_per_day):
                    step_global = (day - 1) * num_steps_per_day + step_in_day
                    hour = step_in_day * (self.config.time_step_minutes / 60.0)
                    
                    # Get all node powers with NTL
                    all_ntl_data = self.ntl_engine.get_all_nodes_with_ntl(day, hour)
                    
                    # Extract metered powers for OpenDSS
                    metered_loads = {}
                    for node_name, ntl_data in all_ntl_data.items():
                        metered_loads[node_name] = ntl_data['metered_power']

                    # Apply feeder-level realism so synthetic feeder behavior is more realistic.
                    metered_loads = self._apply_feeder_realism(metered_loads, day=day, hour=hour)
                    calibration_summary = self._compute_calibration_summary(metered_loads, {k: v['actual_power'] for k, v in all_ntl_data.items()})
                    for node_name in metered_loads:
                        prior_state = self._feeder_realism_state.get(node_name, 0.0)
                        self._feeder_realism_state[node_name] = float(min(5.0, prior_state + max(0.0, calibration_summary["gap_pct"] / 100.0)))
                    
                    # Set load profile in OpenDSS
                    for node_name, (p_kw, q_kvar) in metered_loads.items():
                        self.opendss_interface.set_load_power(node_name, p_kw, q_kvar)
                    
                    # Solve power flow
                    self.opendss_interface.solve_power_flow(mode="snapshot")

                    # Aggregate feeder-level powers for loss decomposition.
                    source_power = self.opendss_interface.get_total_circuit_power()
                    metered_total_kw = sum(p for p, _ in metered_loads.values())
                    actual_total_kw = sum(data['actual_power'][0] for data in all_ntl_data.values())
                    
                    # Record meter readings
                    meter_readings = self.metering_system.record_all_measurements(
                        metered_loads,
                        time_interval_minutes=self.config.time_step_minutes
                    )
                    
                    # Compile snapshot data
                    snapshot = {
                        'day': day,
                        'hour': hour,
                        'timestep': step_global,
                        'convergence': self.opendss_interface.convergence_flag,
                        'source_p_kw': source_power['p_kw'],
                        'metered_total_kw': metered_total_kw,
                        'actual_total_kw': actual_total_kw,
                        'meter_readings': meter_readings,
                        'ntl_data': all_ntl_data,
                        'calibration_summary': calibration_summary,
                    }
                    
                    self.simulation_results.append(snapshot)
                    
                    # Progress callback
                    if progress_callback:
                        progress_callback(step_global, total_steps)
                    
                    # Periodic logging
                    if (step_global + 1) % 96 == 0:  # Every 24 hours
                        ntl_summary = self.ntl_engine.get_ntl_summary(day, hour)
                        logger.info(f"Day {day} - Hour {hour:.2f}: "
                                   f"NTL={ntl_summary['ntl_percentage']:.2f}%, "
                                   f"Loss={ntl_summary['total_ntl_loss_kw']:.1f}kW")
            
            self.is_running = False
            logger.info("Simulation completed successfully")
            
            return self._compile_results_dataframe()
            
        except Exception as e:
            self.is_running = False
            logger.error(f"Simulation failed: {str(e)}")
            raise

    def _compile_results_dataframe(self) -> pd.DataFrame:
        """
        Compile simulation results into a single DataFrame.

        Returns:
            Combined DataFrame with all measurements and metadata
        """
        all_data = []
        
        for snapshot in self.simulation_results:
            if snapshot['meter_readings'] is not None:
                meter_df = snapshot['meter_readings'].copy()
                meter_df['day'] = snapshot['day']
                meter_df['hour'] = snapshot['hour']
                meter_df['timestep'] = snapshot['timestep']
                meter_df['convergence'] = snapshot['convergence']
                meter_df['source_p_kw'] = snapshot.get('source_p_kw', np.nan)
                meter_df['metered_total_kw'] = snapshot.get('metered_total_kw', np.nan)
                meter_df['actual_total_kw'] = snapshot.get('actual_total_kw', np.nan)
                calibration_summary = snapshot.get('calibration_summary', {})
                meter_df['calibration_gap_pct'] = calibration_summary.get('gap_pct', np.nan)
                meter_df['calibration_stress_factor'] = calibration_summary.get('stress_factor', np.nan)
                
                # Add NTL data
                for node_name, ntl_data in snapshot['ntl_data'].items():
                    mask = meter_df['node_name'] == node_name
                    if mask.any():
                        meter_df.loc[mask, 'actual_p_kw'] = ntl_data['actual_power'][0]
                        meter_df.loc[mask, 'ntl_loss_kw'] = ntl_data['ntl_loss'][0]
                        meter_df.loc[mask, 'ntl_type'] = str(ntl_data['ntl_type'])
                
                all_data.append(meter_df)
        
        if all_data:
            results_df = pd.concat(all_data, ignore_index=True)
            return results_df
        else:
            return pd.DataFrame()

    def export_results(self, output_dir: str):
        """
        Export simulation results to CSV files.

        Args:
            output_dir: Directory to save results
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        if not self.simulation_results:
            logger.warning("No simulation results to export")
            return
        
        # Export main results
        results_df = self._compile_results_dataframe()
        results_df.to_csv(output_path / "simulation_results.csv", index=False)
        logger.info(f"Exported main results: {results_df.shape[0]} rows")
        
        # Export NTL event schedule
        ntl_schedule = self.ntl_engine.export_event_schedule()
        ntl_schedule.to_csv(output_path / "ntl_events.csv", index=False)
        logger.info(f"Exported NTL schedule: {len(ntl_schedule)} events")
        
        # Export configuration
        config_dict = self.config.to_dict()
        with open(output_path / "simulation_config.json", 'w') as f:
            json.dump(config_dict, f, indent=2)
        logger.info("Exported configuration")
        
        # Export NTL statistics
        ntl_stats = self._compute_ntl_statistics()
        ntl_stats.to_csv(output_path / "ntl_statistics.csv", index=False)
        logger.info("Exported NTL statistics")

        # Export realism report
        realism_report = self._build_realism_report()
        realism_report.to_csv(output_path / "realism_report.csv", index=False)
        logger.info("Exported realism report")

    def _build_realism_report(self) -> pd.DataFrame:
        """Build a compact summary of realism KPIs for export and downstream analysis."""
        stats = self.get_summary_statistics()
        if not stats:
            return pd.DataFrame(columns=["metric", "value", "unit"])

        report_rows = [
            {"metric": "total_energy_supplied_kwh", "value": stats.get("total_energy_supplied_kwh", 0.0), "unit": "kWh"},
            {"metric": "total_energy_metered_kwh", "value": stats.get("total_energy_metered_kwh", 0.0), "unit": "kWh"},
            {"metric": "total_gap_kwh", "value": stats.get("total_gap_kwh", 0.0), "unit": "kWh"},
            {"metric": "total_ntl_loss_kwh", "value": stats.get("total_ntl_loss_kwh", 0.0), "unit": "kWh"},
            {"metric": "metering_data_gap_kwh", "value": stats.get("metering_data_gap_kwh", 0.0), "unit": "kWh"},
            {"metric": "communication_loss_rate_percent", "value": stats.get("communication_loss_rate_percent", 0.0), "unit": "%"},
            {"metric": "technical_loss_pct_of_source", "value": stats.get("technical_loss_pct_of_source", 0.0), "unit": "%"},
            {"metric": "ntl_percentage", "value": stats.get("ntl_percentage", 0.0), "unit": "%"},
            {"metric": "convergence_rate_percent", "value": stats.get("convergence_rate_percent", 0.0), "unit": "%"},
            {"metric": "realism_profile", "value": stats.get("profile", self.config.realism_profile), "unit": "-"},
        ]
        return pd.DataFrame(report_rows)

    def _compute_ntl_statistics(self) -> pd.DataFrame:
        """
        Compute aggregate NTL statistics per node.

        Returns:
            DataFrame with NTL statistics
        """
        results_df = self._compile_results_dataframe()
        
        if results_df.empty:
            return pd.DataFrame()
        
        stats = []
        
        for node_name in results_df['node_name'].unique():
            node_data = results_df[results_df['node_name'] == node_name]
            energy_series = node_data['energy_kwh'] if 'energy_kwh' in node_data.columns else pd.Series(0.0, index=node_data.index)
            measured_series = node_data['measured_p_kw'] if 'measured_p_kw' in node_data.columns else pd.Series(0.0, index=node_data.index)
            ntl_loss_series = node_data['ntl_loss_kw'] if 'ntl_loss_kw' in node_data.columns else pd.Series(0.0, index=node_data.index)
            ntl_type_series = node_data['ntl_type'] if 'ntl_type' in node_data.columns else pd.Series('None', index=node_data.index)
            communication_loss_series = node_data['communication_loss'] if 'communication_loss' in node_data.columns else pd.Series(False, index=node_data.index)
            
            stats.append({
                'Node': node_name,
                'Meter_Type': node_data['meter_type'].iloc[0] if 'meter_type' in node_data.columns and len(node_data) > 0 else 'unknown',
                'Total_Energy_kWh': energy_series.sum(),
                'Avg_Power_kW': measured_series.mean(),
                'Max_Power_kW': measured_series.max(),
                'Total_NTL_Loss_kWh': ntl_loss_series.sum() * (self.config.time_step_minutes / 60.0),
                'Avg_NTL_Loss_kW': ntl_loss_series.mean(),
                'NTL_Events_Count': ntl_type_series[ntl_type_series != 'None'].shape[0],
                'Data_Quality_Loss_Pct': (communication_loss_series.sum() / len(node_data) * 100) if len(node_data) > 0 else 0,
            })
        
        return pd.DataFrame(stats)

    def get_summary_statistics(self) -> Dict:
        """
        Get overall simulation summary statistics.

        Returns:
            Dictionary with key metrics
        """
        results_df = self._compile_results_dataframe()
        
        if results_df.empty:
            return {}
        
        total_energy_supplied = results_df['actual_p_kw'].sum() * (self.config.time_step_minutes / 60.0)
        total_energy_metered = results_df['measured_p_kw'].sum() * (self.config.time_step_minutes / 60.0)
        total_ntl_loss = results_df['ntl_loss_kw'].sum() * (self.config.time_step_minutes / 60.0)
        total_gap_kwh = total_energy_supplied - total_energy_metered

        # Non-NTL baseline is the post-theft physical demand before meter errors and comm drops.
        baseline_non_ntl_kw = results_df['actual_p_kw'] - results_df['ntl_loss_kw']
        measured_kw = results_df['measured_p_kw']
        meas_factor = results_df.get('measurement_error_factor', pd.Series(1.0, index=results_df.index))

        # What the meter would report without communication dropout (still includes meter error).
        measured_no_comm_kw = baseline_non_ntl_kw * meas_factor

        if 'communication_loss' in results_df.columns:
            comm_mask = results_df['communication_loss'].astype(bool)
            measured_no_comm_kw = measured_no_comm_kw.where(comm_mask, measured_kw)
        else:
            comm_mask = pd.Series(False, index=results_df.index)

        non_ntl_gap_kw_series = baseline_non_ntl_kw - measured_kw
        communication_gap_kw_series = measured_no_comm_kw - measured_kw
        meter_bias_gap_kw_series = baseline_non_ntl_kw - measured_no_comm_kw

        timestep_hours = self.config.time_step_minutes / 60.0
        metering_data_gap_kwh = float(non_ntl_gap_kw_series.sum() * timestep_hours)
        communication_gap_kwh = float(communication_gap_kw_series.sum() * timestep_hours)
        meter_bias_gap_kwh = float(meter_bias_gap_kw_series.sum() * timestep_hours)
        meter_bias_under_kwh = float(meter_bias_gap_kw_series.clip(lower=0.0).sum() * timestep_hours)
        meter_bias_over_kwh = float((-meter_bias_gap_kw_series.clip(upper=0.0)).sum() * timestep_hours)

        source_energy_kwh = 0.0
        technical_loss_kwh_est = 0.0
        for snapshot in self.simulation_results:
            source_kw = float(snapshot.get('source_p_kw', 0.0))
            metered_kw = float(snapshot.get('metered_total_kw', 0.0))
            source_energy_kwh += source_kw * timestep_hours
            technical_loss_kwh_est += max(source_kw - metered_kw, 0.0) * timestep_hours
        
        ntl_percentage = (total_ntl_loss / total_energy_supplied * 100) if total_energy_supplied > 0 else 0
        
        convergence_rate = (results_df['convergence'].sum() / len(results_df) * 100) if len(results_df) > 0 else 0
        
        return {
            'total_energy_supplied_kwh': total_energy_supplied,
            'total_energy_metered_kwh': total_energy_metered,
            'total_gap_kwh': total_gap_kwh,
            'total_ntl_loss_kwh': total_ntl_loss,
            'metering_data_gap_kwh': metering_data_gap_kwh,
            'communication_gap_kwh': communication_gap_kwh,
            'meter_bias_gap_kwh': meter_bias_gap_kwh,
            'meter_bias_under_kwh': meter_bias_under_kwh,
            'meter_bias_over_kwh': meter_bias_over_kwh,
            'source_energy_kwh': source_energy_kwh,
            'technical_loss_kwh_est': technical_loss_kwh_est,
            'technical_loss_pct_of_source': (
                (technical_loss_kwh_est / source_energy_kwh) * 100
                if source_energy_kwh > 0
                else 0.0
            ),
            'ntl_percentage': ntl_percentage,
            'convergence_rate_percent': convergence_rate,
            'communication_loss_rate_percent': (
                float(results_df['communication_loss'].mean() * 100)
                if 'communication_loss' in results_df.columns and len(results_df) > 0
                else 0.0
            ),
            'profile': self.config.realism_profile,
            'total_meters': self.metering_system.get_metering_statistics()['total_meters'],
            'smart_meters': self.metering_system.get_metering_statistics()['smart_meters'],
            'legacy_meters': self.metering_system.get_metering_statistics()['legacy_meters'],
            'num_timesteps': len(results_df),
        }

    def _evaluate_realism_kpis(self, stats: Dict) -> List[str]:
        """Return KPI status lines compared to profile-specific expected ranges."""
        profile = stats.get('profile', 'benchmark')
        ranges = {
            'benchmark': {
                'technical_loss_pct_of_source': (2.0, 8.0),
                'communication_loss_rate_percent': (0.0, 6.0),
                'ntl_percentage': (0.0, 2.0),
            },
            'utility': {
                'technical_loss_pct_of_source': (3.0, 12.0),
                'communication_loss_rate_percent': (0.0, 3.0),
                'ntl_percentage': (5.0, 9.0),
            },
            'stressed': {
                'technical_loss_pct_of_source': (5.0, 18.0),
                'communication_loss_rate_percent': (1.0, 12.0),
                'ntl_percentage': (0.0, 6.0),
            },
        }.get(profile, {})

        labels = {
            'technical_loss_pct_of_source': 'Technical loss %',
            'communication_loss_rate_percent': 'Communication loss %',
            'ntl_percentage': 'NTL %',
        }

        lines: List[str] = []
        for key, (low, high) in ranges.items():
            value = float(stats.get(key, 0.0))
            status = 'OK' if low <= value <= high else 'CHECK'
            lines.append(
                f"{status}: {labels[key]} = {value:.2f}% (expected {low:.1f}-{high:.1f}%)"
            )
        return lines

    def print_summary(self):
        """Print simulation summary to console."""
        stats = self.get_summary_statistics()
        
        print("\n" + "="*60)
        print("DIGITAL TWIN SIMULATION SUMMARY")
        print("="*60)
        print(f"Feeder:                    {self.config.feeder_name}")
        print(f"Realism Profile:           {stats.get('profile', 'benchmark')}")
        print(f"Simulation Duration:       {self.config.simulation_days} days")
        print(f"Total Energy Supplied:     {stats.get('total_energy_supplied_kwh', 0):.1f} kWh")
        print(f"Total Energy Metered:      {stats.get('total_energy_metered_kwh', 0):.1f} kWh")
        print(f"Total Gap (Supplied-Metered): {stats.get('total_gap_kwh', 0):.1f} kWh")
        print(f"Total NTL Loss:            {stats.get('total_ntl_loss_kwh', 0):.1f} kWh")
        print(f"Non-NTL Meter/Data Gap (net): {stats.get('metering_data_gap_kwh', 0):.1f} kWh")
        print(f"  - Communication Gap:        {stats.get('communication_gap_kwh', 0):.1f} kWh")
        print(f"  - Meter Bias Gap (net):     {stats.get('meter_bias_gap_kwh', 0):.1f} kWh")
        print(f"    * Under-registration:     {stats.get('meter_bias_under_kwh', 0):.1f} kWh")
        print(f"    * Over-registration:      {stats.get('meter_bias_over_kwh', 0):.1f} kWh")
        print(f"Source Energy (OpenDSS):   {stats.get('source_energy_kwh', 0):.1f} kWh")
        print(f"Estimated Technical Loss:  {stats.get('technical_loss_kwh_est', 0):.1f} kWh")
        print(f"Technical Loss % (source): {stats.get('technical_loss_pct_of_source', 0):.2f}%")
        print(f"NTL Percentage:            {stats.get('ntl_percentage', 0):.2f}%")
        print(f"Comm Loss Rate:            {stats.get('communication_loss_rate_percent', 0):.2f}%")
        print(f"Power Flow Convergence:    {stats.get('convergence_rate_percent', 0):.1f}%")
        print(f"Total Meters:              {stats.get('total_meters', 0)}")
        print(f"  - Smart Meters:          {stats.get('smart_meters', 0)}")
        print(f"  - Legacy Meters:         {stats.get('legacy_meters', 0)}")
        print("Realism KPI Check:")
        for line in self._evaluate_realism_kpis(stats):
            print(f"  - {line}")
        print("="*60 + "\n")
