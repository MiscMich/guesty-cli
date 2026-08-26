from setuptools import setup, find_packages

setup(
    name='guesty-cli',
    version='0.2.1',
    description='Universal CLI for Guesty PMS',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='Villa Paraiso Vacation Rentals',
    author_email='tech@paraisovacationrentals.com',
    url='https://github.com/Villa-Paraiso-Vacation-Rentals/guesty-cli',
    packages=find_packages(),
    include_package_data=True,
    python_requires='>=3.8',
    entry_points={
        'console_scripts': [
            'guesty=guesty_cli.main:main',
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Topic :: Software Development :: Libraries',
        'Topic :: Office/Business',
        'Operating System :: OS Independent',
    ],
    keywords='guesty pms vacation rental cli automation',
    project_urls={
        'Bug Reports': 'https://github.com/Villa-Paraiso-Vacation-Rentals/guesty-cli/issues',
        'Source': 'https://github.com/Villa-Paraiso-Vacation-Rentals/guesty-cli',
        'Documentation': 'https://github.com/Villa-Paraiso-Vacation-Rentals/guesty-cli/blob/main/README.md',
    },
)
