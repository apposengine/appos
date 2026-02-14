"""
AppOS setup.py — Package configuration and CLI entry point.
"""

from setuptools import find_packages, setup

setup(
    name="appos",
    version="2.1.0",
    description="AppOS — Python Low-Code Platform",
    packages=find_packages(),
    python_requires=">=3.11",
    entry_points={
        "console_scripts": [
            "appos=appos.cli:main",
        ],
    },
    install_requires=[
        "reflex>=0.6.0",
        "sqlalchemy>=2.0",
        "alembic>=1.13",
        "psycopg2-binary>=2.9",
        "pydantic>=2.5",
        "redis>=5.0",
        "celery[redis]>=5.3",
        "networkx>=3.2",
        "bcrypt>=4.1",
        "cryptography>=42.0",
        "passlib>=1.7",
        "pyyaml>=6.0",
        "httpx>=0.27",
    ],
)
