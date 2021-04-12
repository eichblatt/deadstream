from setuptools import setup

setup(
    name="deadstream",
    version="0.0.2",
    packages=["deadstream"],
    install_requires=[
        'aiohttp',
        'requests',
        'python-mpv',
        'RPi.GPIO',
        'adafruit-blinka',
        'adafruit-circuitpython-rgb-display',
        'pillow',
        'pickle5'
    ],
    package_data={
        "deadstream": ["FreeMono.ttf", "ariallgt.ttf", "DejaVuSansMono-Bold.ttf","set_breaks.csv"]
    }
)
