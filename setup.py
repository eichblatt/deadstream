from setuptools import setup

setup(
    name="timemachine",
    version="0.2.0",
    author="Steve Eichblatt",
    author_email="gdtimemachine@gmail.com",
    description="A Grateful Dead Time Machine",
    url="https://github.com/eichblatt/deadstream",
    packages=["timemachine"],
    python_requires=">=3.6",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: GPL v3.0 ",
        "Operating System :: Linux ",
    ],
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
    entry_points={'console_scripts':
                  ['timemachine=timemachine.main:main',
                   'timemachine_test_update=timemachine.main:main_test_update'
                   ]},
    package_data={
        "timemachine": ["FreeMono.ttf", "ariallgt.ttf", "DejaVuSansMono-Bold.ttf", "set_breaks.csv"]
    }
)
