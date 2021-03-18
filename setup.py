from setuptools import setup, find_packages


def readme():
    with open( 'README.md' ) as f:
        return f.read()


setup( name='RoboGen',
       version='0.1',
       description='Robot Motion Generator',
       long_description=readme(),
       author='Karthik , Shan Desai',
       author_email='des@biba.uni-bremen.de, she@biba.uni-bremen.de',
       license='MIT',
       packages=['RoboGen'],
       scripts=[],
       install_requires=[
           'numpy',
           'PyYAML',
           'pamqp',
           'aio-pika'
       ],
       include_data_package=True,
       zip_safe=False )
