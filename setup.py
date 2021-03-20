from setuptools import setup

setup(
    name="deadstream",
    version="0.0.0",
    packages=["GD"],
    install_requires=[
        'requests',
        'python-mpv'
        ],
    package_data={
        "GD": ["set_breaks.csv"]
    }
)