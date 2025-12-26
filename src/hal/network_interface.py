"""
Network Hardware Abstraction Layer
Platform-independent interface for network operations

Supports:
- Ethernet configuration
- WiFi management
- Network status monitoring
- Connection testing

Author: Neural Lens Development Team
Date: January 4, 2026
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import logging
import subprocess
import socket


class ConnectionType(Enum):
    """Network connection types"""
    ETHERNET = "ethernet"
    WIFI = "wifi"
    CELLULAR = "cellular"
    UNKNOWN = "unknown"


class ConnectionStatus(Enum):
    """Connection status"""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    ERROR = "error"


@dataclass
class NetworkInfo:
    """Network connection information"""
    interface: str
    connection_type: ConnectionType
    status: ConnectionStatus
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    ssid: Optional[str] = None  # WiFi only
    signal_strength: Optional[int] = None  # WiFi only (0-100)
    speed: Optional[int] = None  # Mbps


class NetworkInterface(ABC):
    """Abstract interface for network operations"""
    
    @abstractmethod
    def get_interfaces(self) -> List[str]:
        """Get list of available network interfaces"""
        pass
    
    @abstractmethod
    def get_status(self, interface: str) -> NetworkInfo:
        """Get network status for interface"""
        pass
    
    @abstractmethod
    def connect_ethernet(self, interface: str, dhcp: bool = True,
                        ip: Optional[str] = None, netmask: Optional[str] = None,
                        gateway: Optional[str] = None) -> bool:
        """Configure ethernet connection"""
        pass
    
    @abstractmethod
    def connect_wifi(self, interface: str, ssid: str, password: str) -> bool:
        """Connect to WiFi network"""
        pass
    
    @abstractmethod
    def disconnect(self, interface: str) -> bool:
        """Disconnect network interface"""
        pass
    
    @abstractmethod
    def test_connectivity(self, host: str = "8.8.8.8", timeout: int = 5) -> bool:
        """Test internet connectivity"""
        pass
    
    @abstractmethod
    def scan_wifi(self, interface: str) -> List[Dict[str, Any]]:
        """Scan for available WiFi networks"""
        pass


class LinuxNetwork(NetworkInterface):
    """Linux network implementation using standard tools"""
    
    def __init__(self):
        """Initialize Linux network interface"""
        self.logger = logging.getLogger(__name__)
        self.logger.info("Linux network interface initialized")
    
    def get_interfaces(self) -> List[str]:
        """Get network interfaces using 'ip' command"""
        try:
            result = subprocess.run(['ip', '-o', 'link', 'show'],
                                  capture_output=True, text=True, check=True)
            interfaces = []
            for line in result.stdout.splitlines():
                parts = line.split(':')
                if len(parts) >= 2:
                    interface = parts[1].strip()
                    if interface != 'lo':  # Skip loopback
                        interfaces.append(interface)
            return interfaces
        except Exception as e:
            self.logger.error(f"Failed to get interfaces: {e}")
            return []
    
    def get_status(self, interface: str) -> NetworkInfo:
        """Get network status for interface"""
        try:
            # Get IP address
            ip_result = subprocess.run(['ip', 'addr', 'show', interface],
                                      capture_output=True, text=True)
            
            ip_address = None
            mac_address = None
            
            for line in ip_result.stdout.splitlines():
                if 'inet ' in line:
                    ip_address = line.split()[1].split('/')[0]
                elif 'link/ether' in line:
                    mac_address = line.split()[1]
            
            # Check if interface is up
            status = ConnectionStatus.DISCONNECTED
            if 'UP' in ip_result.stdout:
                if ip_address:
                    status = ConnectionStatus.CONNECTED
                else:
                    status = ConnectionStatus.CONNECTING
            
            # Determine connection type
            connection_type = self._detect_connection_type(interface)
            
            # Get WiFi info if applicable
            ssid = None
            signal_strength = None
            if connection_type == ConnectionType.WIFI:
                ssid, signal_strength = self._get_wifi_info(interface)
            
            return NetworkInfo(
                interface=interface,
                connection_type=connection_type,
                status=status,
                ip_address=ip_address,
                mac_address=mac_address,
                ssid=ssid,
                signal_strength=signal_strength
            )
            
        except Exception as e:
            self.logger.error(f"Failed to get status for {interface}: {e}")
            return NetworkInfo(
                interface=interface,
                connection_type=ConnectionType.UNKNOWN,
                status=ConnectionStatus.ERROR
            )
    
    def _detect_connection_type(self, interface: str) -> ConnectionType:
        """Detect connection type from interface name"""
        if interface.startswith('wl') or interface.startswith('wlan'):
            return ConnectionType.WIFI
        elif interface.startswith('eth') or interface.startswith('en'):
            return ConnectionType.ETHERNET
        elif interface.startswith('wwan') or interface.startswith('ppp'):
            return ConnectionType.CELLULAR
        return ConnectionType.UNKNOWN
    
    def _get_wifi_info(self, interface: str) -> tuple:
        """Get WiFi SSID and signal strength"""
        try:
            # Try using iwconfig first
            result = subprocess.run(['iwconfig', interface],
                                  capture_output=True, text=True)
            
            ssid = None
            signal = None
            
            for line in result.stdout.splitlines():
                if 'ESSID:' in line:
                    ssid = line.split('ESSID:')[1].strip('"')
                elif 'Signal level=' in line:
                    # Parse signal level (e.g., "-50 dBm")
                    signal_str = line.split('Signal level=')[1].split()[0]
                    signal_dbm = int(signal_str)
                    # Convert dBm to percentage (rough approximation)
                    signal = max(0, min(100, 2 * (signal_dbm + 100)))
            
            return ssid, signal
            
        except Exception:
            return None, None
    
    def connect_ethernet(self, interface: str, dhcp: bool = True,
                        ip: Optional[str] = None, netmask: Optional[str] = None,
                        gateway: Optional[str] = None) -> bool:
        """Configure ethernet connection"""
        try:
            # Bring interface up
            subprocess.run(['ip', 'link', 'set', interface, 'up'], check=True)
            
            if dhcp:
                # Use DHCP
                subprocess.run(['dhclient', interface], check=True)
            else:
                # Static IP
                if not all([ip, netmask, gateway]):
                    self.logger.error("IP, netmask, and gateway required for static config")
                    return False
                
                # Set IP address
                cidr = self._netmask_to_cidr(netmask)
                subprocess.run(['ip', 'addr', 'add', f'{ip}/{cidr}', 'dev', interface],
                             check=True)
                
                # Set default gateway
                subprocess.run(['ip', 'route', 'add', 'default', 'via', gateway],
                             check=True)
            
            self.logger.info(f"Ethernet configured: {interface}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to configure ethernet: {e}")
            return False
    
    def connect_wifi(self, interface: str, ssid: str, password: str) -> bool:
        """Connect to WiFi using wpa_supplicant"""
        try:
            # Create wpa_supplicant config
            wpa_config = f"""
