"""Validate a text list with format, DNS and SMTP checks, preserving unknown results."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import inspect
import os
from pathlib import Path
import sys
from typing import Callable

Validator = Callable[[str], bool | None]
OUTPUT_NAMES = {'valid': 'true emails.txt', 'invalid': 'false emails.txt',
                'unknown': 'unknown emails.txt'}


def load_validator() -> Validator:
    """Load the documented API without the unused blacklist updater's network I/O."""
    previous = os.environ.get('PY3VE_IGNORE_UPDATER')
    os.environ['PY3VE_IGNORE_UPDATER'] = '1'
    try:
        from validate_email import validate_email_or_fail
        from validate_email.exceptions import (
            AddressFormatError, AddressNotDeliverableError, DomainNotFoundError,
            EmailValidationError, NoMXError, NoValidMXError)
    finally:
        if previous is None:
            os.environ.pop('PY3VE_IGNORE_UPDATER', None)
        else:
            os.environ['PY3VE_IGNORE_UPDATER'] = previous
    options = dict(check_format=True, check_blacklist=False, check_dns=True,
                   dns_timeout=3, check_smtp=True, smtp_timeout=3,
                   smtp_helo_host=None, smtp_from_address=None, smtp_debug=False)
    # Fail before opening result files if a conflicting package shadows this API.
    inspect.signature(validate_email_or_fail).bind(email_address='fixture@example.test', **options)

    def validate(address: str) -> bool | None:
        try:
            return validate_email_or_fail(email_address=address, **options)
        except (AddressFormatError, AddressNotDeliverableError, DomainNotFoundError,
                NoMXError, NoValidMXError):
            return False
        except (EmailValidationError, OSError):
            # DNS timeouts, greylisting, TLS and communication failures do not
            # prove that the address is invalid. Programming errors still stop.
            return None
    return validate


def run_file(source: Path, output_dir: Path, validator: Validator, *,
             progress: Callable[[], None] | None = None) -> dict[str, int]:
    """Stream input once into fresh outputs; flush completed results as they arrive."""
    paths = {kind: Path(output_dir) / name for kind, name in OUTPUT_NAMES.items()}
    for path in paths.values():
        if os.path.lexists(path):
            raise FileExistsError(f'Results already exist; choose a fresh output directory: {path}')
    counts = {'valid': 0, 'invalid': 0, 'unknown': 0, 'blank': 0}
    with ExitStack() as stack:
        addresses = stack.enter_context(Path(source).open('r', encoding='utf-8-sig'))
        # Exclusive creation also protects a destination that appears after preflight.
        outputs = {kind: stack.enter_context(path.open('x', encoding='utf-8', newline='\n'))
                   for kind, path in paths.items()}
        for line in addresses:
            address = line.rstrip('\r\n')
            if not address.strip():
                counts['blank'] += 1
                continue
            result = validator(address)
            if result is True:
                kind = 'valid'
            elif result is False:
                kind = 'invalid'
            elif result is None:
                kind = 'unknown'
            else:
                raise TypeError('Validator must return True, False or None')
            outputs[kind].write(address + '\n')
            outputs[kind].flush()
            os.fsync(outputs[kind].fileno())
            counts[kind] += 1
            if progress is not None:
                progress()
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path('emails.txt'))
    parser.add_argument('--output-dir', type=Path, default=Path('.'),
                        help='Existing directory without previous result files')
    args = parser.parse_args(argv)
    try:
        validator = load_validator()
        from tqdm import tqdm
        with tqdm(unit='address', desc='Checking') as progress:
            counts = run_file(args.input, args.output_dir, validator,
                              progress=lambda: progress.update(1))
        print(' · '.join(f'{kind}: {count}' for kind, count in counts.items()))
        return 2 if counts['unknown'] else 0
    except KeyboardInterrupt:
        print('Interrupted; completed results are retained. The current address is unclassified.', file=sys.stderr)
        return 130
    except (ImportError, OSError, UnicodeError, TypeError, ValueError) as error:
        print(f'{type(error).__name__}: {error}. Any completed result files are retained.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
