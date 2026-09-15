"""Offline regression checks; all address lists and provider replies are fixtures."""
from contextlib import redirect_stderr, redirect_stdout
from importlib import import_module, util
from io import StringIO
from pathlib import Path
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = util.spec_from_file_location('validateemail', ROOT / 'validateemail.py')
app = util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


class ResultsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.input = self.root / 'emails.txt'
        self.input.write_text('yes@example.test\nno@example.test\nmaybe@example.test\n', encoding='utf-8')
        self.output = self.root / 'results'

    def run_fixture(self, replies, **kwargs):
        self.output.mkdir(exist_ok=True)
        return app.run_file(self.input, self.output, Mock(side_effect=replies), **kwargs)

    def read_output(self, name):
        return (self.output / f'{name} emails.txt').read_text(encoding='utf-8')

    def test_import_has_no_list_dependency_or_provider_import(self):
        code = 'import sys; import validateemail; assert "validate_email" not in sys.modules; assert "tqdm" not in sys.modules'
        result = subprocess.run([sys.executable, '-c', code], cwd=self.root,
                                env={**os.environ, 'PYTHONPATH': str(ROOT)}, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['emails.txt'])

    def test_three_results_remain_distinct(self):
        counts = self.run_fixture([True, False, None])
        self.assertEqual(counts, {'valid': 1, 'invalid': 1, 'unknown': 1, 'blank': 0})
        self.assertEqual(self.read_output('true'), 'yes@example.test\n')
        self.assertEqual(self.read_output('false'), 'no@example.test\n')
        self.assertEqual(self.read_output('unknown'), 'maybe@example.test\n')

    def test_original_input_bytes_and_duplicate_occurrences_are_preserved(self):
        data = b'same@example.test\r\nsame@example.test\r\n\r\n'
        self.input.write_bytes(data)
        counts = self.run_fixture([True, True])
        self.assertEqual(self.input.read_bytes(), data)
        self.assertEqual(self.read_output('true'), 'same@example.test\nsame@example.test\n')
        self.assertEqual(counts['blank'], 1)

    def test_existing_outputs_prevent_validation_or_new_files(self):
        for filename in app.OUTPUT_NAMES.values():
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                target = Path(directory)
                retained = target / filename
                retained.write_bytes(b'prior results\x00\xff')
                validator = Mock()
                with self.assertRaises(FileExistsError):
                    app.run_file(self.input, target, validator)
                validator.assert_not_called()
                self.assertEqual(retained.read_bytes(), b'prior results\x00\xff')
                self.assertEqual(list(target.iterdir()), [retained])

    def test_repeat_run_does_not_append_duplicates(self):
        self.run_fixture([True, False, None])
        before = {p.name: p.read_bytes() for p in self.output.iterdir()}
        with self.assertRaises(FileExistsError):
            self.run_fixture([True, False, None])
        self.assertEqual({p.name: p.read_bytes() for p in self.output.iterdir()}, before)

    def test_missing_input_creates_no_output_files(self):
        self.output.mkdir()
        with self.assertRaises(FileNotFoundError):
            app.run_file(self.root / 'missing.txt', self.output, Mock())
        self.assertEqual(list(self.output.iterdir()), [])

    def test_interruption_stops_before_classifying_current_address(self):
        with self.assertRaises(KeyboardInterrupt):
            self.run_fixture([True, KeyboardInterrupt(), False])
        self.assertEqual(self.read_output('true'), 'yes@example.test\n')
        self.assertEqual(self.read_output('false'), '')
        self.assertEqual(self.read_output('unknown'), '')

    def test_unexpected_provider_error_keeps_prior_results_and_stops(self):
        with self.assertRaisesRegex(RuntimeError, 'fixture provider bug'):
            self.run_fixture([True, RuntimeError('fixture provider bug')])
        self.assertEqual(self.read_output('true'), 'yes@example.test\n')
        self.assertEqual(self.read_output('false'), '')

    def test_non_boolean_provider_result_is_not_classified(self):
        for result in [1, 0, 'true', 'false', []]:
            with self.subTest(result=result), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(TypeError):
                    app.run_file(self.input, Path(directory), Mock(return_value=result))
                self.assertTrue(all(p.stat().st_size == 0 for p in Path(directory).iterdir()))

    def test_destination_race_preserves_the_concurrent_file(self):
        self.output.mkdir()
        original = Path.open
        target = self.output / 'true emails.txt'
        def raced_open(path, mode='r', *args, **kwargs):
            if path == target and mode == 'x':
                with original(path, 'w', encoding='utf-8') as file:
                    file.write('concurrent result\n')
            return original(path, mode, *args, **kwargs)
        validator = Mock()
        with patch.object(Path, 'open', new=raced_open), self.assertRaises(FileExistsError):
            app.run_file(self.input, self.output, validator)
        self.assertEqual(target.read_text(), 'concurrent result\n')
        validator.assert_not_called()

    def test_progress_runs_after_each_persisted_nonblank_result(self):
        callback = Mock()
        self.run_fixture([True, False, None], progress=callback)
        self.assertEqual(callback.call_count, 3)

    def test_cli_help_does_not_load_provider(self):
        result = subprocess.run([sys.executable, str(ROOT / 'validateemail.py'), '--help'],
                                cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--output-dir', result.stdout)
        self.assertEqual(list(self.root.iterdir()), [self.input])

    def test_cli_interrupt_returns_130_with_completed_results_retained(self):
        self.output.mkdir()
        errors = StringIO()
        with patch.object(app, 'load_validator', return_value=Mock(side_effect=[True, KeyboardInterrupt()])), redirect_stderr(errors):
            result = app.main(['--input', str(self.input), '--output-dir', str(self.output)])
        self.assertEqual(result, 130)
        self.assertIn('retained', errors.getvalue())
        self.assertEqual(self.read_output('true'), 'yes@example.test\n')

    def test_cli_reports_unknown_results_with_incomplete_exit_code(self):
        self.output.mkdir()
        output = StringIO()
        with patch.object(app, 'load_validator', return_value=Mock(side_effect=[True, False, None])), redirect_stdout(output), redirect_stderr(StringIO()):
            result = app.main(['--input', str(self.input), '--output-dir', str(self.output)])
        self.assertEqual(result, 2)
        self.assertIn('unknown: 1', output.getvalue())

    def test_first_provider_load_starts_no_updater_or_network(self):
        code = '''
import os, socket, threading, urllib.request
from unittest.mock import patch
import validateemail
os.environ.pop('PY3VE_IGNORE_UPDATER', None)
with patch.object(threading.Thread, 'start') as thread, patch.object(socket, 'getaddrinfo') as dns, patch.object(socket.socket, 'connect') as connect, patch.object(urllib.request, 'urlopen') as fetch:
    validateemail.load_validator()
    thread.assert_not_called()
    dns.assert_not_called()
    connect.assert_not_called()
    fetch.assert_not_called()
assert 'PY3VE_IGNORE_UPDATER' not in os.environ
'''
        result = subprocess.run([sys.executable, '-c', code], cwd=self.root,
                                env={**os.environ, 'PYTHONPATH': str(ROOT)}, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


class ProviderContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.object(socket.socket, 'connect', side_effect=AssertionError('unexpected network')):
            cls.check = staticmethod(app.load_validator())
        cls.provider = import_module('validate_email.validate_email')
        cls.errors = import_module('validate_email.exceptions')

    def test_real_provider_api_runs_format_dns_smtp_against_fixtures(self):
        with patch.object(self.provider, 'dns_check', return_value=['mx.example.test']) as dns, \
                patch.object(self.provider, 'smtp_check', return_value=True) as smtp:
            self.assertIs(self.check('person@example.test'), True)
        dns.assert_called_once()
        self.assertEqual(dns.call_args.kwargs['timeout'], 3)
        smtp.assert_called_once()
        self.assertEqual(smtp.call_args.kwargs['timeout'], 3)

    def test_installed_dns_dependency_parses_a_fixture_answer(self):
        from dns.rrset import from_text
        from types import SimpleNamespace
        dns_module = import_module('validate_email.dns_check')
        answer = SimpleNamespace(rrset=from_text('example.test.', 60, 'IN', 'MX', '10 mx.example.test.'))
        with patch.object(dns_module, 'resolve', return_value=answer) as resolver, patch.object(self.provider, 'smtp_check', return_value=True) as smtp:
            self.assertIs(self.check('person@example.test'), True)
        self.assertEqual(resolver.call_args.kwargs['qname'], 'example.test')
        self.assertEqual(smtp.call_args.kwargs['mx_records'], ['mx.example.test'])

    def test_definitive_errors_remain_invalid(self):
        e = self.errors
        for error in [e.AddressFormatError(), e.DomainNotFoundError(), e.NoMXError(), e.NoValidMXError(), e.AddressNotDeliverableError({})]:
            with self.subTest(error=type(error).__name__), patch.object(self.provider, 'dns_check', side_effect=error):
                self.assertIs(self.check('person@example.test'), False)

    def test_ambiguous_failures_remain_unknown(self):
        e = self.errors
        for error in [e.DNSTimeoutError(), e.NoNameserverError(), e.DNSConfigurationError(), e.SMTPTemporaryError({}), e.SMTPCommunicationError({}), e.TLSNegotiationError(), TimeoutError('fixture timeout')]:
            with self.subTest(error=type(error).__name__), patch.object(self.provider, 'dns_check', side_effect=error):
                self.assertIsNone(self.check('person@example.test'))

    def test_ambiguous_smtp_reply_remains_unknown(self):
        with patch.object(self.provider, 'dns_check', return_value=['mx.example.test']), patch.object(self.provider, 'smtp_check', return_value=None):
            self.assertIsNone(self.check('person@example.test'))

    def test_malformed_input_does_not_start_dns_or_smtp(self):
        with patch.object(self.provider, 'dns_check') as dns, patch.object(self.provider, 'smtp_check') as smtp:
            self.assertIs(self.check('not an address'), False)
        dns.assert_not_called()
        smtp.assert_not_called()

    def test_provider_updater_stays_disabled_and_environment_is_restored(self):
        updater = import_module('validate_email.updater')
        previous = os.environ.get('PY3VE_IGNORE_UPDATER')
        self.assertTrue(updater.ENV_IGNORE_UPDATER)
        with patch.object(updater, 'Thread') as thread:
            app.load_validator()
            self.assertIsNone(updater.update_builtin_blacklist())
        thread.assert_not_called()
        self.assertEqual(os.environ.get('PY3VE_IGNORE_UPDATER'), previous)


if __name__ == '__main__':
    unittest.main()
