"""
Main Simulation Engine
======================
Orchestrates the complete digital twin simulation combining OpenDSS power flow,
load profiles, hybrid metering, and NTL injection.

Author: MENG Digital Twin Simulation
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Callable
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
                    
                    # Set load profile in OpenDSS
                    for node_name, (p_kw, q_kvar) in metered_loads.items():
                        self.opendss_interface.set_load_power(node_name, p_kw, q_kvar)
                    
                    # Solve power flow
                    self.opendss_interface.solve_power_flow(mode="snapshot")
                    
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
                        'meter_readings': meter_readings,
                        'ntl_data': all_ntl_data,
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
            
            stats.append({
                'Node': node_name,
                'Meter_Type': node_data['meter_type'].iloc[0] if len(node_data) > 0 else 'unknown',
                'Total_Energy_kWh': node_data['energy_kwh'].sum(),
                'Avg_Power_kW': node_data['measured_p_kw'].mean(),
                'Max_Power_kW': node_data['measured_p_kw'].max(),
                'Total_NTL_Loss_kWh': node_data['ntl_loss_kw'].sum() * (self.config.time_step_minutes / 60.0),
                'Avg_NTL_Loss_kW': node_data['ntl_loss_kw'].mean(),
                'NTL_Events_Count': node_data[node_data['ntl_type'] != 'None'].shape[0],
                'Data_Quality_Loss_Pct': (node_data['communication_loss'].sum() / len(node_data) * 100) if len(node_data) > 0 else 0,
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
        
        ntl_percentage = (total_ntl_loss / total_energy_supplied * 100) if total_energy_supplied > 0 else 0
        
        convergence_rate = (results_df['convergence'].sum() / len(results_df) * 100) if len(results_df) > 0 else 0
        
        return {
            'total_energy_supplied_kwh': total_energy_supplied,
            'total_energy_metered_kwh': total_energy_metered,
            'total_ntl_loss_kwh': total_ntl_loss,
            'ntl_percentage': ntl_percentage,
            'convergence_rate_percent': convergence_rate,
            'total_meters': self.metering_system.get_metering_statistics()['total_meters'],
            'smart_meters': self.metering_system.get_metering_statistics()['smart_meters'],
            'legacy_meters': self.metering_system.get_metering_statistics()['legacy_meters'],
            'num_timesteps': len(results_df),
        }

    def print_summary(self):
        """Print simulation summary to console."""
        stats = self.get_summary_statistics()
        
        print("\n" + "="*60)
        print("DIGITAL TWIN SIMULATION SUMMARY")
        print("="*60)
        print(f"Feeder:                    {self.config.feeder_name}")
        print(f"Simulation Duration:       {self.config.simulation_days} days")
        print(f"Total Energy Supplied:     {stats.get('total_energy_supplied_kwh', 0):.1f} kWh")
        print(f"Total Energy Metered:      {stats.get('total_energy_metered_kwh', 0):.1f} kWh")
        print(f"Total NTL Loss:            {stats.get('total_ntl_loss_kwh', 0):.1f} kWh")
        print(f"NTL Percentage:            {stats.get('ntl_percentage', 0):.2f}%")
        print(f"Power Flow Convergence:    {stats.get('convergence_rate_percent', 0):.1f}%")
        print(f"Total Meters:              {stats.get('total_meters', 0)}")
        print(f"  - Smart Meters:          {stats.get('smart_meters', 0)}")
        print(f"  - Legacy Meters:         {stats.get('legacy_meters', 0)}")
        print("="*60 + "\n")
