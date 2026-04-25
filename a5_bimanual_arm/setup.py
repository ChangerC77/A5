from setuptools import find_packages, setup

package_name = 'a5_bimanual_arm'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'launch/bimanual_arm.launch.py']),
    ],
    install_requires=['setuptools', 'transitions', 'h5py', 'numpy', 'cv_bridge', 'message_filters'],
    python_requires='>=3.8',
    zip_safe=True,
    maintainer='tony',
    maintainer_email='2676239430@qq.com',
    description='TODO: Package description',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'bimanual_arm_controller = a5_bimanual_arm.bimanual_arm_controller_node:main',
        ],
    },
)
