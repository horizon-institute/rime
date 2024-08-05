"""
Make a release package of RIME, consisting of the compiled frontend, the backend, and a Python embedded distribution.
"""
from argparse import ArgumentParser
from dataclasses import dataclass
import datetime
import glob
import io
import os
import re
import subprocess
import sys
import shutil
import zipfile


for _candidate in ('.venv/bin/python', 'python3', 'python'):
    if shutil.which(_candidate):
        PYTHON = _candidate
        break
else:
    print('Python not found.')
    sys.exit(1)

FRONTEND_BUILD_CMD = ['npm', 'run', 'build']
FRONTEND_RUN_DIR = 'frontend'
FRONTEND_BUILD_DIR = 'frontend/dist'
BACKEND_BUILD_CMD = [PYTHON, '-m', 'build']
BACKEND_RUN_DIR = '.'
BACKEND_BUILD_DIR = 'dist'
WINDOWS_PYTHON_DIST = 'python-3.12.3-embed-amd64-rime.zip'
GIT = 'git'
EXAMPLES = {'anon-android.zip', 'anon-iphone-6.zip', 'anon-iphone-8.zip'}

PTH_CONTENTS = """\
python312.zip
site-packages.zip
pyd
rime.whl
.
"""
PYTHON_BASEDIR = 'python'


def build_frontend():
    shutil.rmtree(FRONTEND_BUILD_DIR, ignore_errors=True)
    subprocess.run(FRONTEND_BUILD_CMD, check=True, cwd=FRONTEND_RUN_DIR)

    built_pathname = os.path.join(FRONTEND_BUILD_DIR, 'frontend.zip')

    with zipfile.ZipFile(built_pathname, 'w') as zf:
        for dirname, subdirs, filenames in os.walk(FRONTEND_BUILD_DIR, topdown=False):
            relative_dirname = os.path.relpath(dirname, FRONTEND_BUILD_DIR)

            for filename in filenames:
                if filename == 'frontend.zip':
                    continue

                src_pathname = os.path.join(dirname, filename)
                target_pathname = os.path.join(relative_dirname, filename)
                zf.write(src_pathname, arcname=target_pathname)

            if dirname != FRONTEND_BUILD_DIR:
                shutil.rmtree(dirname)


    return built_pathname


def build_backend():
    shutil.rmtree(BACKEND_BUILD_DIR, ignore_errors=True)
    subprocess.run(BACKEND_BUILD_CMD, check=True, cwd=BACKEND_RUN_DIR)
    wheel_files = glob.glob(f'{BACKEND_BUILD_DIR}/*.whl')

    if len(wheel_files) != 1:
        print('Expected exactly one wheel file, found:', wheel_files)
        sys.exit(1)

    return wheel_files[0]


def git_get_release_name():
    try:
        release_name = subprocess.check_output([GIT, 'describe', '--tags'], text=True).strip()
    except subprocess.CalledProcessError:
        # No tags, use the commit hash.
        commit_hash = subprocess.check_output([GIT, 'rev-parse', 'HEAD'], text=True).strip()
        now = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        release_name = f'{now}-{commit_hash}'

    return release_name


def make_frontend_only_release(release_dir):
    frontend_pathname = build_frontend()

    shutil.copyfile(frontend_pathname, os.path.join(release_dir, 'frontend.zip'))

    return 0


def extract_zip_to_zip(src_zf, dst_zf, rename_fn):
    for info in src_zf.infolist():
        if info.is_dir():
            continue

        if target_pathname := rename_fn(info):
            with src_zf.open(info) as src_file:
                dst_zf.writestr(target_pathname, src_file.read())

@dataclass
class FileFate:
    cmd: str
    pathname: str
    contents: bytes|None = None

