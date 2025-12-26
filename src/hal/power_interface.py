"""
Power Management Hardware Abstraction Layer
Platform-independent interface for power management operations

Features:
- Battery monitoring
- Power state management (sleep, hibernate, shutdown)
- CPU frequency scaling
- Power consumption monitoring
- Wake-on-LAN support

Author: Neural Lens Development Team
Date: January 4, 2026
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import subprocess


class PowerState(Enum):
    """System power states"""
    ACTIVE = "active"
    IDLE = "idle"
    SLEEP = "sleep"
    HIBERNATE = "hibernate"
    SHUTDOWN = "shutdown"


class PowerSource(Enum):
    """Power source types"""
    BATTERY = "battery"
    AC = "ac"
    UNKNOWN = "unknown"


class BatteryStatus(Enum):
    """Battery status"""
    CHARGING = "charging"
    DISCHARGING = "discharging"
    FULL = "full"
    NOT_CHARGING = "not_charging"
    UNKNOWN = "unknown"


@dataclass
class BatteryInfo:
    """Battery information"""
    present: bool
    status: BatteryStatus
    capacity: int  # Percentage (0-100)
    voltage: float  # Volts
    current: float  # Amperes
    power: float  # Watts
    time_remaining: Optional[timedelta] = None  # Time to empty/full


@dataclass
class PowerInfo:
    """Power management information"""
    power_source: PowerSource
    power_state: PowerState
    battery: Optional[BatteryInfo]
    cpu_frequency: float  # MHz
    temperature: float  # Celsius


class PowerInterface(ABC):
    """Abstract interface for power management"""
    
    @abstractmethod
    def get_power_info(self) -> PowerInfo:
        """Get current power status"""
        pass
    
    @abstractmethod
    def get_battery_info(self) -> Optional[BatteryInfo]:
        """Get battery information"""
        pass
    
    @abstractmethod
    def set_power_state(self, state: PowerState) -> bool:
        """Set system power state"""
        pass
    
    @abstractmethod
    def set_cpu_frequency(self, frequency: str) -> bool:
        """
        Set CPU frequency scaling governor
        
        Args:
            frequency: Governor mode (powersave, performance, ondemand, conservative)
        """
        pass
    
    @abstractmethod
    def get_power_consumption(self) -> float:
        """Get current power consumption in watts"""
        pass
    
    @abstractmethod
    def enable_wake_on_lan(self, interface: str) -> bool:
        """Enable Wake-on-LAN for network interface"""
        pass


class LinuxPower(PowerInterface):
    """Linux power management implementation"""
    
    BATTERY_PATH = "/sys/class/power_supply/BAT0"
    CPU_FREQ_PATH = "/sys/devices/system/cpu/cpu0/cpufreq"
    
    def __init__(self):
        """Initialize Linux power management"""
        self.logger = logging.getLogger(__name__)
        self.logger.info("Linux power management initialized")
    
    def get_power_info(self) -> PowerInfo:
        """Get comprehensive power information"""
        battery = self.get_battery_info()
        
        # Determine power source
        power_source = PowerSource.UNKNOWN
        if battery:
            if battery.status == BatteryStatus.CHARGING:
                power_source = PowerSource.AC
            else:
                power_source = PowerSource.BATTERY
        else:
            power_source = PowerSource.AC
        
        # Get CPU frequency
        cpu_freq = self._get_cpu_frequency()
        
        # Get temperature
        temp = self._get_temperature()
        
        return PowerInfo(
            power_source=power_source,
            power_state=PowerState.ACTIVE,
            battery=battery,
            cpu_frequency=cpu_freq,
            temperature=temp
        )
    
    def get_battery_info(self) -> Optional[BatteryInfo]:
        """Get battery information from sysfs"""
        try:
            from pathlib import Path
            battery_path = Path(self.BATTERY_PATH)
            
            if not battery_path.exists():
                return None
            
            # Read battery properties
            def read_value(filename: str, default: Any = 0):
                try:
                    return (battery_path / filename).read_text().strip()
                except FileNotFoundError:
                    return default
            
            status_str = read_value('status', 'Unknown').lower()
            status_map = {
                'charging': BatteryStatus.CHARGING,
                'discharging': BatteryStatus.DISCHARGING,
                'full': BatteryStatus.FULL,
                'not charging': BatteryStatus.NOT_CHARGING
            }
            status = status_map.get(status_str, BatteryStatus.UNKNOWN)
            
            capacity = int(read_value('capacity', '0'))
            
            # Voltage in microvolts
            voltage_uv = int(read_value('voltage_now', '0'))
            voltage = voltage_uv / 1_000_000.0
            
            # Current in microamperes
            current_ua = int(read_value('current_now', '0'))
            current = current_ua / 1_000_000.0
            
            # Power in microwatts
            power_uw = int(read_value('power_now', '0'))
            if power_uw == 0 and voltage > 0 and current > 0:
                power_uw = voltage_uv * current_ua / 1_000_000
            power = power_uw / 1_000_000.0
            
            # Calculate time remaining
            time_remaining = None
            if power > 0:
                if status == BatteryStatus.DISCHARGING:
                    # Estimate time to empty
                    energy_now = int(read_value('energy_now', '0'))
                    if energy_now > 0:
                        hours = (energy_now / 1_000_000.0) / power
                        time_remaining = timedelta(hours=hours)
                elif status == BatteryStatus.CHARGING:
                    # Estimate time to full
                    energy_now = int(read_value('energy_now', '0'))
                    energy_full = int(read_value('energy_full', '0'))
                    if energy_full > energy_now:
                        hours = ((energy_full - energy_now) / 1_000_000.0) / power
                        time_remaining = timedelta(hours=hours)
            
            return BatteryInfo(
                present=True,
                status=status,
                capacity=capacity,
                voltage=voltage,
                current=current,
                power=power,
                time_remaining=time_remaining
            )
            
        except Exception as e:
            self.logger.error(f"Failed to get battery info: {e}")
            return None
    
    def _get_cpu_frequency(self) -> float:
        """Get current CPU frequency in MHz"""
        try:
            from pathlib import Path
            freq_file = Path(self.CPU_FREQ_PATH) / "scaling_cur_freq"
            if freq_file.exists():
                freq_khz = int(freq_file.read_text().strip())
                return freq_khz / 1000.0
        except Exception:
            pass
        return 0.0
    
    def _get_temperature(self) -> float:
        """Get CPU temperature in Celsius"""
        try:
            from pathlib import Path
            # Try different thermal zones
            for zone in range(10):
                temp_file = Path(f"/sys/class/thermal/thermal_zone{zone}/temp")
                if temp_file.exists():
                    temp_millic = int(temp_file.read_text().strip())
                    return temp_millic / 1000.0
        except Exception:
            pass
        return 0.0
    
    def set_power_state(self, state: PowerState) -> bool:
        """Set system power state"""
        try:
            if state == PowerState.SLEEP:
                subprocess.run(['systemctl', 'suspend'], check=True)
            elif state == PowerState.HIBERNATE:
                subprocess.run(['systemctl', 'hibernate'], check=True)
            elif state == PowerState.SHUTDOWN:
                subprocess.run(['systemctl', 'poweroff'], check=True)
            else:
                self.logger.warning(f"Unsupported power state: {state}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to set power state: {e}")
            return False
    
    def set_cpu_frequency(self, frequency: str) -> bool:
        """Set CPU frequency governor"""
        try:
            from pathlib import Path
            import glob
            
            governor_file_pattern = "/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"
            governor_files = glob.glob(governor_file_pattern)
            
            if not governor_files:
                self.logger.error("CPU frequency scaling not supported")
                return False
            
            for governor_file in governor_files:
                Path(governor_file).write_text(frequency)
            
            self.logger.info(f"CPU frequency governor set to: {frequency}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to set CPU frequency: {e}")
            return False
    
    def get_power_consumption(self) -> float:
        """Get current power consumption"""
        battery = self.get_battery_info()
        if battery:
            return battery.power
        return 0.0
    
    def enable_wake_on_lan(self, interface: str) -> bool:
        """Enable Wake-on-LAN"""
        try:
            subprocess.run(['ethtool', '-s', interface, 'wol', 'g'], check=True)
            self.logger.info(f"Wake-on-LAN enabled for {interface}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to enable Wake-on-LAN: {e}")
            return False


class MockPower(PowerInterface):
    """Mock power interface for testing"""
    
    def __init__(self):
        """Initialize mock power management"""
        self.logger = logging.getLogger(__name__)
        self.power_state = PowerState.ACTIVE
        self.cpu_governor = "ondemand"
        self.logger.info("Mock power management initialized")
    
    def get_power_info(self) -> PowerInfo:
        battery = self.get_battery_info()
        
        return PowerInfo(
            power_source=PowerSource.AC,
            power_state=self.power_state,
            battery=battery,
            cpu_frequency=1800.0,
            temperature=45.0
        )
    
    def get_battery_info(self) -> Optional[BatteryInfo]:
        return BatteryInfo(
            present=True,
            status=BatteryStatus.DISCHARGING,
            capacity=75,
            voltage=12.6,
            current=2.5,
            power=31.5,
            time_remaining=timedelta(hours=3)
        )
    
    def set_power_state(self, state: PowerState) -> bool:
        self.logger.info(f"Mock: Power state set to {state.value}")
        self.power_state = state
        return True
    
    def set_cpu_frequency(self, frequency: str) -> bool:
        self.logger.info(f"Mock: CPU governor set to {frequency}")
        self.cpu_governor = frequency
        return True
    
    def get_power_consumption(self) -> float:
        return 31.5  # Watts
    
    def enable_wake_on_lan(self, interface: str) -> bool:
        self.logger.info(f"Mock: Wake-on-LAN enabled for {interface}")
        return True


class PowerFactory:
    """Factory for creating power management instances"""
    
    @staticmethod
    def create(platform: str = "linux") -> PowerInterface:
        """
        Create power management instance
        
        Args:
            platform: Platform type (linux, mock)
            
        Returns:
            PowerInterface instance
        """
        platform = platform.lower()
        
        if platform == "linux":
            return LinuxPower()
        elif platform == "mock":
            return MockPower()
        else:
            logging.warning(f"Unknown platform: {platform}, using mock")
            return MockPower()
