from setuptools import setup, find_packages

setup(
    name="edutrack",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "fastapi",
        "uvicorn",
        "sqlalchemy",
        "pydantic",
        "python-jose[cryptography]",
        "passlib[bcrypt]",
        "python-multipart",
        "python-dotenv",
        "aiosqlite",
        "gitpython",
        "pytest",
        "httpx",
        "pytest-asyncio"
    ],
)
