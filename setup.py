from pathlib import Path
from setuptools import setup, find_packages


def main():
    readme = Path(__file__).parent / "README.md"

    setup(
        name="relst",
        version="1.1.0",
        author="Ariel Tubul",
        author_email="avarti765@gmail.com",
        description="Expose any python object as an API: relst server and client over json, xml and a compact binary protocol",
        long_description=readme.read_text(encoding="utf-8"),
        long_description_content_type="text/markdown",
        url="https://pypi.org/project/relst/",
        project_urls={"Source": "https://github.com/mon231/relst"},
        packages=find_packages(exclude=["tests", "tests.*"]),
        package_data={"relst.server": ["ui/*.html"]},
        python_requires=">=3.10",
        install_requires=["flask", "waitress", "requests", "firstclass"],
        extras_require={
            "gui": ["eel"],
            "dev": ["pytest", "hypothesis", "build", "twine"],
        },
        classifiers=[
            "Programming Language :: Python :: 3",
            "Programming Language :: Python :: 3.10",
            "Programming Language :: Python :: 3.11",
            "Programming Language :: Python :: 3.12",
            "Programming Language :: Python :: 3.13",
            "Operating System :: OS Independent",
            "Topic :: Software Development :: Libraries",
            "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
        ],
    )


if __name__ == "__main__":
    main()
