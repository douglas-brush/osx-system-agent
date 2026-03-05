from osx_system_agent.scanners.aging import scan_aging
from osx_system_agent.scanners.brew import scan_brew
from osx_system_agent.scanners.caches import scan_caches
from osx_system_agent.scanners.disk_hogs import scan_disk_hogs
from osx_system_agent.scanners.disk_usage import scan_disk_usage
from osx_system_agent.scanners.docker import scan_docker
from osx_system_agent.scanners.duplicates import scan_duplicates
from osx_system_agent.scanners.google_drive import scan_google_drive
from osx_system_agent.scanners.inventory import scan_inventory
from osx_system_agent.scanners.junk import scan_junk
from osx_system_agent.scanners.launch_agents import scan_launch_agents
from osx_system_agent.scanners.login_items import scan_login_items
from osx_system_agent.scanners.network import scan_network
from osx_system_agent.scanners.security import scan_security
from osx_system_agent.scanners.xcode import scan_xcode

__all__ = [
    "scan_aging",
    "scan_brew",
    "scan_caches",
    "scan_disk_hogs",
    "scan_disk_usage",
    "scan_docker",
    "scan_duplicates",
    "scan_google_drive",
    "scan_inventory",
    "scan_junk",
    "scan_launch_agents",
    "scan_login_items",
    "scan_network",
    "scan_security",
    "scan_xcode",
]
