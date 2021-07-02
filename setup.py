from setuptools import setup

setup(
    name='timemachine',
    version='0.2.2',
    author='Steve Eichblatt',
    author_email='gdtimemachine@gmail.com',
    description='A Grateful Dead Time Machine',
    long_description='A Grateful Dead Time Machine. \nGNU General Public License v3 (GPLv3)',
    url='https://github.com/eichblatt/deadstream',
    package_dir={
        'timemachine': 'timemachine',
        'timemachine.fonts': 'timemachine/fonts',
        'timemachine.metadata': 'timemachine/metadata'},
    packages=['timemachine', 'timemachine.fonts', 'timemachine.metadata'],
    python_requires='>=3.6',
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: Linux '],
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
        'wheel'],
    package_data={
        'timemachine': ['fonts/ariallgt.ttf', 'fonts/DejaVuSansMono-Bold.ttf', 'fonts/FreeMono.ttf', 'metadata/set_breaks.csv',
                        'metadata/silence600.ogg', 'metadata/silence300.ogg', 'options.txt']},
    entry_points={'console_scripts':
                  ['connect_network=timemachine.connect_network:main',
                   'serve_options=timemachine.serve_options:main',
                   'timemachine=timemachine.main:main',
                   'timemachine_test_update=timemachine.main:main_test_update']},
    scripts=['timemachine/bin/services.sh', 'timemachine/bin/update.sh', 'timemachine/bin/board_version.sh',
             'timemachine/bin/timemachine.service', 'timemachine/bin/update.service', 'timemachine/bin/connect_network.service',
             'timemachine/bin/serve_options.service'],
    license_files=('LICENSE',),
    license='GNU General Public License v3 (GPLv3)'
)
