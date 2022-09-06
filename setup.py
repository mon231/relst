from setuptools import setup, find_packages


SOURCES_FOLDER = "relst"
PROJECT_REQUIREMENTS = [
    'altgraph >= 0.17.2',
    'asgiref==3.5.2',
    'bottle==0.12.23',
    'bottle-websocket==0.2.9',
    'certifi==2022.6.15',
    'charset-normalizer==2.1.1',
    'click==8.1.3',
    'Eel==0.14.0',
    'Flask==2.2.2',
    'future==0.18.2',
    'gevent==21.12.0',
    'gevent-websocket==0.10.1',
    'greenlet==1.1.3',
    'idna==3.3',
    'itsdangerous==2.1.2',
    'Jinja2==3.1.2',
    'MarkupSafe==2.1.1',
    'pyinstaller==5.3',
    'pyinstaller-hooks-contrib==2022.10',
    'pyparsing==3.0.9',
    'requests==2.28.1',
    'urllib3==1.26.12',
    'waitress==2.1.2',
    'Werkzeug==2.2.2',
    'whichcraft==0.6.1',
    'zope.event==4.5.0',
    'zope.interface==5.4.0'
]


def main():
    setup(
        name="relst",
        version="1.0.0",
        author="Ariel Tubul",
        description="Package used to implement relst-api server and client",
        packages=find_packages(),
        requires=PROJECT_REQUIREMENTS
    )


if __name__ == "__main__":
    main()
