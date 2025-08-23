import os
import sys
from pathlib import Path
import pytest


def test_logic_modules_importable():
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    
    try:
        from virtughan_qgis.common.common_logic import CommonLogic
        from virtughan_qgis.engine.engine_logic import EngineLogic
        from virtughan_qgis.extractor.extractor_logic import ExtractorLogic
        from virtughan_qgis.tiler.tiler_logic import TilerLogic
        
        assert CommonLogic is not None
        assert EngineLogic is not None
        assert ExtractorLogic is not None
        assert TilerLogic is not None
        
    except ImportError as e:
        if 'qgis' in str(e).lower():
            pytest.skip("QGIS not available in test environment")
        else:
            assert False, f"Logic module import failed: {e}"


# def test_helper_functions():
#     project_root = Path(__file__).parent.parent
#     sys.path.insert(0, str(project_root))
    
#     try:
#         from virtughan_qgis.utils import helpers
#         assert helpers is not None
        
#     except ImportError as e:
#         if 'qgis' in str(e).lower():
#             pytest.skip("QGIS not available in test environment")
#         else:
#             assert False, f"Helper functions import failed: {e}"


def test_processing_provider_import():
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    
    try:
        from virtughan_qgis.processing_provider import VirtuGhanProvider
        
        provider = VirtuGhanProvider()
        assert provider.id() == "virtughan"
        assert provider.name() == "VirtuGhan"
        
    except ImportError as e:
        if 'qgis' in str(e).lower():
            pytest.skip("QGIS not available in test environment")
        else:
            assert False, f"Processing provider import failed: {e}"


def test_main_plugin_class():
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    
    try:
        from virtughan_qgis.main_plugin import VirtuGhanPlugin
        
        assert VirtuGhanPlugin is not None
        assert hasattr(VirtuGhanPlugin, 'initGui')
        assert hasattr(VirtuGhanPlugin, 'unload')
        
    except ImportError as e:
        if 'qgis' in str(e).lower():
            pytest.skip("QGIS not available in test environment")
        else:
            assert False, f"Main plugin class import failed: {e}"


def test_bootstrap_functions():
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    
    try:
        from virtughan_qgis.bootstrap import install_dependencies, check_dependencies
        
        assert callable(install_dependencies)
        assert callable(check_dependencies)
        
    except ImportError as e:
        if 'qgis' in str(e).lower():
            pytest.skip("QGIS not available in test environment")
        else:
            assert False, f"Bootstrap functions import failed: {e}"
