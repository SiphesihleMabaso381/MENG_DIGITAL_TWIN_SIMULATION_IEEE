"""
Non-Technical Loss (NTL) Injection Module
==========================================
Simulates various types of non-technical losses including electricity theft,
meter tampering, illegal connections, and load manipulation.

Author: MENG Digital Twin Simulation
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from enum import Enum
from dataclasses import dataclass
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NTLType(Enum):
    """Types of Non-Technical Losses."""
    FULL_METER_BYPASS = "full_meter_bypass"
    PARTIAL_METER_BYPASS = "partial_meter_bypass"
    METER_TAMPERING = "meter_tampering"
    ILLEGAL_CONNECTION = "illegal_connection"
    LOAD_MANIPULATION = "load_manipulation"
    METER_FREEZING = "meter_freezing"


@dataclass
class NTLEvent:
    """Represents an NTL event at a specific node."""
    node_name: str
    ntl_type: NTLType
    start_day: int  # Day of year
    start_hour: float  # Hour of day
    duration_hours: float
    intensity_fraction: float  # 0-1, severity of theft
    description: str


class NTLInjectionEngine:
    """
    Injects realistic non-technical loss scenarios into the simulation.
    Supports temporal scheduling of theft events with realistic patterns.
    Also supports South African operational disturbances such as load shedding,
    which should be separated from theft for training and analytics.
    """
    
    def __init__(self, load_manager):
        """
        Initialize NTL injection engine.

        Args:
            load_manager: Reference to HybridGridLoadManager
        """
        self.load_manager = load_manager
        self.ntl_events: List[NTLEvent] = []
        self.operational_events: List[Dict] = []
        self.node_ntl_state: Dict[str, Dict] = {}  # Track active NTL at each node
        
        # Initialize NTL state for all nodes
        for node_name in self.load_manager.node_profiles.keys():
            self.node_ntl_state[node_name] = {
                'active_ntl': None,
                'actual_power_kw': 0,
                'metered_power_kw': 0,
                'ntl_loss_kw': 0,
                'operational_event_type': None,
                'operational_intensity': 0.0,
            }
        
        logger.info("Initialized NTL injection engine")

    def schedule_ntl_event(self, node_name: str, ntl_type: NTLType,
                          start_day: int, start_hour: float,
                          duration_hours: float, intensity: float,
                          description: str = ""):
        """
        Schedule an NTL event.

        Args:
            node_name: Target node
            ntl_type: Type of NTL
            start_day: Start day of year (1-365)
            start_hour: Start hour of day (0-24)
            duration_hours: Duration of event
            intensity: Severity/intensity (0-1)
            description: Optional description
        """
        event = NTLEvent(
            node_name=node_name,
            ntl_type=ntl_type,
            start_day=start_day,
            start_hour=start_hour,
            duration_hours=duration_hours,
            intensity_fraction=intensity,
            description=description or f"{ntl_type.value} at {node_name}"
        )
        
        self.ntl_events.append(event)
        logger.info(f"Scheduled NTL event: {description}")

    def _is_event_active(self, event: NTLEvent, current_day: int, current_hour: float) -> bool:
        """Check if an NTL event is currently active."""
        # Convert event times to total hours from start of year
        event_start_total_hours = (event.start_day - 1) * 24 + event.start_hour
        event_end_total_hours = event_start_total_hours + event.duration_hours
        
        current_total_hours = (current_day - 1) * 24 + current_hour
        
        return event_start_total_hours <= current_total_hours < event_end_total_hours

    def _apply_full_meter_bypass(self, node_name: str, actual_power: Tuple[float, float],
                                intensity: float) -> Tuple[float, float]:
        """
        Apply full meter bypass: load diverted to avoid meter, meter reads zero.
        In the grid, this manifests as lower than expected voltages/losses.
        """
        # Meter reads zero (or reduced based on intensity)
        metered_power = (0, 0)  # Meter sees nothing
        
        # Grid actually supplies the power (unmetered)
        # This is captured in actual load increase
        return metered_power

    def _apply_partial_meter_bypass(self, node_name: str, actual_power: Tuple[float, float],
                                   intensity: float) -> Tuple[float, float]:
        """
        Partial meter bypass: fraction of load diverted.
        intensity=0.3 means 30% bypassed.
        """
        p_actual, q_actual = actual_power
        
        # Fraction bypassed (not metered)
        p_metered = p_actual * (1 - intensity)
        q_metered = q_actual * (1 - intensity)
        
        return (p_metered, q_metered)

    def _apply_meter_tampering(self, node_name: str, actual_power: Tuple[float, float],
                              intensity: float) -> Tuple[float, float]:
        """
        Meter tampering: meter underreports consumption.
        intensity=0.3 means meter reads 30% less.
        """
        p_actual, q_actual = actual_power
        
        # Meter reports less than actual (theft factor)
        underreport_factor = 1 - intensity  # Report (1-intensity) fraction
        p_metered = p_actual * underreport_factor
        q_metered = q_actual * underreport_factor
        
        return (p_metered, q_metered)

    def _apply_illegal_connection(self, node_name: str, actual_power: Tuple[float, float],
                                 intensity: float) -> Tuple[float, float]:
        """
        Illegal connection: unauthorized load added, consuming power without metering.
        intensity=0.5 means 50% additional load consumed.
        """
        p_actual, q_actual = actual_power
        
        # Actual consumption increases (due to illegal load)
        # But metered remains legitimate (no tampering at meter itself)
        # The "actual" already reflects the increased consumption
        # Metered is the same as legitimate consumption
        
        # Return as-is (meter reads actual, but actual is inflated by illegal load)
        return actual_power  # Meter untouched, but actual includes theft

    def _apply_load_manipulation(self, node_name: str, actual_power: Tuple[float, float],
                                intensity: float) -> Tuple[float, float]:
        """
        Load manipulation: temporal shifting or peak clipping to evade detection.
        intensity=0.4 means 40% load reduction/shift at this time.
        """
        p_actual, q_actual = actual_power
        
        # Reduce consumption at this time (shift to off-peak or reduce overall)
        p_metered = p_actual * (1 - intensity * 0.5)  # Reduce but not eliminate
        q_metered = q_actual * (1 - intensity * 0.5)
        
        return (p_metered, q_metered)

    def _apply_meter_freezing(self, node_name: str, actual_power: Tuple[float, float],
                             intensity: float) -> Tuple[float, float]:
        """
        Meter freezing: meter reading halts/pauses periodically.
        intensity=0.2 means 20% of the time meter is frozen.
        """
        # Stochastically freeze the meter (with probability = intensity)
        if np.random.random() < intensity:
            # Meter frozen, reads zero for this interval
            return (0, 0)
        else:
            # Meter operating normally
            return actual_power

    def get_node_power_with_ntl(self, node_name: str, day_of_year: int, 
                               hour: float) -> Dict:
        """
        Get node power considering active NTL events.

        Args:
            node_name: Node name
            day_of_year: Day of year
            hour: Hour of day

        Returns:
            Dict with 'actual_power' (true consumption) and 'metered_power' (meter reading)
        """
        # Get legitimate load
        actual_p, actual_q = self.load_manager.get_loads_at_time(day_of_year, hour)[node_name]
        actual_power = (actual_p, actual_q)
        
        metered_power = actual_power  # Start with legitimate
        ntl_loss = (0, 0)
        active_ntl_type = None
        operational_event_type = None
        operational_intensity = 0.0
        
        # Check which NTL events are active
        for event in self.ntl_events:
            if event.node_name == node_name and self._is_event_active(event, day_of_year, hour):
                active_ntl_type = event.ntl_type
                intensity = event.intensity_fraction
                
                # Apply appropriate NTL transformation
                if event.ntl_type == NTLType.FULL_METER_BYPASS:
                    metered_power = self._apply_full_meter_bypass(node_name, actual_power, intensity)
                elif event.ntl_type == NTLType.PARTIAL_METER_BYPASS:
                    metered_power = self._apply_partial_meter_bypass(node_name, actual_power, intensity)
                elif event.ntl_type == NTLType.METER_TAMPERING:
                    metered_power = self._apply_meter_tampering(node_name, actual_power, intensity)
                elif event.ntl_type == NTLType.ILLEGAL_CONNECTION:
                    # Illegal connection increases physical demand, but meter reads only legitimate load.
                    actual_power = (actual_p * (1 + intensity), actual_q * (1 + intensity))
                    metered_power = (actual_p, actual_q)
                elif event.ntl_type == NTLType.LOAD_MANIPULATION:
                    metered_power = self._apply_load_manipulation(node_name, actual_power, intensity)
                elif event.ntl_type == NTLType.METER_FREEZING:
                    metered_power = self._apply_meter_freezing(node_name, actual_power, intensity)
        
        # Apply South African load-shedding / operational interruptions
        for event in self.operational_events:
            if event['node_name'] == node_name and self._is_operational_event_active(event, day_of_year, hour):
                operational_event_type = event['event_type']
                operational_intensity = event['intensity']
                if event['event_type'] == 'load_shedding':
                    # Customer load is disconnected for the interval. Metered and actual both collapse.
                    metered_power = (0.0, 0.0)
                    actual_power = (0.0, 0.0)
                elif event['event_type'] == 'rotational_outage':
                    metered_power = (actual_power[0] * (1.0 - operational_intensity), actual_power[1] * (1.0 - operational_intensity))
                    actual_power = (actual_power[0] * (1.0 - operational_intensity), actual_power[1] * (1.0 - operational_intensity))
                elif event['event_type'] == 'voltage_sag':
                    sag_factor = 1.0 - operational_intensity
                    metered_power = (actual_power[0] * sag_factor, actual_power[1] * sag_factor)
                elif event['event_type'] == 'feeder_trip':
                    metered_power = (0.0, 0.0)
                    actual_power = (0.0, 0.0)

        # Calculate unaccounted-for energy (NTL loss)
        ntl_loss = (actual_power[0] - metered_power[0], actual_power[1] - metered_power[1])
        
        # Update state
        self.node_ntl_state[node_name]['actual_power_kw'] = actual_power[0]
        self.node_ntl_state[node_name]['metered_power_kw'] = metered_power[0]
        self.node_ntl_state[node_name]['ntl_loss_kw'] = ntl_loss[0]
        self.node_ntl_state[node_name]['active_ntl'] = active_ntl_type
        self.node_ntl_state[node_name]['operational_event_type'] = operational_event_type
        self.node_ntl_state[node_name]['operational_intensity'] = operational_intensity
        
        return {
            'actual_power': actual_power,
            'metered_power': metered_power,
            'ntl_loss': ntl_loss,
            'ntl_type': active_ntl_type,
            'operational_event_type': operational_event_type,
            'operational_intensity': operational_intensity,
        }

    def get_all_nodes_with_ntl(self, day_of_year: int, hour: float) -> Dict[str, Dict]:
        """
        Get power for all nodes considering NTL.

        Returns:
            Dict mapping node_name -> power data (actual, metered, loss)
        """
        result = {}
        for node_name in self.load_manager.node_profiles.keys():
            result[node_name] = self.get_node_power_with_ntl(node_name, day_of_year, hour)
        return result

    def get_ntl_summary(self, day_of_year: int, hour: float) -> Dict:
        """
        Get summary statistics of NTL at current time.

        Returns:
            Dict with total losses, loss percentage, number of affected nodes
        """
        all_data = self.get_all_nodes_with_ntl(day_of_year, hour)
        
        total_actual = sum(d['actual_power'][0] for d in all_data.values())
        total_metered = sum(d['metered_power'][0] for d in all_data.values())
        total_loss = total_actual - total_metered
        
        affected_nodes = sum(1 for d in all_data.values() if d['ntl_type'] is not None)
        
        loss_pct = (total_loss / total_actual * 100) if total_actual > 0 else 0
        
        return {
            'total_actual_kw': total_actual,
            'total_metered_kw': total_metered,
            'total_ntl_loss_kw': total_loss,
            'ntl_percentage': loss_pct,
            'affected_nodes': affected_nodes,
        }

    def get_active_events(self, day_of_year: int, hour: float) -> List[NTLEvent]:
        """Get list of currently active NTL events."""
        active = []
        for event in self.ntl_events:
            if self._is_event_active(event, day_of_year, hour):
                active.append(event)
        return active

    def _is_operational_event_active(self, event: Dict, current_day: int, current_hour: float) -> bool:
        """Check whether a South African operational event is active."""
        event_start_total_hours = (event['start_day'] - 1) * 24 + event['start_hour']
        event_end_total_hours = event_start_total_hours + event['duration_hours']
        current_total_hours = (current_day - 1) * 24 + current_hour
        return event_start_total_hours <= current_total_hours < event_end_total_hours

    def export_event_schedule(self) -> pd.DataFrame:
        """
        Export NTL event schedule as DataFrame.

        Returns:
            DataFrame with all scheduled events
        """
        data = []
        for event in self.ntl_events:
            data.append({
                'Node': event.node_name,
                'NTL_Type': event.ntl_type.value,
                'Start_Day': event.start_day,
                'Start_Hour': event.start_hour,
                'Duration_Hours': event.duration_hours,
                'Intensity': event.intensity_fraction,
                'Description': event.description,
            })
        for event in self.operational_events:
            data.append({
                'Node': event['node_name'],
                'NTL_Type': 'operational_event',
                'Start_Day': event['start_day'],
                'Start_Hour': event['start_hour'],
                'Duration_Hours': event['duration_hours'],
                'Intensity': event['intensity'],
                'Description': event['description'],
            })
        return pd.DataFrame(data)

    def schedule_operational_event(self, node_name: str, event_type: str,
                                  start_day: int, start_hour: float,
                                  duration_hours: float, intensity: float,
                                  description: str = ""):
        """Schedule a non-theft operational event such as load shedding or outage."""
        self.operational_events.append({
            'node_name': node_name,
            'event_type': event_type,
            'start_day': start_day,
            'start_hour': start_hour,
            'duration_hours': duration_hours,
            'intensity': float(intensity),
            'description': description or f"{event_type} at {node_name}",
        })

    def generate_south_africa_load_shedding_scenarios(
        self,
        sim_duration_days: int = 30,
        stage: Optional[int] = None,
        affected_nodes: Optional[List[str]] = None,
        include_all_stages: bool = False,
    ) -> List[Dict]:
        """Generate South African load-shedding schedules separate from theft.

        By default this generates a single stage-based event. When include_all_stages=True,
        it creates a small representative schedule covering stages 1 through 8.
        """
        if affected_nodes is None:
            affected_nodes = list(self.load_manager.node_profiles.keys())

        if stage is None:
            stage = 4

        valid_stages = [1, 2, 3, 4, 5, 6, 7, 8]
        if stage not in valid_stages:
            stage = 4

        generated_events = []
        for node in affected_nodes:
            if include_all_stages:
                for current_stage in valid_stages:
                    start_day = 1 + (current_stage - 1) % max(1, sim_duration_days)
                    start_hour = float((current_stage - 1) * 2)
                    duration = float(np.random.uniform(1.0, 4.0))
                    intensity = float(np.random.uniform(0.35, 0.95)) if current_stage >= 4 else float(np.random.uniform(0.15, 0.55))
                    event_type = "load_shedding"
                    description = f"South Africa {event_type} stage {current_stage} at {node}"
                    event = {
                        'node_name': node,
                        'event_type': event_type,
                        'stage': current_stage,
                        'start_day': start_day,
                        'start_hour': start_hour,
                        'duration_hours': duration,
                        'intensity': intensity,
                        'description': description,
                    }
                    self.operational_events.append(event)
                    generated_events.append(event)
            else:
                start_day = 1
                start_hour = 0.0
                duration = float(np.random.uniform(1.0, 6.0))
                intensity = float(np.random.uniform(0.35, 0.95)) if stage >= 4 else float(np.random.uniform(0.15, 0.55))
                event_type = "load_shedding"
                description = f"South Africa {event_type} stage {stage} at {node}"
                event = {
                    'node_name': node,
                    'event_type': event_type,
                    'stage': stage,
                    'start_day': start_day,
                    'start_hour': start_hour,
                    'duration_hours': duration,
                    'intensity': intensity,
                    'description': description,
                }
                self.operational_events.append(event)
                generated_events.append(event)

        logger.info(
            f"Generated {len(generated_events)} South African operational outage events "
            f"({'all stages' if include_all_stages else f'stage {stage}'})"
        )
        return generated_events

    def generate_realistic_theft_scenarios(
        self,
        num_theft_nodes: int = 3,
        theft_nodes: Optional[List[str]] = None,
        sim_duration_days: int = 30,
        realism_profile: str = "utility",
    ) -> List[NTLEvent]:
        """
        Generate realistic theft scenarios (stochastic, seasonal, adaptive patterns).

        Args:
            num_theft_nodes: Number of nodes with theft
            sim_duration_days: Simulation duration

        Returns:
            List of generated NTL events
        """
        available_nodes = sorted(list(self.load_manager.node_profiles.keys()))
        if not available_nodes:
            return []

        if theft_nodes is None:
            selected_nodes = np.random.choice(
                available_nodes,
                min(max(num_theft_nodes, 0), len(available_nodes)),
                replace=False,
            ).tolist()
        else:
            selected_nodes = [n for n in theft_nodes if n in set(available_nodes)]
        
        generated_events = []
        
        profile_settings = {
            "benchmark": {
                "type_weights": [0.45, 0.35, 0.15, 0.05],
                "events_per_node_low": 1,
                "events_per_node_high": 3,
                "intensity_low": 0.15,
                "intensity_high": 0.45,
                "duration_low": 1.0,
                "duration_high": 6.0,
            },
            "utility": {
                "type_weights": [0.35, 0.30, 0.20, 0.15],
                "events_per_node_low": 2,
                "events_per_node_high": 7,
                "intensity_low": 0.20,
                "intensity_high": 0.65,
                "duration_low": 0.5,
                "duration_high": 12.0,
            },
            "stressed": {
                "type_weights": [0.25, 0.25, 0.30, 0.20],
                "events_per_node_low": 2,
                "events_per_node_high": 8,
                "intensity_low": 0.20,
                "intensity_high": 0.70,
                "duration_low": 1.0,
                "duration_high": 16.0,
            },
        }
        cfg = profile_settings.get(realism_profile, profile_settings["utility"])

        ntl_type_pool = [
            NTLType.PARTIAL_METER_BYPASS,
            NTLType.METER_TAMPERING,
            NTLType.ILLEGAL_CONNECTION,
            NTLType.METER_FREEZING,
        ]

        for node in selected_nodes:
            num_events_per_node = int(
                np.random.randint(cfg["events_per_node_low"], cfg["events_per_node_high"] + 1)
            )

            for _ in range(num_events_per_node):
                theft_type = np.random.choice(ntl_type_pool, p=cfg["type_weights"])

                start_day = int(np.random.randint(1, max(sim_duration_days, 1) + 1))

                # Theft tends to cluster in evening/night, with some daytime activity.
                hour_bucket = np.random.choice(["night", "evening", "day"], p=[0.40, 0.40, 0.20])
                if hour_bucket == "night":
                    start_hour = float(np.random.uniform(0, 6))
                elif hour_bucket == "evening":
                    start_hour = float(np.random.uniform(17, 24))
                else:
                    start_hour = float(np.random.uniform(8, 17))

                duration = float(np.random.uniform(cfg["duration_low"], cfg["duration_high"]))
                intensity = float(np.random.uniform(cfg["intensity_low"], cfg["intensity_high"]))

                event = NTLEvent(
                    node_name=node,
                    ntl_type=theft_type,
                    start_day=start_day,
                    start_hour=start_hour,
                    duration_hours=duration,
                    intensity_fraction=intensity,
                    description=(
                        f"{realism_profile} realistic {theft_type.value} at {node} "
                        f"(day {start_day}, {start_hour:.2f}h)"
                    ),
                )

                generated_events.append(event)
                self.schedule_ntl_event(
                    node_name=event.node_name,
                    ntl_type=event.ntl_type,
                    start_day=event.start_day,
                    start_hour=event.start_hour,
                    duration_hours=event.duration_hours,
                    intensity=event.intensity_fraction,
                    description=event.description,
                )
        
        logger.info(f"Generated {len(generated_events)} realistic theft events")
        return generated_events
