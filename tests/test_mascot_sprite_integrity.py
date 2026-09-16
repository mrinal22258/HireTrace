import os
import pytest
from scripts.generate_mascot_system import verify_mascot_sprite_integrity

def test_brand_mascot_sprite_integrity():
    path = os.path.join("assets", "brand", "hiretrace_mascot_directions.webp")
    assert os.path.exists(path), f"File {path} does not exist"
    assert verify_mascot_sprite_integrity(path) is True

def test_ui_mascot_sprite_integrity():
    path = os.path.join("ui", "hiretrace_mascot_directions.webp")
    assert os.path.exists(path), f"File {path} does not exist"
    assert verify_mascot_sprite_integrity(path) is True
