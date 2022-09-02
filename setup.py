from setuptools import setup, find_packages


def main():
    setup(
        name="relst",
        version="1.0.0",
        author="Ariel Tubul",
        description="Package used to implement relst-api server and client",
        packages=find_packages()
    )


if __name__ == "__main__":
    main()
