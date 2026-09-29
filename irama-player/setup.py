from setuptools import setup, find_packages

setup(
    name="irama-player",
    version="0.1.0",
    description="Irama Nusantara Album Streamer and Downloader CLI",
    author="Gemini Software Engineer",
    packages=find_packages(),
    install_requires=[
        "requests>=2.28.0",
    ],
    entry_points={
        "console_scripts": [
            "irama-player=irama.cli:main",
        ],
    },
    python_requires=">=3.8",
)
