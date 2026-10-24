"""
Kiem tra pyproject.toml [project].dependencies khop tung dong voi requirements.txt.

Vercel cai thu vien tu pyproject.toml (uu tien hon requirements.txt), con Dockerfile
va CI cai tu requirements.txt. Neu 2 file lech nhau, ban deploy tren Vercel se khac
ban chay local/CI - lan dau deploy, pyproject rong nen Vercel khong cai gi ca va
moi request deu tra 500.
"""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _requirements() -> list[str]:
    lines = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    reqs = [line.split("#")[0].strip() for line in lines]
    return [r for r in reqs if r]


def test_pyproject_dependencies_match_requirements_txt():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["dependencies"] == _requirements()


def test_runtime_requirements_have_no_heavy_dev_packages():
    # torch/sentence-transformers day bundle Vercel qua gioi han 500 MB
    names = {r.split("==")[0].split("[")[0].lower() for r in _requirements()}
    assert not names & {"torch", "sentence-transformers", "streamlit", "pytest"}
