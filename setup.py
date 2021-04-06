from setuptools import setup


def readme():
    with open('README.md') as f:
        return f.read()


setup(
    name='pyrobogen',
    version='0.0.1',
    description='2D-Robotic Arm Motion Generator',
    url='https://github.com/virtual-origami/pyrobomogen',
    long_description=readme(),
    author='Karthik Shenoy, Shan Desai',
    author_email='she@biba.uni-bremen.de, des@biba.uni-bremen.de',
    license='MIT',
    packages=['RoboGen'],
    install_requires=[
        'numpy',
        'PyYAML',
        'pamqp',
        'aio-pika'
    ],
    include_data_package=True,
    zip_safe=False
)
