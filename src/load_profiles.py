"""
Load Profiles Module
====================
Generates and manages realistic electricity consumption profiles for different
customer types (residential, commercial, industrial) based on real-world patterns
and OpenEI datasets.

Author: MENG Digital Twin Simulation
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Callable
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CustomerType(Enum):
    """Customer/Load classification."""
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"
    AGRICULTURAL = "agricultural"


class LoadProfileGenerator:
    """
    Generates realistic electricity load profiles based on customer type,
    time of day, day of week, and seasonal variations.
    """
    
    # Normalized baseline consumption patterns (0-1 scale)
    # Based on typical OpenEI and utility data
    RESIDENTIAL_DAILY_PROFILE = np.array([
        0.35, 0.30, 0.28, 0.27, 0.25, 0.30, 0.45, 0.65,  # 00-08
        0.60, 0.50, 0.40, 0.35, 0.40, 0.38, 0.42, 0.52,  # 08-16
        0.65, 0.78, 0.85, 0.92, 0.90, 0.88, 0.75, 0.55,  # 16-00
    ])
    
    COMMERCIAL_DAILY_PROFILE = np.array([
        0.20, 0.15, 0.10, 0.08, 0.10, 0.15, 0.25, 0.50,  # 00-08
        0.80, 0.95, 1.00, 0.98, 0.90, 0.92, 0.95, 0.98,  # 08-16
        0.92, 0.85, 0.60, 0.40, 0.30, 0.25, 0.20, 0.15,  # 16-00
    ])
    
    INDUSTRIAL_DAILY_PROFILE = np.array([
        0.60, 0.55, 0.50, 0.50, 0.55, 0.70, 0.85, 0.95,  # 00-08
        1.00, 1.00, 1.00, 1.00, 0.95, 0.98, 1.00, 0.98,  # 08-16
        0.92, 0.85, 0.80, 0.75, 0.70, 0.65, 0.62, 0.60,  # 16-00
    ])
    
    # Day-of-week factors (Monday-Sunday)
    DOW_FACTORS = np.array([1.00, 1.02, 1.05, 1.08, 1.10, 0.85, 0.75])
    
    # Seasonal factors (based on day of year)
    # Peak in summer (cooling) and winter (heating)
    SEASONAL_PEAK_DAYS = [15, 200]  # Mid-Jan (winter), mid-July (summer)
    SEASONAL_MIN_DAY = 100  # Mid-April (spring minimum)
    
    def __init__(self, customer_type: CustomerType = CustomerType.RESIDENTIAL,
                 annual_consumption_kwh: float = 4000):
        """
        Initialize load profile generator.

        Args:
            customer_type: Type of customer (residential, commercial, industrial)
            annual_consumption_kwh: Expected annual consumption for scaling
        """
        self.customer_type = customer_type
        self.annual_consumption_kwh = annual_consumption_kwh
        self._compute_scaling_factor()
        
    def _compute_scaling_factor(self):
        """Compute scaling factor based on annual consumption."""
        # Get baseline daily profile
        baseline = self._get_baseline_profile()
        
        # Estimate daily consumption from profile (peak power × profile integral)
        daily_profile_integral = np.sum(baseline) / len(baseline)  # Average factor
        
        # Assume peak load is baseline_peak_kw
        if self.customer_type == CustomerType.RESIDENTIAL:
            peak_kw = 8.0  # Typical residential peak
        elif self.customer_type == CustomerType.COMMERCIAL:
            peak_kw = 50.0  # Typical commercial peak
        else:
            peak_kw = 200.0  # Typical industrial peak
        
        # Daily consumption from profile
        estimated_daily_kwh = peak_kw * daily_profile_integral * 24
        
        # Scale to match annual consumption
        self.scaling_factor = (self.annual_consumption_kwh / 365) / estimated_daily_kwh
        
    def _get_baseline_profile(self) -> np.ndarray:
        """Get baseline hourly profile for customer type."""
        if self.customer_type == CustomerType.RESIDENTIAL:
            return self.RESIDENTIAL_DAILY_PROFILE
        elif self.customer_type == CustomerType.COMMERCIAL:
            return self.COMMERCIAL_DAILY_PROFILE
        elif self.customer_type == CustomerType.INDUSTRIAL:
            return self.INDUSTRIAL_DAILY_PROFILE
        else:
            # Agricultural - similar to industrial
            return self.INDUSTRIAL_DAILY_PROFILE

    def _get_dow_factor(self, day_of_year: int) -> float:
        """Get day-of-week factor (Monday=0, Sunday=6)."""
        # Jan 1, 2024 was a Monday
        dow = (day_of_year - 1) % 7
        return self.DOW_FACTORS[dow]

    def _get_seasonal_factor(self, day_of_year: int) -> float:
        """Get seasonal factor (peaks in winter and summer)."""
        # Assume sinusoidal seasonal variation
        # Peaks on day 15 (winter) and day 200 (summer)
        # Min on day 100 (spring)
        
        # Simple model: blend of two cosines for double-peak
        winter_phase = (day_of_year - self.SEASONAL_PEAK_DAYS[0]) * 2 * np.pi / 365
        summer_phase = (day_of_year - self.SEASONAL_PEAK_DAYS[1]) * 2 * np.pi / 365
        
        winter_component = 0.5 * (1 + np.cos(winter_phase))  # Peak at day 15
        summer_component = 0.5 * (1 + np.cos(summer_phase))  # Peak at day 200
        
        seasonal = 0.7 + 0.3 * (winter_component + summer_component) / 2
        return seasonal

    def get_hourly_profile(self, day_of_year: int) -> np.ndarray:
        """
        Get hourly load profile (24 hours) for a specific day.

        Args:
            day_of_year: Day number (1-365)

        Returns:
            Array of 24 hourly load factors (0-1 scale)
        """
        baseline = self._get_baseline_profile()
        dow_factor = self._get_dow_factor(day_of_year)
        seasonal_factor = self._get_seasonal_factor(day_of_year)
        
        # Combine all factors
        profile = baseline * dow_factor * seasonal_factor * self.scaling_factor
        
        return profile

    def get_15min_profile(self, day_of_year: int, stochasticity: float = 0.05) -> np.ndarray:
        """
        Get 15-minute resolution profile for a day (96 points).

        Args:
            day_of_year: Day number (1-365)
            stochasticity: Random variation factor (0-1)

        Returns:
            Array of 96 15-minute load factors
        """
        hourly = self.get_hourly_profile(day_of_year)
        
        # Interpolate to 15-minute resolution (simple repeat each hour 4x)
        profile_15min = np.repeat(hourly, 4)
        
        # Add realistic randomness (appliance usage variability)
        if stochasticity > 0:
            noise = np.random.normal(1.0, stochasticity, len(profile_15min))
            profile_15min *= noise
            # Clip to non-negative
            profile_15min = np.maximum(profile_15min, 0)
        
        return profile_15min

    def get_power_kw(self, day_of_year: int, hour: float, 
                     peak_power_kw: Optional[float] = None) -> float:
        """
        Get instantaneous power (kW) at specific time.

        Args:
            day_of_year: Day number (1-365)
            hour: Hour of day (0-24)
            peak_power_kw: Peak power rating (if None, use default for customer type)

        Returns:
            Power in kW
        """
        if peak_power_kw is None:
            if self.customer_type == CustomerType.RESIDENTIAL:
                peak_power_kw = 8.0
            elif self.customer_type == CustomerType.COMMERCIAL:
                peak_power_kw = 50.0
            else:
                peak_power_kw = 200.0
        
        # Get hourly profile
        hourly_profile = self.get_hourly_profile(day_of_year)
        
        # Interpolate for sub-hour
        hour_idx = int(hour) % 24
        next_hour_idx = (hour_idx + 1) % 24
        
        frac = hour - int(hour)
        profile_at_time = (hourly_profile[hour_idx] * (1 - frac) + 
                          hourly_profile[next_hour_idx] * frac)
        
        power_kw = peak_power_kw * profile_at_time
        
        return power_kw


class NodeLoadProfile:
    """
    Container for a specific node's load profile and consumption data.
    Manages time-series consumption for a single load node.
    """
    
    def __init__(self, node_name: str, customer_type: CustomerType,
                 annual_consumption_kwh: float, power_factor: float = 0.95):
        """
        Initialize node load profile.

        Args:
            node_name: Name of the load/node
            customer_type: Type of customer
            annual_consumption_kwh: Expected annual consumption
            power_factor: Power factor (default 0.95)
        """
        self.node_name = node_name
        self.customer_type = customer_type
        self.annual_consumption_kwh = annual_consumption_kwh
        self.power_factor = power_factor
        
        self.generator = LoadProfileGenerator(customer_type, annual_consumption_kwh)
        
    def get_power_at_time(self, day_of_year: int, hour: float) -> Tuple[float, float]:
        """
        Get P and Q power at specific time.

        Returns:
            Tuple of (P_kW, Q_kVAr)
        """
        p_kw = self.generator.get_power_kw(day_of_year, hour)
        
        # Calculate reactive power from power factor
        q_kvar = p_kw * np.tan(np.arccos(self.power_factor))
        
        return p_kw, q_kvar


class HybridGridLoadManager:
    """
    Manages load profiles for all nodes in a hybrid grid.
    Provides centralized load generation and management.
    """
    
    def __init__(self):
        """Initialize load manager."""
        self.node_profiles: Dict[str, NodeLoadProfile] = {}
        self.load_data_cache: Dict[int, pd.DataFrame] = {}  # Cache by day_of_year
        
    def add_load_node(self, node_name: str, customer_type: CustomerType,
                     annual_consumption_kwh: float):
        """
        Add a load node to the system.

        Args:
            node_name: Name of the node
            customer_type: Type of customer
            annual_consumption_kwh: Annual consumption
        """
        profile = NodeLoadProfile(node_name, customer_type, annual_consumption_kwh)
        self.node_profiles[node_name] = profile
        logger.debug(f"Added load node {node_name} ({customer_type.value})")
        
    def add_load_nodes_bulk(self, node_list: List[Tuple[str, CustomerType, float]]):
        """
        Add multiple load nodes at once.

        Args:
            node_list: List of (node_name, customer_type, annual_kwh) tuples
        """
        for node_name, cust_type, annual_kwh in node_list:
            self.add_load_node(node_name, cust_type, annual_kwh)
        logger.info(f"Added {len(node_list)} load nodes")

    def get_loads_at_time(self, day_of_year: int, hour: float) -> Dict[str, Tuple[float, float]]:
        """
        Get all node loads (P, Q) at a specific time.

        Args:
            day_of_year: Day number (1-365)
            hour: Hour of day (0-24)

        Returns:
            Dict mapping node_name -> (P_kW, Q_kVAr)
        """
        loads = {}
        
        for node_name, profile in self.node_profiles.items():
            p_kw, q_kvar = profile.get_power_at_time(day_of_year, hour)
            loads[node_name] = (p_kw, q_kvar)
        
        return loads

    def generate_daily_profiles(self, day_of_year: int, 
                               resolution_minutes: int = 15) -> pd.DataFrame:
        """
        Generate full day load profiles for all nodes.

        Args:
            day_of_year: Day number (1-365)
            resolution_minutes: Time resolution (15 or 60 minutes)

        Returns:
            DataFrame with columns: Timestamp, Node, P_kW, Q_kVAr
        """
        num_steps = int(24 * 60 / resolution_minutes)
        data = []
        
        for step in range(num_steps):
            hour = step * (resolution_minutes / 60.0)
            loads = self.get_loads_at_time(day_of_year, hour)
            
            for node_name, (p_kw, q_kvar) in loads.items():
                data.append({
                    'Day': day_of_year,
                    'Hour': hour,
                    'Timestamp_minutes': step * resolution_minutes,
                    'Node': node_name,
                    'P_kW': p_kw,
                    'Q_kVAr': q_kvar,
                })
        
        return pd.DataFrame(data)

    def export_loadshape_for_opendss(self, node_name: str, day_of_year: int,
                                    resolution_minutes: int = 15) -> Dict:
        """
        Export load profile in OpenDSS LoadShape format.

        Args:
            node_name: Name of node
            day_of_year: Day number
            resolution_minutes: Time resolution

        Returns:
            Dict with OpenDSS LoadShape definition
        """
        if node_name not in self.node_profiles:
            logger.warning(f"Node {node_name} not found")
            return {}
        
        profile = self.node_profiles[node_name]
        num_steps = int(24 * 60 / resolution_minutes)
        
        multipliers = []
        hours = []
        
        for step in range(num_steps):
            hour = step * (resolution_minutes / 60.0)
            p_kw, _ = profile.get_power_at_time(day_of_year, hour)
            
            # Normalize to average
            avg_power = profile.annual_consumption_kwh * 1000 / (365 * 24)  # Average W
            multiplier = (p_kw * 1000) / avg_power if avg_power > 0 else 0
            
            multipliers.append(multiplier)
            hours.append(hour)
        
        return {
            'node': node_name,
            'npts': num_steps,
            'interval': resolution_minutes / 60.0,
            'multipliers': multipliers,
            'hours': hours,
        }
