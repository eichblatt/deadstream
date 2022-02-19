from setuptools import setup
from distutils.util import convert_path

version_path = convert_path('timemachine/.latest_tag')
version_number = open(version_path, 'r').readline().strip()
print(f"version_number is {version_number}")

setup(
    name='timemachine',
    version=version_number,
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
        'pexpect',
        'pickle5',
        'Pillow',
        'pre-commit',
        'pulsectl',
        'python-mpv',
        'requests',
        'RPi.GPIO',
        'tenacity',
        'wheel'],
    package_data={
        'timemachine': ['fonts/ariallgt.ttf', 'fonts/DejaVuSansMono-Bold.ttf', 'fonts/FreeMono.ttf', 'metadata/set_breaks.csv',
                        'metadata/silence600.ogg', 'metadata/silence300.ogg', 'options.txt', '.latest_tag']},
    entry_points={'console_scripts':
                  ['connect_network=timemachine.connect_network:main',
                   'calibrate=timemachine.calibrate:main',
                   'serve_options=timemachine.serve_options:main',
                   'timemachine=timemachine.main:main',
                   'timemachine_test_update=timemachine.main:main_test_update']},
    scripts=['timemachine/bin/services.sh', 'timemachine/bin/update.sh', 'timemachine/bin/board_version.sh',
             'timemachine/bin/calibrate.sh', 'timemachine/bin/timemachine.service', 'timemachine/bin/update.service',
             'timemachine/bin/connect_network.service', 'timemachine/bin/serve_options.service',
             'timemachine/bin/calibrate.service', 'timemachine/bin/pulseaudio.service'],
    license_files=('LICENSE',),
    license='GNU General Public License v3 (GPLv3)'
)