network={{
    ssid="{ssid}"
    psk="{password}"
}}
"""
            config_file = f'/tmp/wpa_{interface}.conf'
            with open(config_file, 'w') as f:
                f.write(wpa_config)
            
            # Start wpa_supplicant
            subprocess.run(['wpa_supplicant', '-B', '-i', interface,
                          '-c', config_file], check=True)
            
            # Get IP with DHCP
            subprocess.run(['dhclient', interface], check=True)
            
            self.logger.info(f"WiFi connected: {ssid}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to connect WiFi: {e}")
            return False
    
    def disconnect(self, interface: str) -> bool:
        """Disconnect network interface"""
        try:
            subprocess.run(['ip', 'link', 'set', interface, 'down'], check=True)
            self.logger.info(f"Interface disconnected: {interface}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to disconnect: {e}")
            return False
    
    def test_connectivity(self, host: str = "8.8.8.8", timeout: int = 5) -> bool:
        """Test connectivity by pinging host"""
        try:
            result = subprocess.run(['ping', '-c', '1', '-W', str(timeout), host],
                                  capture_output=True)
            return result.returncode == 0
        except Exception:
            return False
    
    def scan_wifi(self, interface: str) -> List[Dict[str, Any]]:
        """Scan for WiFi networks using iwlist"""
        try:
            result = subprocess.run(['iwlist', interface, 'scan'],
                                  capture_output=True, text=True, check=True)
            
            networks = []
            current_network = {}
            
            for line in result.stdout.splitlines():
                line = line.strip()
                
                if 'Cell' in line and 'Address:' in line:
                    if current_network:
                        networks.append(current_network)
                    current_network = {'bssid': line.split('Address:')[1].strip()}
                
                elif 'ESSID:' in line:
                    current_network['ssid'] = line.split('ESSID:')[1].strip('"')
                
                elif 'Quality=' in line:
                    quality = line.split('Quality=')[1].split()[0]
                    current, maximum = map(int, quality.split('/'))
                    current_network['signal'] = int((current / maximum) * 100)
                
                elif 'Encryption key:' in line:
                    encrypted = line.split(':')[1].strip().lower() == 'on'
                    current_network['encrypted'] = encrypted
            
            if current_network:
                networks.append(current_network)
            
            return networks
            
        except Exception as e:
            self.logger.error(f"Failed to scan WiFi: {e}")
            return []
    
    def _netmask_to_cidr(self, netmask: str) -> int:
        """Convert netmask to CIDR notation"""
        return sum([bin(int(x)).count('1') for x in netmask.split('.')])


class MockNetwork(NetworkInterface):
    """Mock network interface for testing"""
    
    def __init__(self):
        """Initialize mock network"""
        self.logger = logging.getLogger(__name__)
        self.interfaces = ['eth0', 'wlan0']
        self.connections: Dict[str, NetworkInfo] = {
            'eth0': NetworkInfo(
                interface='eth0',
                connection_type=ConnectionType.ETHERNET,
                status=ConnectionStatus.CONNECTED,
                ip_address='192.168.1.100',
                mac_address='00:11:22:33:44:55'
            ),
            'wlan0': NetworkInfo(
                interface='wlan0',
                connection_type=ConnectionType.WIFI,
                status=ConnectionStatus.DISCONNECTED
            )
        }
        self.logger.info("Mock network interface initialized")
    
    def get_interfaces(self) -> List[str]:
        return self.interfaces
    
    def get_status(self, interface: str) -> NetworkInfo:
        return self.connections.get(interface, NetworkInfo(
            interface=interface,
            connection_type=ConnectionType.UNKNOWN,
            status=ConnectionStatus.DISCONNECTED
        ))
    
    def connect_ethernet(self, interface: str, dhcp: bool = True,
                        ip: Optional[str] = None, netmask: Optional[str] = None,
                        gateway: Optional[str] = None) -> bool:
        self.logger.info(f"Mock: Ethernet connected on {interface}")
        if interface in self.connections:
            self.connections[interface].status = ConnectionStatus.CONNECTED
            self.connections[interface].ip_address = ip or "192.168.1.100"
        return True
    
    def connect_wifi(self, interface: str, ssid: str, password: str) -> bool:
        self.logger.info(f"Mock: WiFi connected to {ssid} on {interface}")
        if interface in self.connections:
            self.connections[interface].status = ConnectionStatus.CONNECTED
            self.connections[interface].ssid = ssid
            self.connections[interface].signal_strength = 75
            self.connections[interface].ip_address = "192.168.1.101"
        return True
    
    def disconnect(self, interface: str) -> bool:
        self.logger.info(f"Mock: Disconnected {interface}")
        if interface in self.connections:
            self.connections[interface].status = ConnectionStatus.DISCONNECTED
            self.connections[interface].ip_address = None
        return True
    
    def test_connectivity(self, host: str = "8.8.8.8", timeout: int = 5) -> bool:
        self.logger.info(f"Mock: Testing connectivity to {host}")
        return True
    
    def scan_wifi(self, interface: str) -> List[Dict[str, Any]]:
        return [
            {'ssid': 'TestNetwork1', 'bssid': '00:11:22:33:44:55', 'signal': 80, 'encrypted': True},
            {'ssid': 'TestNetwork2', 'bssid': '00:11:22:33:44:66', 'signal': 60, 'encrypted': True},
            {'ssid': 'OpenNetwork', 'bssid': '00:11:22:33:44:77', 'signal': 50, 'encrypted': False}
        ]


class NetworkFactory:
    """Factory for creating network instances"""
    
    @staticmethod
    def create(platform: str = "linux") -> NetworkInterface:
        """
        Create network interface instance
        
        Args:
            platform: Platform type (linux, mock)
            
        Returns:
            NetworkInterface instance
        """
        platform = platform.lower()
        
        if platform == "linux":
            return LinuxNetwork()
        elif platform == "mock":
            return MockNetwork()
        else:
            logging.warning(f"Unknown platform: {platform}, using mock")
            return MockNetwork()
