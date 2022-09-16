from pathlib import Path
from setuptools import setup, find_packages


def main():
    setup(
        name="relst",
        version="1.0.0",
        author="Ariel Tubul",
        description="Package used to implement relst-api server and client",
        packages=find_packages(),
        install_requires=list(get_requirements())
    )


def get_requirements():
    requirements_path = Path(__file__).parent / "requirements.txt"

    with open(requirements_path, "r") as requirements_file:
        requirements = requirements_file.readlines()

    while requirements:
        if current_line := requirements.pop().split('#')[0].strip():
            yield current_line


if __name__ == "__main__":
    main()
