"""Guards for the packaging and the CI / publish workflows, so a broken release is found before the tag"""

import re
import pytest
from pathlib import Path


ROOT = Path(__file__).parent.parent
SETUP = (ROOT / 'setup.py').read_text(encoding='utf-8')
VERSION_SED = re.compile(r'version="[^"]*"')
TAG_PATTERN = re.compile(r'^v[0-9]+\.[0-9]+\.[0-9]+([abc]|rc)?[0-9]*$')


def test_setup_has_exactly_one_version_for_the_publish_workflow_to_rewrite():
    assert len(VERSION_SED.findall(SETUP)) == 1
    assert VERSION_SED.sub('version="9.9.9"', SETUP).count('version="9.9.9"') == 1


@pytest.mark.parametrize('tag', ['v1.2.3', 'v0.0.1', 'v10.20.30', 'v1.2.3rc1', 'v1.2.3a1', 'v1.2.3b2'])
def test_release_tags_accepted(tag):
    assert TAG_PATTERN.match(tag)


@pytest.mark.parametrize('tag', ['1.2.3', 'v1.2', 'v1.2.3.4', 'vx', 'v1.2.3-beta', 'v1.2.3dev1', 'release-1'])
def test_other_tags_rejected(tag):
    assert not TAG_PATTERN.match(tag)


def test_workflow_files_are_valid_yaml_with_expected_jobs():
    yaml = pytest.importorskip('yaml')

    ci = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8'))
    publish = yaml.safe_load((ROOT / '.github/workflows/publish.yml').read_text(encoding='utf-8'))

    assert set(ci['jobs']) == {'test', 'build'}
    assert list(publish['jobs']) == ['test', 'build', 'publish', 'release']
    # NOTE: yaml parses the bare key `on` as boolean True
    assert publish[True]['push']['tags'] == ['v*']
    assert publish['jobs']['publish']['needs'] == 'build'


def test_workflows_use_extras_that_exist():
    for workflow in (ROOT / '.github/workflows').glob('*.yml'):
        for extra in re.findall(r'-e "\.\[(\w+)\]"', workflow.read_text(encoding='utf-8')):
            assert f'"{extra}":' in SETUP, f'{workflow.name} installs missing extra {extra}'


def test_workflows_only_run_files_that_exist():
    for workflow in (ROOT / '.github/workflows').glob('*.yml'):
        for path in re.findall(r'python (examples/\S+\.py)', workflow.read_text(encoding='utf-8')):
            assert (ROOT / path).exists(), f'{workflow.name} runs missing {path}'


def test_ui_file_is_shipped_as_package_data():
    from relst.server.textual_server import UI_PATH

    assert UI_PATH.exists()
    assert 'ui/*.html' in SETUP


def test_declared_runtime_requirements_are_imported_modules():
    declared = re.search(r'install_requires=\[(.*?)\]', SETUP).group(1)
    assert {'flask', 'waitress', 'requests', 'firstclass'} <= set(re.findall(r'"(\w+)"', declared))


def test_gitignore_does_not_hide_tracked_project_folders():
    ignored = [line.strip() for line in (ROOT / '.gitignore').read_text(encoding='utf-8').splitlines() if line.strip() and not line.startswith('#')]

    for folder in ('examples', 'tests', 'relst', '.github'):
        assert not any(line.rstrip('/') in (folder, folder + '*', '/' + folder) for line in ignored), folder

    assert 'example*' not in ignored


def test_readme_mentions_every_public_class():
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')

    for name in ('RelstTextualServer', 'RelstBinaryServer', 'RelstFlaskClient', 'RelstSocketClient', 'pip install relst'):
        assert name in readme


def test_workflows_run_on_ubuntu_only():
    for workflow in (ROOT / '.github/workflows').glob('*.yml'):
        runners = re.findall(r'runs-on:\s*(\S+)', workflow.read_text(encoding='utf-8'))

        assert runners and all(runner == 'ubuntu-latest' for runner in runners), workflow.name
