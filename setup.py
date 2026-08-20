import sys
from pathlib import Path

from setuptools import find_packages, setup

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from openmontage.product_version import PRODUCT_VERSION

setup(
    name="openmontage",
    version=PRODUCT_VERSION,
    description="AI-Orchestrated Video Production Platform",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.10",
    install_requires=[
        "pyyaml>=6.0",
        "pydantic>=2.0",
        "jsonschema>=4.20",
        "python-dotenv>=1.0",
        "Pillow>=10.0",
        "requests>=2.31",
        "alibabacloud-oss-v2",
        "google-genai>=1.0.0",
        "openai>=2.44.0",
    ],
)
