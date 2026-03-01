from osx_system_agent.scanners.aging import scan_aging
from osx_system_agent.scanners.brew import scan_brew
from osx_system_agent.scanners.caches import scan_caches
from osx_system_agent.scanners.disk_hogs import scan_disk_hogs
from osx_system_agent.scanners.duplicates import scan_duplicates
from osx_system_agent.scanners.inventory import scan_inventory
from osx_system_agent.scanners.junk import scan_junk
from osx_system_agent.scanners.launch_agents import scan_launch_agents

__all__ = [
    "scan_aging",
    "scan_brew",
    "scan_caches",
    "scan_disk_hogs",
    "scan_duplicates",
    "scan_inventory",
    "scan_junk",
    "scan_launch_agents",
]
