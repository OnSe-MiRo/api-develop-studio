"""Generate with pinned OpenAPI Generator; --check detects stale generated files."""
from pathlib import Path
from importlib.metadata import version
import argparse
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '7.24.0'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    import openapi_generator_cli
    if version('openapi-generator-cli') != VERSION:
        raise SystemExit(f'Install openapi-generator-cli=={VERSION}')
    jar = Path(openapi_generator_cli.__file__).with_name('openapi-generator.jar')
    java = shutil.which('java')
    if not java:
        raise SystemExit('Java is required by OpenAPI Generator')
    with tempfile.TemporaryDirectory(prefix='studio-server-generator-') as directory:
        command = [java, '-jar', str(jar)]
        subprocess.run([*command, 'validate', '-i', str(ROOT / 'openapi/studio.yaml')], check=True)
        subprocess.run([*command, 'generate', '-g', 'python-fastapi', '-i', str(ROOT / 'openapi/studio.yaml'),
                        '-c', str(ROOT / 'openapi/generator-config.yaml'), '-t', str(ROOT / 'openapi/templates'),
                        '-o', directory, '--global-property', 'apiTests=false,modelTests=false,apiDocs=false,modelDocs=false'], check=True)
        source = Path(directory) / 'api_test/generated'
        files = {str(p.relative_to(source)): p.read_bytes() for p in source.rglob('*.py') if p.name != 'security_api.py' and not p.name.endswith('_base.py')}
        destination = ROOT / 'api_test/generated'
        existing = {str(p.relative_to(destination)): p.read_bytes() for p in destination.rglob('*.py')}
        if args.check:
            changed = sorted(name for name in files.keys() | existing.keys() if files.get(name) != existing.get(name))
            if changed:
                raise SystemExit('Generated files differ: ' + ', '.join(changed))
            print('Generated server is up to date.')
            return
        for name in existing.keys() - files.keys():
            (destination / name).unlink()
        for name, content in files.items():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        print(f'Generated {len(files)} Python files.')


if __name__ == '__main__':
    main()
