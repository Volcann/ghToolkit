import importlib.util
import sys
from pathlib import Path

# Ensure ghtoolkit package resolves to src/ during test discovery
_src_dir = str(Path(__file__).resolve().parent.parent / "src")
if "ghtoolkit" not in sys.modules:
    try:
        import ghtoolkit  # noqa: F401
    except ImportError:
        _spec = importlib.util.spec_from_file_location(
            "ghtoolkit",
            Path(_src_dir) / "__init__.py",
            submodule_search_locations=[_src_dir],
        )
        if _spec and _spec.loader:
            _mod = importlib.util.module_from_spec(_spec)
            sys.modules["ghtoolkit"] = _mod
            _spec.loader.exec_module(_mod)
