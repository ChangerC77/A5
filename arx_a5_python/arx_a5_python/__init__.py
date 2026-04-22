import os
import sys
import ctypes

_current_dir = os.path.dirname(os.path.abspath(__file__))


def _find_so_file(root_dir, prefix):
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.startswith(prefix) and filename.endswith('.so'):
                return os.path.join(dirpath, filename)
    return None


def _preload_native_libs(lib_dir):
    for name in sorted(os.listdir(lib_dir)):
        if name.endswith('.so') and not name.startswith(('arx_a5.', 'kinematic_solver.')):
            ctypes.CDLL(os.path.join(lib_dir, name), mode=ctypes.RTLD_GLOBAL)


_lib_dir = os.path.join(_current_dir, 'lib')

if os.path.isdir(_lib_dir):
    if _lib_dir not in sys.path:
        sys.path.insert(0, _lib_dir)
    ld_path = os.environ.get('LD_LIBRARY_PATH', '')
    if _lib_dir not in ld_path.split(os.pathsep):
        os.environ['LD_LIBRARY_PATH'] = _lib_dir + os.pathsep + ld_path

    _preload_native_libs(_lib_dir)

    _so_file = _find_so_file(_lib_dir, 'arx_a5.')
    if _so_file:
        _so_dir = os.path.dirname(_so_file)
        if _so_dir not in sys.path:
            sys.path.insert(0, _so_dir)

    _so_file = _find_so_file(_lib_dir, 'kinematic_solver.')
    if _so_file:
        _so_dir = os.path.dirname(_so_file)
        if _so_dir not in sys.path:
            sys.path.insert(0, _so_dir)

try:
    from .dual_arm import BimanualArm
    from .single_arm import SingleArm
    from .solver import forward_kinematics, inverse_kinematics
except ImportError as e:
    raise ImportError(f"Failed to import modules (ensure .so files are built and in lib/): {e}")
