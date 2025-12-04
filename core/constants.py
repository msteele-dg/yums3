import os
from enum import Enum

class RepoConfigFiles(Enum):
    SYSTEM = "/etc/dg-repos.conf"
    LOCAL = "./dg-repos.conf"
    USER = os.path.expanduser("~/.dg-repos.conf")

AVAIL_BACKEND_TYPES = [
    "s3",
    "local"
]

DEFAULTS = {
    'backend.type': 's3',
    # Type-specific repo defaults
    'repo.rpm.cache_dir': '~/yum-repo',
    'repo.deb.cache_dir': '~/deb-repo',
    # Shared behavior defaults
    'validation.enabled': True,
    'behavior.confirm': True,
    'behavior.backup': True,
}

class RepoTypes(Enum):
    RPM = "rpm"
    DEB = "deb"
