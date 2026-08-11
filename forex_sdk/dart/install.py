import sys
import os

def get_safe_path(base, path):
    abs_base = os.path.abspath(base)
    abs_path = os.path.abspath(os.path.join(base, path))
    if not abs_path.startswith(abs_base):
        raise RuntimeError('Path containment violation')
    return abs_path

sys.path.append(get_safe_path(os.getcwd(), '.rokct'))
import sdk_installer_base

if __name__ == '__main__':
    sdk_name = 'forex_sdk'
    sdk_installer_base.install_sdk_files_and_routes(sdk_name)
