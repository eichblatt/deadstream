from setuptools import setup

setup(
    name="timemachine",
    version="0.1.0",
    packages=["timemachine"],
    install_requires=[
        'aiohttp',
        'aiofiles',
        'requests',
        'python-mpv',
        'RPi.GPIO',
        'adafruit-blinka',
        'adafruit-circuitpython-rgb-display',
        'Pillow',
        'gpiozero',
        'tenacity',
        'pickle5'
    ],
    package_data={
        "timemachine": ["FreeMono.ttf", "ariallgt.ttf", "DejaVuSansMono-Bold.ttf","set_breaks.csv"]
    }
)
