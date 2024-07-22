# Check whether the currently installed packages are the ones specified
# in the `requirements.txt` file.
#
# Exit with code 1 if any of the three is true:
#   - At least one of the currently installed packages has a different
#       version than the one specified in `requirements.txt`.
#   - At least one of the packages in `requirements.txt` is not currently installed.
#   - There is at leas a packages installed that is not in the `requirements.txt`.
#

import sys
import importlib.metadata
from typing import Dict

# Quick lookup of currently installed packages and their versions
current_packages: Dict[str, str] = {}

def normalize_name(name: str) -> str:
    return name.strip().replace('_', '-').lower()

def normalize_version(version: str) -> str:
    return version.strip().lower()

def check_package(req: str) -> bool:
    " Does 'req' (requirements.txt line) match the currently installed packages? "
    # Get the package name and the version
    version = None  # shut linter up
    if req.startswith('-e'):
        # Editable. Just check package name without version.
        if 'egg=' in req:
            project_name = req.split('#egg=')[1]
            check_version = False
        else:
            project_name = req.split('/')[-1]
            check_version = False
    else:
        basics_without_constraints = req.split(';')[0]
        project_name, version = basics_without_constraints.strip().split('==')
        check_version = True

    project_name = normalize_name(project_name)
    version = normalize_version(version)

    if project_name not in current_packages:
        return False
    
    if check_version and current_packages[project_name] != version:
        return False

    return True

def main():
    for dist in importlib.metadata.distributions():
        current_packages[normalize_name(dist.name)] = normalize_version(dist.version)

    with open('requirements.txt') as requirements:
        for req in requirements:
            if not check_package(req.strip()):
                print(f'Requirements do not match for {req}')
                sys.exit(1)

if __name__ == '__main__':
    main()