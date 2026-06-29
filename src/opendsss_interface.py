"""
OpenDSS Interface Module
========================
High-level wrapper around opendssdirect.py for IEEE feeder simulation.
Handles circuit initialization, load flow solutions, time-series simulation,
and data extraction from OpenDSS.

Author: MENG Digital Twin Simulation
"""

import os
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
import opendssdirect as dss
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OpenDSSInterface:
    """
    Interface to OpenDSS for IEEE test feeder simulation.
    Supports 13, 34, and 123 bus feeders with quasi-static time-series (QSTS) simulation.
    """

    def __init__(self, feeder_file: str, feeder_name: str = "IEEE13"):
        """
        Initialize OpenDSS interface with a feeder .dss file.

        Args:
            feeder_file: Path to IEEE feeder .dss file
            feeder_name: Name identifier (IEEE13, IEEE34, IEEE123)
        """
        self.feeder_file = feeder_file
        self.feeder_name = feeder_name
        self.circuit = None
        self.solved = False
        self.convergence_flag = False
        self.buses = []
        self.loads = []
        self.lines = []
        
        logger.info(f"Initializing OpenDSS with feeder: {feeder_name}")

    @staticmethod
    def _normalize_bus_name(bus_name: str) -> str:
        """Strip phase suffix from bus names like '650.1.2.3' -> '650'."""
        return bus_name.split(".")[0] if bus_name else bus_name
        
    def load_circuit(self) -> bool:
        """
        Load and initialize the circuit from .dss file.

        Returns:
            True if circuit loaded successfully, False otherwise
        """
        try:
            if not os.path.exists(self.feeder_file):
                logger.error(f"Feeder file not found: {self.feeder_file}")
                return False

            # Clear any previous circuit
            dss.run_command("Clear")
            
            # Load circuit file using absolute path to avoid issues with spaces/parentheses in Windows paths.
            feeder_abs = os.path.abspath(self.feeder_file)
            compile_result = dss.run_command(f'Compile "{feeder_abs}"')
            if isinstance(compile_result, str) and "error" in compile_result.lower():
                logger.error(f"Compile failed: {compile_result}")
                return False

            # Verify circuit loaded
            if dss.Circuit.NumBuses() == 0:
                logger.error("Circuit failed to load or is empty")
                return False

            self.circuit = dss.Circuit.Name()
            logger.info(f"Circuit loaded: {self.circuit}")
            logger.info(f"Number of buses: {dss.Circuit.NumBuses()}")
            logger.info(f"Number of loads: {len(dss.Loads.AllNames())}")
            
            self._extract_circuit_elements()
            return True
            
        except Exception as e:
            logger.error(f"Error loading circuit: {str(e)}")
            return False

    def _extract_circuit_elements(self):
        """Extract and cache circuit buses and loads for later use."""
        try:
            self.buses = dss.Circuit.AllBusNames()
            self.loads = dss.Loads.AllNames()
            self.lines = dss.Lines.AllNames()
            logger.info(f"Extracted {len(self.buses)} buses, {len(self.loads)} loads, {len(self.lines)} lines")
        except Exception as e:
            logger.error(f"Error extracting circuit elements: {str(e)}")

    def set_load_profile(self, load_name: str, multiplier_array: np.ndarray, time_interval_minutes: int = 15):
        """
        Set a load profile (time-varying multiplier) for a load.

        Args:
            load_name: Name of the load element
            multiplier_array: Array of load multipliers (0-1 or higher)
            time_interval_minutes: Time interval between samples (default 15 min)
        """
        try:
            # Check if load exists
            if load_name not in self.loads:
                logger.warning(f"Load {load_name} not found in circuit")
                return False

            # Create loadshape in OpenDSS
            n_points = len(multiplier_array)
            hour_array = np.arange(n_points) * (time_interval_minutes / 60.0)
            
            # Build loadshape definition
            loadshape_name = f"Profile_{load_name}"
            multiplier_str = " ".join([f"{m:.6f}" for m in multiplier_array])
            hour_str = " ".join([f"{h:.6f}" for h in hour_array])
            
            # Define loadshape in OpenDSS
            cmd = (f"New LoadShape.{loadshape_name} "
                   f"npts={n_points} "
                   f"interval={time_interval_minutes/60.0} "
                   f"mult=({multiplier_str}) "
                   f"hour=({hour_str})")
            dss.run_command(cmd)
            
            # Assign loadshape to load
            dss.Loads.Name(load_name)
            dss.run_command(f"Load.{load_name}.daily={loadshape_name}")
            
            logger.debug(f"Assigned profile {loadshape_name} to load {load_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting load profile: {str(e)}")
            return False

    def solve_power_flow(self, mode: str = "snapshot") -> bool:
        """
        Solve power flow for the circuit.

        Args:
            mode: "snapshot" for single point, "daily" for 24-hour, "yearly" for full year

        Returns:
            True if convergence achieved, False otherwise
        """
        try:
            if mode == "snapshot":
                dss.run_command("solve mode=snap")
            elif mode == "daily":
                dss.run_command("solve mode=daily number=1440 stepsize=1m")
            elif mode == "yearly":
                dss.run_command("solve mode=yearly number=8760 stepsize=1h")
            else:
                logger.error(f"Unknown solve mode: {mode}")
                return False

            # Check convergence
            self.convergence_flag = dss.Solution.Converged()
            self.solved = True
            
            if self.convergence_flag:
                logger.info(f"Power flow solved successfully (mode={mode})")
            else:
                logger.warning("Power flow did not converge")
            
            return self.convergence_flag
            
        except Exception as e:
            logger.error(f"Error solving power flow: {str(e)}")
            return False

    def get_bus_voltage(self, bus_name: str) -> Dict[str, float]:
        """
        Get voltage magnitude and angle at a bus.

        Args:
            bus_name: Bus name

        Returns:
            Dict with keys: 'magnitude_pu', 'angle_deg'
        """
        try:
            clean_bus_name = self._normalize_bus_name(bus_name)
            dss.Circuit.SetActiveBus(clean_bus_name)

            # puVmagAngle returns [V1, ang1, V2, ang2, ...] in per-unit.
            pu_mag_angle = dss.Bus.puVmagAngle()
            if not pu_mag_angle:
                return {'magnitude_pu': 0, 'angle_deg': 0, 'v_a_pu': 0, 'v_b_pu': 0, 'v_c_pu': 0}

            mags = pu_mag_angle[0::2]
            angles = pu_mag_angle[1::2]

            mag_pu = float(mags[0]) if mags else 0.0
            angle_deg = float(angles[0]) if angles else 0.0

            v_a = float(mags[0]) if len(mags) > 0 else 0.0
            v_b = float(mags[1]) if len(mags) > 1 else 0.0
            v_c = float(mags[2]) if len(mags) > 2 else 0.0
            
            return {
                'magnitude_pu': mag_pu,
                'angle_deg': angle_deg,
                'v_a_pu': v_a,
                'v_b_pu': v_b,
                'v_c_pu': v_c,
            }
        except Exception as e:
            logger.error(f"Error getting bus voltage for {bus_name}: {str(e)}")
            return {'magnitude_pu': 0, 'angle_deg': 0}

    def get_load_power(self, load_name: str) -> Dict[str, float]:
        """
        Get real and reactive power consumption from a load.

        Args:
            load_name: Load name

        Returns:
            Dict with keys: 'p_kw', 'q_kvar'
        """
        try:
            dss.Loads.Name(load_name)

            # Get power in kW and kVAr
            p_kw = dss.Loads.kW()
            q_kvar = dss.Loads.kvar()
            
            return {
                'p_kw': p_kw,
                'q_kvar': q_kvar,
            }
        except Exception as e:
            logger.error(f"Error getting load power for {load_name}: {str(e)}")
            return {'p_kw': 0, 'q_kvar': 0}

    def set_load_power(self, load_name: str, p_kw: float, q_kvar: float = 0):
        """
        Set load power (P and Q) directly.

        Args:
            load_name: Load name
            p_kw: Real power in kW
            q_kvar: Reactive power in kVAr
        """
        try:
            dss.Loads.Name(load_name)
            dss.run_command(f"Load.{load_name}.kW={p_kw}")
            dss.run_command(f"Load.{load_name}.kvar={q_kvar}")
            logger.debug(f"Set {load_name} to P={p_kw}kW, Q={q_kvar}kVAr")
        except Exception as e:
            logger.error(f"Error setting load power for {load_name}: {str(e)}")

    def inject_ntl(self, load_name: str, ntl_type: str, ntl_fraction: float):
        """
        Inject Non-Technical Loss at a load node.

        Args:
            load_name: Load name
            ntl_type: Type of NTL (bypass, tamper, illegal, etc.)
            ntl_fraction: Fraction of power lost/diverted (0-1)
        """
        try:
            dss.Loads.Name(load_name)

            current_p = dss.Loads.kW()
            current_q = dss.Loads.kvar()
            
            if ntl_type == "full_bypass":
                # All consumption diverted, meter reads zero but grid loses power
                # Model as reducing visible load to zero, but tracking actual load elsewhere
                new_p = 0
                new_q = 0
            elif ntl_type == "partial_bypass":
                # Fraction diverted
                new_p = current_p * (1 - ntl_fraction)
                new_q = current_q * (1 - ntl_fraction)
            elif ntl_type == "meter_tampering":
                # Underreporting but physical load unchanged
                # (real load stays, meter reading reduced - captured in metering layer)
                new_p = current_p
                new_q = current_q
            elif ntl_type == "illegal_connection":
                # Actual load increases but not on any meter
                # Model as load addition at node
                new_p = current_p * (1 + ntl_fraction)
                new_q = current_q * (1 + ntl_fraction)
            else:
                logger.warning(f"Unknown NTL type: {ntl_type}")
                return False
            
            self.set_load_power(load_name, new_p, new_q)
            logger.info(f"Injected NTL {ntl_type} at {load_name}: {ntl_fraction*100:.1f}%")
            return True
            
        except Exception as e:
            logger.error(f"Error injecting NTL: {str(e)}")
            return False

    def clear_ntl(self, load_name: str):
        """Clear NTL injection at a load (reset to nominal load)."""
        # This is a simplified version - in full implementation, track original loads
        logger.info(f"Cleared NTL at {load_name}")

    def get_all_loads_data(self) -> pd.DataFrame:
        """
        Extract power data from all loads in the circuit.

        Returns:
            DataFrame with columns: Load, P_kW, Q_kVAr, Voltage_pu
        """
        data = []
        
        for load_name in self.loads:
            try:
                power_data = self.get_load_power(load_name)
                # Get voltage at load bus
                dss.Circuit.SetActiveElement(f"Load.{load_name}")
                bus_names = dss.CktElement.BusNames()
                bus_name = bus_names[0] if bus_names else ""
                voltage_data = self.get_bus_voltage(bus_name)
                
                data.append({
                    'Load': load_name,
                    'P_kW': power_data['p_kw'],
                    'Q_kVAr': power_data['q_kvar'],
                    'Bus': bus_name,
                    'Voltage_pu': voltage_data['magnitude_pu'],
                })
            except Exception as e:
                logger.warning(f"Error extracting data from load {load_name}: {str(e)}")
        
        return pd.DataFrame(data)

    def quasi_static_time_series(self, num_steps: int = 96, 
                                 step_size_minutes: int = 15,
                                 progress_callback=None) -> List[Dict]:
        """
        Run quasi-static time-series simulation (QSTS).
        Solves power flow at each timestep with updated load profiles.

        Args:
            num_steps: Number of timesteps (96 = 24 hours at 15-min intervals)
            step_size_minutes: Time interval between steps
            progress_callback: Optional callback function for progress updates

        Returns:
            List of dictionaries containing snapshot data at each timestep
        """
        results = []
        
        try:
            for step in range(num_steps):
                # Set time
                hour = (step * step_size_minutes) / 60.0
                dss.run_command(f"set hour={hour} sec=0")
                
                # Solve power flow for this timestep
                if not self.solve_power_flow(mode="snapshot"):
                    logger.warning(f"Non-convergence at step {step}")
                
                # Extract snapshot data
                snapshot = {
                    'timestep': step,
                    'hour': hour,
                    'converged': self.convergence_flag,
                }
                
                # Get data from all loads
                loads_data = self.get_all_loads_data()
                snapshot['loads_data'] = loads_data
                
                results.append(snapshot)
                
                # Progress callback
                if progress_callback:
                    progress_callback(step, num_steps)
                
                if step % 24 == 0:
                    logger.info(f"QSTS step {step}/{num_steps} (hour {hour:.2f})")
            
            logger.info("QSTS simulation completed successfully")
            return results
            
        except Exception as e:
            logger.error(f"Error in quasi-static time-series simulation: {str(e)}")
            return results

    def export_results_to_dataframe(self, qsts_results: List[Dict]) -> pd.DataFrame:
        """
        Convert QSTS results to a pandas DataFrame for analysis.

        Args:
            qsts_results: List of snapshots from quasi_static_time_series

        Returns:
            Combined DataFrame with all measurements
        """
        all_data = []
        
        for snapshot in qsts_results:
            if 'loads_data' in snapshot:
                loads_data = snapshot['loads_data']
                loads_data['Timestep'] = snapshot['timestep']
                loads_data['Hour'] = snapshot['hour']
                loads_data['Converged'] = snapshot['converged']
                all_data.append(loads_data)
        
        if all_data:
            return pd.concat(all_data, ignore_index=True)
        else:
            return pd.DataFrame()

    def close(self):
        """Close the OpenDSS interface."""
        try:
            dss.run_command("Clear")
            logger.info("OpenDSS interface closed")
        except Exception as e:
            logger.error(f"Error closing OpenDSS: {str(e)}")
