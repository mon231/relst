from setuptools import setup


def main():
    setup(
        name="relst",
        version="1.0.0",
        author="Ariel Tubul",
        description="Package used to implement relst-api server and client",
        packages=['relst']
    )


if __name__ == "__main__":
    main()
