"""
GUI Smoke Tests für RoomCurve (ISO 52016-1)
==========================================

Prüft, dass die GUI ohne Fehler startet.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestGUIImports:
    """Tests für GUI-Modul Imports"""
    
    def test_streamlit_import(self):
        """Streamlit ist installiert"""
        pytest.importorskip("streamlit")
        import streamlit as st
        assert st is not None
    
    def test_plotly_import(self):
        """Plotly ist installiert"""
        pytest.importorskip("plotly")
        import plotly.graph_objects as go
        assert go is not None
    
    def test_numpy_import(self):
        """NumPy ist installiert"""
        import numpy as np
        assert np is not None
    
    def test_pandas_import(self):
        """Pandas ist installiert"""
        import pandas as pd
        assert pd is not None


class TestGUIModul:
    """Tests für GUI-Modul selbst"""
    
    def test_app_syntax(self):
        """app.py hat keine Syntaxfehler"""
        gui_path = Path(__file__).parent.parent / "gui" / "app.py"
        
        with open(gui_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        # Kompiliert ohne Fehler
        compile(code, gui_path, 'exec')
    
    def test_konstanten_definiert(self):
        """GUI-Konstanten sind definiert"""
        gui_path = Path(__file__).parent.parent / "gui" / "app.py"
        
        with open(gui_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        # Wichtige Konstanten vorhanden
        assert "U_WERT_PRESETS" in code
        assert "RANDBEDINGUNGEN" in code
        assert "TRY_REGIONEN" in code


class TestGUIKonfiguration:
    """Tests für Streamlit-Konfiguration"""
    
    def test_config_toml_existiert(self, project_root):
        """Streamlit config.toml existiert"""
        config_path = project_root / ".streamlit" / "config.toml"
        assert config_path.exists()
    
    def test_config_toml_lesbar(self, project_root):
        """config.toml ist lesbar"""
        config_path = project_root / ".streamlit" / "config.toml"
        
        with open(config_path, 'r') as f:
            content = f.read()
        
        assert "[theme]" in content or "[server]" in content
