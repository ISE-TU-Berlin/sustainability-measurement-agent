"""Setup configuration for Sustainability Measurment Agent."""

from setuptools import setup, find_packages

# Core dependencies for runtime
requirements = [
    "requests>=2.32.4",
]

setup(
    name="sutainability-measurement-agent",
    version="0.1.0",
    description="A tool for collecting and analyzing sustainability metrics in cloud native enviroments.",
    author="ISE, TU Berlin",
    packages=find_packages(),
    install_requires=requirements,
    python_requires=">=3.12",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
