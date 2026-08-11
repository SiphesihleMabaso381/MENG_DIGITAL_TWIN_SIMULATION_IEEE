"""
Hybrid Metering System Module
==============================
Simulates realistic smart meters and legacy electromechanical meters
with their respective characteristics, measurement errors, and communication patterns.

Author: MENG Digital Twin Simulation
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MeterType(Enum):
    """Enum for meter types."""
    SMART_METER = "smart"
    LEGACY_METER = "legacy"


@dataclass
class MeterCharacteristics:
    """Characteristics of different meter types."""
    meter_type: MeterType
    accuracy_class: float  # IEC 62053 accuracy class (e.g., 0.5, 1, 2)
    sampling_interval_minutes: int  # Data collection interval
    reporting_interval_minutes: int  # Data reporting interval
    has_voltage_sensor: bool
    has_current_sensor: bool
    has_harmonics: bool
    communication_reliability: float  # Packet arrival rate (0-1)
    communication_recovery_rate: float  # Share of dropped packets later recovered/reconstructed
    communication_burst_probability: float  # Probability of entering burst outage
    communication_burst_steps_min: int  # Minimum burst duration in timesteps
    communication_burst_steps_max: int  # Maximum burst duration in timesteps
    tamper_flag_support: bool  # Can detect meter tampering
    clock_drift_ppm: float  # Clock drift in parts per million
    
    
class SmartMeterCharacteristics(MeterCharacteristics):
    """Smart meter (AMI) characteristics."""
    def __init__(
        self,
        accuracy_class: float = 0.5,
        communication_reliability: float = 0.95,
        communication_recovery_rate: float = 0.0,
        communication_burst_probability: float = 0.01,
        communication_burst_steps_min: int = 2,
        communication_burst_steps_max: int = 8,
    ):
        super().__init__(
            meter_type=MeterType.SMART_METER,
            accuracy_class=accuracy_class,
            sampling_interval_minutes=1,  # 1-min internal sampling
            reporting_interval_minutes=15,  # 15-min billing interval
            has_voltage_sensor=True,
            has_current_sensor=True,
            has_harmonics=True,
            communication_reliability=communication_reliability,
            communication_recovery_rate=communication_recovery_rate,
            communication_burst_probability=communication_burst_probability,
            communication_burst_steps_min=max(int(communication_burst_steps_min), 1),
            communication_burst_steps_max=max(int(communication_burst_steps_max), 1),
            tamper_flag_support=True,
            clock_drift_ppm=10,  # ±10 ppm typical
        )


class LegacyMeterCharacteristics(MeterCharacteristics):
    """Legacy electromechanical meter characteristics."""
    def __init__(
        self,
        accuracy_class: float = 2.0,
        communication_reliability: float = 1.0,
        communication_recovery_rate: float = 0.0,
        communication_burst_probability: float = 0.0,
        communication_burst_steps_min: int = 1,
        communication_burst_steps_max: int = 1,
    ):
        super().__init__(
            meter_type=MeterType.LEGACY_METER,
            accuracy_class=accuracy_class,
            sampling_interval_minutes=60,  # 1-hour mechanical sampling
            reporting_interval_minutes=60*24*30,  # Monthly manual reading
            has_voltage_sensor=False,
            has_current_sensor=False,
            has_harmonics=False,
            communication_reliability=communication_reliability,
            communication_recovery_rate=communication_recovery_rate,
            communication_burst_probability=communication_burst_probability,
            communication_burst_steps_min=max(int(communication_burst_steps_min), 1),
            communication_burst_steps_max=max(int(communication_burst_steps_max), 1),
            tamper_flag_support=False,  # No tamper detection
            clock_drift_ppm=100,  # ±100 ppm (mechanical drift)
        )


class Meter:
    """
    Individual meter simulator.
    Simulates realistic meter behavior including errors, communication issues,
    and meter-specific characteristics.
    """
    
    def __init__(self, meter_id: str, node_name: str, 
                 characteristics: MeterCharacteristics,
                 node_type: str = "residential"):
        """
        Initialize a meter.

        Args:
            meter_id: Unique meter identifier
            node_name: Associated load/node name in the grid
            characteristics: MeterCharacteristics object
            node_type: Classification (residential, commercial, industrial)
        """
        self.meter_id = meter_id
        self.node_name = node_name
        self.characteristics = characteristics
        self.node_type = node_type
        
        # Meter state
        self.cumulative_energy_kwh = 0.0
        self.cumulative_reactive_kvarh = 0.0
        self.tamper_detected = False
        self.clock_offset_seconds = 0
        self.measurement_error_factor = 1.0  # Multiplicative error
        self.communication_outage_remaining_steps = 0
        self.data_quality_profile: Dict[str, float] = {
            "missing_reading_probability": 0.0,
            "stale_reading_probability": 0.0,
            "noise_scale": 0.0,
        }
        
        # Initialize random meter-specific error
        self._init_measurement_error()
        
        # Initialize clock drift (slow accumulation)
        self._init_clock_drift()
        
    def _init_measurement_error(self):
        """Initialize meter-specific measurement error based on accuracy class."""
        # Accuracy class defines ±percentage error
        # Simulate as +/- around accuracy class
        max_error_pct = self.characteristics.accuracy_class
        error_pct = np.random.uniform(-max_error_pct, max_error_pct)
        self.measurement_error_factor = 1.0 + (error_pct / 100.0)
        
    def _init_clock_drift(self):
        """Initialize meter clock drift."""
        drift_ppm = self.characteristics.clock_drift_ppm
        self.clock_offset_seconds = np.random.uniform(-drift_ppm, drift_ppm) / 1e6 * 3600
        
    def record_measurement(self, p_kw: float, q_kvar: float = 0, 
                          time_interval_minutes: float = 15) -> Dict:
        """
        Record an energy measurement at the meter.
        Applies realistic errors: measurement error, communication loss, etc.

        Args:
            p_kw: Real power in kW
            q_kvar: Reactive power in kVAr
            time_interval_minutes: Time since last reading

        Returns:
            Dict with recorded measurement and metadata
        """
        # Apply measurement error (affects recorded consumption)
        measured_p_kw = p_kw * self.measurement_error_factor
        measured_q_kvar = q_kvar * self.measurement_error_factor
        
        # Calculate energy (kW × h = kWh)
        time_hours = time_interval_minutes / 60.0
        energy_kwh = measured_p_kw * time_hours
        reactive_kvarh = measured_q_kvar * time_hours
        
        # Accumulate
        self.cumulative_energy_kwh += energy_kwh
        self.cumulative_reactive_kvarh += reactive_kvarh
        
        # Apply synthetic data-quality imperfections.
        missing_reading_probability = self.data_quality_profile.get("missing_reading_probability", 0.0)
        stale_reading_probability = self.data_quality_profile.get("stale_reading_probability", 0.0)
        noise_scale = self.data_quality_profile.get("noise_scale", 0.0)
        self.measurement_uncertainty_pct = max(0.0, abs(self.measurement_error_factor - 1.0) * 100.0 + noise_scale * 100.0)

        if np.random.random() < missing_reading_probability:
            measured_p_out = 0.0
            measured_q_out = 0.0
            energy_out = 0.0
            reactive_out = 0.0
            communication_loss = True
            communication_recovered = False
        else:
            measured_p_out = measured_p_kw
            measured_q_out = measured_q_kvar
            energy_out = energy_kwh
            reactive_out = reactive_kvarh

        if np.random.random() < stale_reading_probability:
            measured_p_out = max(0.0, measured_p_out * 0.85)
            measured_q_out = max(0.0, measured_q_out * 0.85)
            energy_out = measured_p_out * time_hours
            reactive_out = measured_q_out * time_hours

        if noise_scale > 0:
            noise_factor = 1.0 + np.random.normal(0.0, noise_scale)
            measured_p_out = max(0.0, measured_p_out * noise_factor)
            measured_q_out = max(0.0, measured_q_out * noise_factor)
            energy_out = measured_p_out * time_hours
            reactive_out = measured_q_out * time_hours

        # Communication loss with realistic burst-outage behavior.
        if self.communication_outage_remaining_steps > 0:
            communication_loss = True
            self.communication_outage_remaining_steps -= 1
        else:
            # Trigger outage burst first.
            if np.random.random() < self.characteristics.communication_burst_probability:
                low = self.characteristics.communication_burst_steps_min
                high = self.characteristics.communication_burst_steps_max
                if high < low:
                    high = low
                self.communication_outage_remaining_steps = int(np.random.randint(low, high + 1))
                communication_loss = True
                self.communication_outage_remaining_steps -= 1
            else:
                communication_loss = np.random.random() > self.characteristics.communication_reliability
        
        # Clock offset affects timestamp
        drift_scale = self.data_quality_profile.get("clock_drift_scale", 0.0)
        timestamp_offset_sec = self.clock_offset_seconds + drift_scale * 60.0
        
        # Generate tamper flag if tamper is detected and meter supports it
        tamper_flag = False
        if self.characteristics.tamper_flag_support and self.tamper_detected:
            tamper_flag = True
        
        communication_recovered = False
        measured_p_out = measured_p_kw
        measured_q_out = measured_q_kvar
        energy_out = energy_kwh
        reactive_out = reactive_kvarh

        if communication_loss:
            if np.random.random() < self.characteristics.communication_recovery_rate:
                # Backfill missing reads with a realistic reconstruction error.
                recovery_factor = np.random.normal(1.0, 0.01)
                measured_p_out = measured_p_kw * recovery_factor
                measured_q_out = measured_q_kvar * recovery_factor
                energy_out = measured_p_out * time_hours
                reactive_out = measured_q_out * time_hours
                communication_recovered = True
            else:
                measured_p_out = 0.0
                measured_q_out = 0.0
                energy_out = 0.0
                reactive_out = 0.0

        data_quality_flag = "nominal"
        if communication_loss:
            data_quality_flag = "communication_loss"
        if np.random.random() < missing_reading_probability:
            data_quality_flag = "missing_reading"
        elif np.random.random() < stale_reading_probability:
            data_quality_flag = "stale_reading"
        elif noise_scale > 0.0:
            data_quality_flag = "noisy"

        return {
            'meter_id': self.meter_id,
            'node_name': self.node_name,
            'actual_p_kw': p_kw,
            'actual_q_kvar': q_kvar,
            'measured_p_kw': measured_p_out,
            'measured_q_kvar': measured_q_out,
            'energy_kwh': energy_out,
            'reactive_kvarh': reactive_out,
            'cumulative_kwh': self.cumulative_energy_kwh,
            'meter_type': self.characteristics.meter_type.value,
            'communication_loss': communication_loss,
            'communication_recovered': communication_recovered,
            'timestamp_offset_sec': timestamp_offset_sec,
            'tamper_flag': tamper_flag,
            'measurement_error_factor': self.measurement_error_factor,
            'accuracy_class': self.characteristics.accuracy_class,
            'missing_reading': np.random.random() < missing_reading_probability,
            'measurement_uncertainty_pct': self.measurement_uncertainty_pct,
            'data_quality_flag': data_quality_flag,
        }

    def inject_tamper(self, tamper_type: str):
        """
        Inject meter tampering.

        Args:
            tamper_type: Type of tamper (halt, reverse, scaling, etc.)
        """
        if tamper_type == "halt":
            # Freeze meter reading
            self.measurement_error_factor = 0.0
            self.tamper_detected = True
        elif tamper_type == "reverse":
            # Reverse rotation (doesn't accumulate)
            self.measurement_error_factor = -1.0
            self.tamper_detected = True
        elif tamper_type == "scaling":
            # Underreport by scaling down
            self.measurement_error_factor = 0.3  # Report only 30%
            self.tamper_detected = True
            
    def clear_tamper(self):
        """Clear meter tampering and reset to normal."""
        self._init_measurement_error()
        self.tamper_detected = False


class HybridMeteringSystem:
    """
    Manages a hybrid metering infrastructure with both smart and legacy meters.
    Provides realistic simulation of meter readings, errors, and communication issues.
    """
    
    def __init__(self, nodes: List[str]):
        """
        Initialize the hybrid metering system.

        Args:
            nodes: List of load/node names in the grid
        """
        self.nodes = nodes
        self.meters: Dict[str, Meter] = {}
        self.meter_placement: Dict[str, str] = {}  # node -> meter_id mapping
        self.data_quality_profile: Dict[str, float] = {
            "missing_reading_probability": 0.0,
            "stale_reading_probability": 0.0,
            "noise_scale": 0.0,
        }
        
        logger.info(f"Initialized hybrid metering system for {len(nodes)} nodes")
        
    def deploy_meters(
        self,
        smart_meter_nodes: List[str],
        legacy_meter_nodes: Optional[List[str]] = None,
        meter_profile: Optional[Dict[str, float]] = None,
    ):
        """
        Deploy meters to specific nodes.

        Args:
            smart_meter_nodes: List of nodes with smart meters
            legacy_meter_nodes: List of nodes with legacy meters (default: remaining nodes)
        """
        if legacy_meter_nodes is None:
            legacy_meter_nodes = [n for n in self.nodes if n not in smart_meter_nodes]
        
        meter_profile = meter_profile or {}

        smart_accuracy = float(meter_profile.get('smart_accuracy_class', 0.5))
        legacy_accuracy = float(meter_profile.get('legacy_accuracy_class', 2.0))
        smart_comm_mean = float(meter_profile.get('smart_communication_reliability', 0.95))
        smart_comm_std = float(meter_profile.get('smart_communication_reliability_std', 0.01))
        smart_comm_recovery = float(meter_profile.get('smart_communication_recovery_rate', 0.0))
        legacy_comm = float(meter_profile.get('legacy_communication_reliability', 1.0))
        legacy_comm_recovery = float(meter_profile.get('legacy_communication_recovery_rate', 0.0))
        smart_burst_prob = float(meter_profile.get('smart_burst_probability', 0.01))
        smart_burst_min = int(meter_profile.get('smart_burst_steps_min', 2))
        smart_burst_max = int(meter_profile.get('smart_burst_steps_max', 8))

        # Deploy smart meters
        for i, node in enumerate(smart_meter_nodes):
            meter_id = f"SM_{node}"
            per_meter_reliability = float(np.clip(
                np.random.normal(smart_comm_mean, smart_comm_std),
                0.70,
                0.999,
            ))
            smart_chars = SmartMeterCharacteristics(
                accuracy_class=smart_accuracy,
                communication_reliability=per_meter_reliability,
                communication_recovery_rate=float(np.clip(smart_comm_recovery, 0.0, 1.0)),
                communication_burst_probability=max(0.0, smart_burst_prob),
                communication_burst_steps_min=max(1, smart_burst_min),
                communication_burst_steps_max=max(1, smart_burst_max),
            )
            meter = Meter(meter_id, node, smart_chars, node_type="residential")
            self.meters[meter_id] = meter
            self.meter_placement[node] = meter_id
            
        # Deploy legacy meters
        for i, node in enumerate(legacy_meter_nodes):
            meter_id = f"LM_{node}"
            legacy_chars = LegacyMeterCharacteristics(
                accuracy_class=legacy_accuracy,
                communication_reliability=float(np.clip(legacy_comm, 0.80, 1.0)),
                communication_recovery_rate=float(np.clip(legacy_comm_recovery, 0.0, 1.0)),
            )
            meter = Meter(meter_id, node, legacy_chars, node_type="residential")
            self.meters[meter_id] = meter
            self.meter_placement[node] = meter_id
        
        logger.info(f"Deployed {len(smart_meter_nodes)} smart meters and {len(legacy_meter_nodes)} legacy meters")
        
    def deploy_meters_by_penetration(
        self,
        smart_meter_fraction: float = 0.5,
        meter_profile: Optional[Dict[str, float]] = None,
    ):
        """
        Deploy meters based on smart meter penetration rate.

        Args:
            smart_meter_fraction: Fraction of nodes with smart meters (0-1)
        """
        num_smart = int(len(self.nodes) * smart_meter_fraction)
        smart_nodes = np.random.choice(self.nodes, num_smart, replace=False).tolist()
        legacy_nodes = [n for n in self.nodes if n not in smart_nodes]
        
        self.deploy_meters(smart_nodes, legacy_nodes, meter_profile=meter_profile)
        logger.info(f"Smart meter penetration: {len(smart_nodes)}/{len(self.nodes)} "
                   f"({smart_meter_fraction*100:.1f}%)")

    def set_data_quality_profile(self, profile: Dict[str, float]) -> None:
        """Set a shared profile for meter data-quality imperfections."""
        self.data_quality_profile = {
            "missing_reading_probability": float(profile.get("missing_reading_probability", 0.0)),
            "stale_reading_probability": float(profile.get("stale_reading_probability", 0.0)),
            "noise_scale": float(profile.get("noise_scale", 0.0)),
        }

    def record_all_measurements(self, node_power_map: Dict[str, Tuple[float, float]],
                               time_interval_minutes: float = 15) -> pd.DataFrame:
        """
        Record measurements from all meters simultaneously.

        Args:
            node_power_map: Dict mapping node_name -> (p_kw, q_kvar)
            time_interval_minutes: Time interval since last reading

        Returns:
            DataFrame with all meter readings
        """
        measurements = []
        
        for node_name, (p_kw, q_kvar) in node_power_map.items():
            if node_name in self.meter_placement:
                meter_id = self.meter_placement[node_name]
                meter = self.meters[meter_id]
                meter.data_quality_profile = dict(self.data_quality_profile)
                measurement = meter.record_measurement(p_kw, q_kvar, time_interval_minutes)
                measurements.append(measurement)
        
        return pd.DataFrame(measurements)

    def inject_ntl_at_meter(self, node_name: str, ntl_type: str, ntl_fraction: float):
        """
        Inject NTL by tampering with a specific meter.

        Args:
            node_name: Node/load name
            ntl_type: Type of tampering (halt, reverse, scaling)
            ntl_fraction: Severity of tampering
        """
        if node_name not in self.meter_placement:
            logger.warning(f"No meter at node {node_name}")
            return False
        
        meter_id = self.meter_placement[node_name]
        meter = self.meters[meter_id]
        
        if ntl_type == "meter_tampering":
            meter.inject_tamper("scaling")  # Scale down by ntl_fraction
            meter.measurement_error_factor = (1 - ntl_fraction)
        elif ntl_type == "meter_freezing":
            meter.inject_tamper("halt")
        else:
            logger.warning(f"Unknown tamper type: {ntl_type}")
            return False
        
        logger.info(f"Injected NTL {ntl_type} at {node_name}")
        return True

    def clear_ntl_at_meter(self, node_name: str):
        """Clear NTL tampering at a meter."""
        if node_name in self.meter_placement:
            meter_id = self.meter_placement[node_name]
            self.meters[meter_id].clear_tamper()

    def get_metering_statistics(self) -> Dict:
        """Get statistics about the metering system."""
        smart_count = sum(1 for m in self.meters.values() 
                         if m.characteristics.meter_type == MeterType.SMART_METER)
        legacy_count = sum(1 for m in self.meters.values() 
                          if m.characteristics.meter_type == MeterType.LEGACY_METER)
        
        return {
            'total_meters': len(self.meters),
            'smart_meters': smart_count,
            'legacy_meters': legacy_count,
            'smart_meter_percentage': 100 * smart_count / len(self.meters) if len(self.meters) > 0 else 0,
        }

    def get_data_granularity_summary(self) -> pd.DataFrame:
        """Get summary of data granularity (sampling/reporting intervals) per meter type."""
        data = []
        for meter_id, meter in self.meters.items():
            data.append({
                'Meter_ID': meter_id,
                'Meter_Type': meter.characteristics.meter_type.value,
                'Sampling_Interval_min': meter.characteristics.sampling_interval_minutes,
                'Reporting_Interval_min': meter.characteristics.reporting_interval_minutes,
                'Accuracy_Class': meter.characteristics.accuracy_class,
                'Has_Voltage': meter.characteristics.has_voltage_sensor,
                'Has_Current': meter.characteristics.has_current_sensor,
            })
        return pd.DataFrame(data)
