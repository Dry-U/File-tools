from setuptools import setup, find_packages

setup(
    name="file-tools",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.95.2",
        "uvicorn>=0.22.0",
        "sqlalchemy>=2.0.15",
        "psycopg2-binary>=2.9.6",
        "python-dotenv>=1.0.0",
        "pyyaml>=6.0",
    ],
    python_requires=">=3.8",
)