from setuptools import setup, find_packages
import os

# Read requirements from requirements.txt
with open("requirements.txt") as f:
    required_packages = [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
    name="deadstream",
    version="0.1.0",
    packages=find_packages(),
    install_requires=required_packages,
    entry_points={
        "console_scripts": [
            "api_server=deadstream.connect_network:main",
            "timemachine=deadstream.main:main",
        ],
    },
)
