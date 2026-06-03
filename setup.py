from setuptools import setup, Extension
import platform

if platform.system() == 'Windows':
    extra_args = ['/O2', '/GL']
    link_args = ['/LTCG']
else:
    extra_args = ['-O3', '-march=native', '-funroll-loops']
    link_args = []

module = Extension('create2_pow',
                  sources=['create2_pow.c'],
                  extra_compile_args=extra_args,
                  extra_link_args=link_args)

setup(name='Create2Pow',
      version='1.0',
      description='CREATE2 address mining C acceleration for PremiumNumber Miner',
      ext_modules=[module])
