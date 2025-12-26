"""
GPIO (General Purpose Input/Output) Hardware Abstraction Layer
Platform-independent interface for GPIO operations

Supports:
- Raspberry Pi GPIO (RPi.GPIO or gpiozero)
- Jetson Nano GPIO (Jetson.GPIO)
- Linux sysfs GPIO (generic)
- Mock GPIO for testing

Author: Neural Lens Development Team
Date: January 4, 2026
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Callable, Dict, Any
import logging
import time


class PinMode(Enum):
    """GPIO pin modes"""
    INPUT = "input"
    OUTPUT = "output"
    PWM = "pwm"


class PullMode(Enum):
    """Pull resistor modes"""
    OFF = "off"
    UP = "pull_up"
    DOWN = "pull_down"


class Edge(Enum):
    """Interrupt edge detection"""
    RISING = "rising"
    FALLING = "falling"
    BOTH = "both"


class GPIOInterface(ABC):
    """Abstract interface for GPIO operations"""
    
    @abstractmethod
    def setup(self, pin: int, mode: PinMode, pull: PullMode = PullMode.OFF):
        """
        Configure GPIO pin
        
        Args:
            pin: Pin number
            mode: Pin mode (INPUT/OUTPUT/PWM)
            pull: Pull resistor mode
        """
        pass
    
    @abstractmethod
    def cleanup(self, pin: Optional[int] = None):
        """
        Clean up GPIO resources
        
        Args:
            pin: Specific pin to cleanup (None for all pins)
        """
        pass
    
    @abstractmethod
    def read(self, pin: int) -> int:
        """
        Read digital value from pin
        
        Args:
            pin: Pin number
            
        Returns:
            0 or 1
        """
        pass
    
    @abstractmethod
    def write(self, pin: int, value: int):
        """
        Write digital value to pin
        
        Args:
            pin: Pin number
            value: 0 or 1
        """
        pass
    
    @abstractmethod
    def pwm_start(self, pin: int, frequency: float, duty_cycle: float):
        """
        Start PWM output on pin
        
        Args:
            pin: Pin number
            frequency: PWM frequency in Hz
            duty_cycle: Duty cycle (0.0 to 100.0)
        """
        pass
    
    @abstractmethod
    def pwm_stop(self, pin: int):
        """Stop PWM output on pin"""
        pass
    
    @abstractmethod
    def add_event_detect(self, pin: int, edge: Edge, callback: Callable[[int], None], 
                        bouncetime: int = 200):
        """
        Add interrupt callback for pin
        
        Args:
            pin: Pin number
            edge: Edge to detect
            callback: Function to call on event
            bouncetime: Debounce time in milliseconds
        """
        pass
    
    @abstractmethod
    def remove_event_detect(self, pin: int):
        """Remove interrupt callback from pin"""
        pass


class RaspberryPiGPIO(GPIOInterface):
    """GPIO implementation for Raspberry Pi using RPi.GPIO"""
    
    def __init__(self, mode: str = "BCM"):
        """
        Initialize Raspberry Pi GPIO
        
        Args:
            mode: Pin numbering mode (BCM or BOARD)
        """
        try:
            import RPi.GPIO as GPIO
            self.GPIO = GPIO
            
            # Set numbering mode
            if mode.upper() == "BCM":
                self.GPIO.setmode(GPIO.BCM)
            else:
                self.GPIO.setmode(GPIO.BOARD)
            
            # Suppress warnings
            self.GPIO.setwarnings(False)
            
            self.pwm_instances: Dict[int, Any] = {}
            self.logger = logging.getLogger(__name__)
            self.logger.info("Raspberry Pi GPIO initialized")
            
        except ImportError:
            raise RuntimeError("RPi.GPIO library not available")
    
    def setup(self, pin: int, mode: PinMode, pull: PullMode = PullMode.OFF):
        pull_map = {
            PullMode.OFF: self.GPIO.PUD_OFF,
            PullMode.UP: self.GPIO.PUD_UP,
            PullMode.DOWN: self.GPIO.PUD_DOWN
        }
        
        if mode == PinMode.INPUT:
            self.GPIO.setup(pin, self.GPIO.IN, pull_up_down=pull_map[pull])
        elif mode == PinMode.OUTPUT:
            self.GPIO.setup(pin, self.GPIO.OUT)
        elif mode == PinMode.PWM:
            self.GPIO.setup(pin, self.GPIO.OUT)
    
    def cleanup(self, pin: Optional[int] = None):
        if pin:
            self.GPIO.cleanup(pin)
        else:
            self.GPIO.cleanup()
    
    def read(self, pin: int) -> int:
        return self.GPIO.input(pin)
    
    def write(self, pin: int, value: int):
        self.GPIO.output(pin, value)
    
    def pwm_start(self, pin: int, frequency: float, duty_cycle: float):
        if pin in self.pwm_instances:
            self.pwm_instances[pin].stop()
        
        pwm = self.GPIO.PWM(pin, frequency)
        pwm.start(duty_cycle)
        self.pwm_instances[pin] = pwm
    
    def pwm_stop(self, pin: int):
        if pin in self.pwm_instances:
            self.pwm_instances[pin].stop()
            del self.pwm_instances[pin]
    
    def add_event_detect(self, pin: int, edge: Edge, callback: Callable[[int], None],
                        bouncetime: int = 200):
        edge_map = {
            Edge.RISING: self.GPIO.RISING,
            Edge.FALLING: self.GPIO.FALLING,
            Edge.BOTH: self.GPIO.BOTH
        }
        
        self.GPIO.add_event_detect(pin, edge_map[edge], 
                                   callback=callback, bouncetime=bouncetime)
    
    def remove_event_detect(self, pin: int):
        self.GPIO.remove_event_detect(pin)


class JetsonGPIO(GPIOInterface):
    """GPIO implementation for Jetson Nano using Jetson.GPIO"""
    
    def __init__(self, mode: str = "BCM"):
        """Initialize Jetson GPIO"""
        try:
            import Jetson.GPIO as GPIO
            self.GPIO = GPIO
            
            if mode.upper() == "BCM":
                self.GPIO.setmode(GPIO.BCM)
            else:
                self.GPIO.setmode(GPIO.BOARD)
            
            self.GPIO.setwarnings(False)
            self.pwm_instances: Dict[int, Any] = {}
            self.logger = logging.getLogger(__name__)
            self.logger.info("Jetson GPIO initialized")
            
        except ImportError:
            raise RuntimeError("Jetson.GPIO library not available")
    
    def setup(self, pin: int, mode: PinMode, pull: PullMode = PullMode.OFF):
        pull_map = {
            PullMode.OFF: self.GPIO.PUD_OFF,
            PullMode.UP: self.GPIO.PUD_UP,
            PullMode.DOWN: self.GPIO.PUD_DOWN
        }
        
        if mode == PinMode.INPUT:
            self.GPIO.setup(pin, self.GPIO.IN, pull_up_down=pull_map[pull])
        elif mode in [PinMode.OUTPUT, PinMode.PWM]:
            self.GPIO.setup(pin, self.GPIO.OUT)
    
    def cleanup(self, pin: Optional[int] = None):
        if pin:
            self.GPIO.cleanup(pin)
        else:
            self.GPIO.cleanup()
    
    def read(self, pin: int) -> int:
        return self.GPIO.input(pin)
    
    def write(self, pin: int, value: int):
        self.GPIO.output(pin, value)
    
    def pwm_start(self, pin: int, frequency: float, duty_cycle: float):
        if pin in self.pwm_instances:
            self.pwm_instances[pin].stop()
        
        pwm = self.GPIO.PWM(pin, frequency)
        pwm.start(duty_cycle)
        self.pwm_instances[pin] = pwm
    
    def pwm_stop(self, pin: int):
        if pin in self.pwm_instances:
            self.pwm_instances[pin].stop()
            del self.pwm_instances[pin]
    
    def add_event_detect(self, pin: int, edge: Edge, callback: Callable[[int], None],
                        bouncetime: int = 200):
        edge_map = {
            Edge.RISING: self.GPIO.RISING,
            Edge.FALLING: self.GPIO.FALLING,
            Edge.BOTH: self.GPIO.BOTH
        }
        
        self.GPIO.add_event_detect(pin, edge_map[edge],
                                   callback=callback, bouncetime=bouncetime)
    
    def remove_event_detect(self, pin: int):
        self.GPIO.remove_event_detect(pin)


class SysfsGPIO(GPIOInterface):
    """Generic Linux sysfs GPIO implementation"""
    
    GPIO_PATH = "/sys/class/gpio"
    
    def __init__(self):
        """Initialize sysfs GPIO"""
        self.exported_pins: set = set()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Sysfs GPIO initialized")
    
    def _export(self, pin: int):
        """Export GPIO pin"""
        if pin in self.exported_pins:
            return
        
        try:
            with open(f"{self.GPIO_PATH}/export", 'w') as f:
                f.write(str(pin))
            time.sleep(0.1)  # Wait for export
            self.exported_pins.add(pin)
        except Exception as e:
            self.logger.error(f"Failed to export pin {pin}: {e}")
    
    def _unexport(self, pin: int):
        """Unexport GPIO pin"""
        if pin not in self.exported_pins:
            return
        
        try:
            with open(f"{self.GPIO_PATH}/unexport", 'w') as f:
                f.write(str(pin))
            self.exported_pins.remove(pin)
        except Exception as e:
            self.logger.error(f"Failed to unexport pin {pin}: {e}")
    
    def setup(self, pin: int, mode: PinMode, pull: PullMode = PullMode.OFF):
        self._export(pin)
        
        # Set direction
        direction = "in" if mode == PinMode.INPUT else "out"
        with open(f"{self.GPIO_PATH}/gpio{pin}/direction", 'w') as f:
            f.write(direction)
    
    def cleanup(self, pin: Optional[int] = None):
        if pin:
            self._unexport(pin)
        else:
            for p in list(self.exported_pins):
                self._unexport(p)
    
    def read(self, pin: int) -> int:
        with open(f"{self.GPIO_PATH}/gpio{pin}/value", 'r') as f:
            return int(f.read().strip())
    
    def write(self, pin: int, value: int):
        with open(f"{self.GPIO_PATH}/gpio{pin}/value", 'w') as f:
            f.write(str(value))
    
    def pwm_start(self, pin: int, frequency: float, duty_cycle: float):
        self.logger.warning("PWM not supported in sysfs GPIO")
    
    def pwm_stop(self, pin: int):
        pass
    
    def add_event_detect(self, pin: int, edge: Edge, callback: Callable[[int], None],
                        bouncetime: int = 200):
        self.logger.warning("Event detection not supported in sysfs GPIO")
    
    def remove_event_detect(self, pin: int):
        pass


class MockGPIO(GPIOInterface):
    """Mock GPIO for testing without hardware"""
    
    def __init__(self):
        """Initialize mock GPIO"""
        self.pin_states: Dict[int, int] = {}
        self.pin_modes: Dict[int, PinMode] = {}
        self.logger = logging.getLogger(__name__)
        self.logger.info("Mock GPIO initialized")
    
    def setup(self, pin: int, mode: PinMode, pull: PullMode = PullMode.OFF):
        self.pin_modes[pin] = mode
        self.pin_states[pin] = 0
        self.logger.debug(f"Mock GPIO: Setup pin {pin} as {mode.value}")
    
    def cleanup(self, pin: Optional[int] = None):
        if pin:
            self.pin_states.pop(pin, None)
            self.pin_modes.pop(pin, None)
        else:
            self.pin_states.clear()
            self.pin_modes.clear()
    
    def read(self, pin: int) -> int:
        value = self.pin_states.get(pin, 0)
        self.logger.debug(f"Mock GPIO: Read pin {pin} = {value}")
        return value
    
    def write(self, pin: int, value: int):
        self.pin_states[pin] = value
        self.logger.debug(f"Mock GPIO: Write pin {pin} = {value}")
    
    def pwm_start(self, pin: int, frequency: float, duty_cycle: float):
        self.logger.debug(f"Mock GPIO: PWM start pin {pin}, freq={frequency}Hz, duty={duty_cycle}%")
    
    def pwm_stop(self, pin: int):
        self.logger.debug(f"Mock GPIO: PWM stop pin {pin}")
    
    def add_event_detect(self, pin: int, edge: Edge, callback: Callable[[int], None],
                        bouncetime: int = 200):
        self.logger.debug(f"Mock GPIO: Event detect added to pin {pin}")
    
    def remove_event_detect(self, pin: int):
        self.logger.debug(f"Mock GPIO: Event detect removed from pin {pin}")


class GPIOFactory:
    """Factory for creating GPIO instances based on platform"""
    
    @staticmethod
    def create(platform: Optional[str] = None) -> GPIOInterface:
        """
        Create appropriate GPIO instance for platform
        
        Args:
            platform: Platform name (raspberry_pi, jetson, sysfs, mock)
                     Auto-detected if None
        
        Returns:
            GPIOInterface instance
        """
        if platform:
            platform = platform.lower()
        else:
            platform = GPIOFactory._detect_platform()
        
        if platform == "raspberry_pi":
            return RaspberryPiGPIO()
        elif platform == "jetson":
            return JetsonGPIO()
        elif platform == "sysfs":
            return SysfsGPIO()
        elif platform == "mock":
            return MockGPIO()
        else:
            logging.warning(f"Unknown platform: {platform}, using Mock GPIO")
            return MockGPIO()
    
    @staticmethod
    def _detect_platform() -> str:
        """Auto-detect hardware platform"""
        try:
            # Try Raspberry Pi
            import RPi.GPIO
            return "raspberry_pi"
        except ImportError:
            pass
        
        try:
            # Try Jetson
            import Jetson.GPIO
            return "jetson"
        except ImportError:
            pass
        
        # Check for sysfs GPIO
        import os
        if os.path.exists("/sys/class/gpio"):
            return "sysfs"
        
        # Default to mock
        return "mock"
