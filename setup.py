from setuptools import setup

setup(
    name="deadstream",
    version="0.0.0",
    packages=["GD"],
    install_requires=[
        'aiohttp',
        'requests',
        'python-mpv',
        'pickle5'
    ],
    package_data={
        "GD": ["set_breaks.csv"]
    }
)
