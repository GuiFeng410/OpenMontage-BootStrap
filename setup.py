from setuptools import find_packages, setup

from openmontage.product_version import PRODUCT_VERSION

setup(
    name="openmontage",
    version=PRODUCT_VERSION,
    description="AI-Orchestrated Video Production Platform",
    packages=find_packages(),
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
