from setuptools import setup

setup(
    name="timemachine",
    version="0.2.1",
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
        'adafruit-blinka',
        'adafruit-circuitpython-rgb-display',
        'aiohttp',
        'aiofiles',
        'cherrypy',
        'gpiozero',
        'Pillow',
        'pre-commit',
        'python-mpv',
        'requests',
        'RPi.GPIO',
        'tenacity',
        'wheel'
    ],
    #package_data={
    #    "timemachine": ["ariallgt.ttf", "DejaVuSansMono-Bold.ttf", "FreeMono.ttf", "set_breaks.csv", "fonts/*ttf"],
    #}
    entry_points={'console_scripts':
                  ['timemachine=timemachine.main:main',
                   'timemachine_test_update=timemachine.main:main_test_update'
                   ]}
)
