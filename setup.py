"""
Setup script for AI-Integrated DAW
"""

from setuptools import setup, find_packages
import os

# Read README
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Read requirements
with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="ai-integrated-daw",
    version="1.0.0",
    author="ARIA Team",
    author_email="contact@aria-daw.com",
    description="A Digital Audio Workstation with AI-powered music generation",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/ai-integrated-daw",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Multimedia :: Sound/Audio :: Editors",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-qt>=4.0.0",
            "black>=22.0.0",
            "flake8>=4.0.0",
            "mypy>=0.950",
        ],
        "build": [
            "pyinstaller>=5.0.0",
            "cx_Freeze>=6.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "aria-daw=main:main",
        ],
        "gui_scripts": [
            "aria-daw-gui=main:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["*.json", "*.txt", "*.md"],
    },
    project_urls={
        "Bug Reports": "https://github.com/yourusername/ai-integrated-daw/issues",
        "Source": "https://github.com/yourusername/ai-integrated-daw",
        "Documentation": "https://github.com/yourusername/ai-integrated-daw/wiki",
    },
    keywords="daw audio music production ai elevenlabs pyqt6",
)
