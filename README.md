# Email Validate

A local Python CLI that checks a text list using format, DNS and SMTP validation. [Published instructions and source downloads](https://hongyime.github.io/emailvalidate/) are static; the website does not run email checks.

## Installation

Use Python 3.11 or newer and a clean virtual environment. The similarly named `validate-email` package is incompatible with this application's API.

```sh
git clone https://github.com/hongyime/emailvalidate.git
cd emailvalidate
python -m venv .venv
# Activate .venv using your shell, then:
python -m pip install -r requirements.txt
```

The pinned [py3-validate-email package](https://pypi.org/project/py3-validate-email/1.0.5.post2/) provides the intended API. Its upstream maintainer no longer publishes updates on PyPI; this release is pinned and covered by the compatibility tests below. The unused blacklist updater is disabled before the dependency loads. `tqdm` provides progress reporting.

## Usage

Create `emails.txt` containing one address per line, then run:

```sh
python validateemail.py
```

All three result filenames must be absent from the output directory. To run another list while retaining previous results, create a fresh directory first:

```sh
mkdir results-next
python validateemail.py --input another-list.txt --output-dir results-next
```

Input is streamed once as UTF-8 (an initial BOM is accepted). Blank lines are skipped. Address spelling, order and duplicate occurrences in the input are retained in the corresponding result files; the original input is never modified. Results use UTF-8 and LF newlines.

| File | Meaning |
| --- | --- |
| `true emails.txt` | Passed the configured checks |
| `false emails.txt` | Definitive format, missing-domain/MX or recipient-rejection result |
| `unknown emails.txt` | Inconclusive reply, DNS timeout, greylisting, TLS or communication failure |

Format, DNS and SMTP checks remain enabled, with the existing three-second DNS/SMTP timeout settings. The library may contact multiple mail servers, so three seconds is not a total per-address deadline. No email message body is sent. Server responses cannot guarantee that an address will accept a future message.

## Preservation and exit codes

Existing results are refused rather than appended or overwritten, including files created concurrently after preflight. Completed lines are flushed to disk as processing advances. Ctrl+C stops the run and leaves the currently checked address unclassified; completed output remains available. A startup/write failure may leave empty or partial result files. Keep those files and select a fresh output directory for another attempt. Results can remain incomplete after an interruption or I/O failure; automatic resume is not implemented.

Exit codes: `0` for a completed run with no unknown results, `2` for completed processing with unknown results (also used for invalid CLI arguments), `130` for Ctrl+C and `1` for installation or file errors. Invalid addresses alone do not cause a nonzero exit code. Unexpected programming errors stop the run without classifying the affected address.

Importing `validateemail` does not open address lists, load the provider, start network work or create outputs. `--help` also works without application dependencies.

## Development

```sh
python -m pip install -r requirements.txt
python -m pip check
python -m unittest discover -s tests -v
```

The 22 tests use temporary address lists and mocked DNS/SMTP replies. They cover the actual installed provider API, unknown/error mapping, file preservation, interruption, CLI status codes and updater suppression. GitHub Actions runs them on Linux and Windows. No real address lists or live DNS/SMTP probes are used for verification.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
