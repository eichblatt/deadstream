from setuptools import setup

setup(
    name="timemachine",
    version="0.2.0",
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
        'cherrypy',
        'pre-commit'
    ],
    package_data={
        "timemachine": ["FreeMono.ttf", "ariallgt.ttf", "DejaVuSansMono-Bold.ttf", "set_breaks.csv"]
    }
)