def make_windows_release(release_dir):
    # A Windows release consists of an embedded Python release with all site packages and RIME installed,
    # the frontend in the top level as frontend.zip, and a small binary loader to run the backend.

    frontend_pathname = build_frontend()
    backend_wheel = build_backend()

    release_zip_pathname = os.path.join(release_dir, 'rime-windows.zip')

    has_suffix = lambda filename, suffixes: any(filename.endswith(suffix) for suffix in suffixes)
    # python_suffixes = ('.py', '.pyc', '.pyo', '.pyi')
    binary_suffixes = ('.pyd', '.dll', '.so', '.dylib')
    python_pth_matcher = re.compile(r'python.*._pth')

    def _location_and_contents_for_file(pathname: str):
        """
        Called for each file in the embedded Python distribution to determine where it should
        end up in the release.
        """
        if pathname.startswith('Lib/site-packages/'):
            # Something in the site-packages subtree.
            if not has_suffix(pathname, binary_suffixes):
                # A Python file in site-packages; add to the site-packages zip excluding the prefix.
                return FileFate('site-packages', pathname[len('Lib/site-packages/'):])
            else:
                # A binary file.
                if pathname.startswith('Lib/site-packages/Crypto'):
                    # A binary file in the Cryptography package; add to the main zip preserving the directory hierarchy.
                    return FileFate('main', PYTHON_BASEDIR + '/' + pathname)
                else:
                    # A binary file in site-packages; add to the root in a pyd/ directory.
                    return FileFate('main', PYTHON_BASEDIR + '/pyd/' + os.path.basename(pathname))
        elif python_pth_matcher.match(pathname):
            # The custom Python imports directive, which we completely overwrite.
            return FileFate('main', PYTHON_BASEDIR + '/' + pathname, PTH_CONTENTS.encode('utf-8'))
        else:
            # Something else.
            return FileFate('main', PYTHON_BASEDIR + '/' + pathname)

    with zipfile.ZipFile(WINDOWS_PYTHON_DIST, 'r') as src_zf, zipfile.ZipFile(release_zip_pathname, 'w') as dst_zf:
        site_packages_zip = io.BytesIO()

        with zipfile.ZipFile(site_packages_zip, 'w', compression=zipfile.ZIP_DEFLATED) as site_packages_zf:
            # Copy all files to the either the main zip or to site-packages.zip.
            for info in src_zf.infolist():

                fate = _location_and_contents_for_file(info.filename)

                if fate.contents is not None:
                    contents = fate.contents
                else:
                    contents = src_zf.read(info)

                match fate:
                    case FileFate(cmd='main', pathname=pathname):
                        dst_zf.writestr(pathname, contents)
                    case FileFate(cmd='site-packages', pathname=pathname):
                        site_packages_zf.writestr(pathname, contents)
                    case _:
                        raise ValueError(f'Unknown fate: {fate}')

        # We're now done with site-packages.zip. Write it to the main zip.
        dst_zf.writestr(PYTHON_BASEDIR + '/site-packages.zip', site_packages_zip.getvalue())

        # Copy the frontend to the main zip.
        dst_zf.write(frontend_pathname, arcname=PYTHON_BASEDIR + '/frontend.zip')

        # Copy the backend to the main zip.
        dst_zf.write(backend_wheel, arcname=PYTHON_BASEDIR + '/rime.whl')

        # Install production dependencies.
        dst_zf.write('release_deps/rime_settings.dist.yaml', arcname=PYTHON_BASEDIR + '/rime_settings.dist.yaml')
        dst_zf.write('release_deps/launch.py', arcname=PYTHON_BASEDIR + '/launch.py')

        # Install examples.
        for example_filename in EXAMPLES:
            example_pathname = os.path.join('example', example_filename)
            dst_zf.write(example_pathname)

        # Install schema.
        dst_zf.write('rime/schema.graphql', arcname=PYTHON_BASEDIR + '/schema.graphql')

        # Install Windows binary
        dst_zf.write('release_deps/Rime.exe', arcname='/Rime.exe')

    return release_zip_pathname


def main():
    parser = ArgumentParser(description='Create a release package for RIME.')
    parser.add_argument('platform', choices=['windows', 'frontend-only'])
    parser.add_argument('--name', help='Name of the release. Defaults to the latest git tag or commit hash.')
    args = parser.parse_args()

    release_name = args.name or git_get_release_name()
    match args.platform:
        case 'frontend-only':
            make_release = make_frontend_only_release
        case 'windows':
            make_release = make_windows_release
        case _:
            print('Unsupported platform:', args.platform)
            sys.exit(1)

    release_dir = os.path.join('releases', release_name)
    shutil.rmtree(release_dir, ignore_errors=True)
    os.makedirs(release_dir, exist_ok=True)

    release_pathname = make_release(release_dir)

    print()
    print(f'Release created at {release_pathname}')

    sys.exit(0)

if __name__ == '__main__':
    main()
