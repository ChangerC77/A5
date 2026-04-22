from setuptools import setup
from glob import glob

package_name = 'arx_a5_python'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    package_data={
        'arx_a5_python': [
            'lib/*.so',
            'lib/**/*.so',
            'urdf/*',
        ],
    },
    install_requires=['setuptools'],
    zip_safe=False,
    maintainer='tony',
    maintainer_email='2676239430@qq.com',
    description='ARX A5 Python bindings and robot arm control',
    license='TODO',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [],
    },
)
