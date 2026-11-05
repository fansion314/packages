"""The reviewed Warp rotation must reach both source and client keyrings."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PRIMARY = '0913165C78D5B7A41B42AC657FF7AB39D60F803F'
SIGNING = 'D272B58E4BF4EA3E7CB958A55AC01A19A09FA9A6'
REVOKED = '19A1E427461B1795F73F629631F4254AFE49E02E'


class KeyRotationTests(unittest.TestCase):
    def test_reviewed_source_and_generated_keyring_keep_rotation_and_revocation(self):
        for key in [ROOT/'upstream-keys/warpdotdev.asc',
                    ROOT/'support/fansionia-keyring/fansionia-upstream.gpg']:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as home:
                subprocess.run(['gpg', '--homedir', home, '--batch', '--import', str(key)],
                               check=True, capture_output=True)
                listing = subprocess.check_output(['gpg', '--homedir', home, '--batch',
                    '--with-colons', '--with-fingerprint', '--with-subkey-fingerprint',
                    '--check-sigs', PRIMARY], stderr=subprocess.PIPE, text=True)
                records = {}
                current = None
                for line in listing.splitlines():
                    parts = line.split(':')
                    if parts[0] in ('pub', 'sub'):
                        current = {'kind': parts[0], 'validity': parts[1], 'signatures': []}
                    elif parts[0] == 'fpr':
                        records[parts[9]] = current
                    elif parts[0] == 'sig':
                        current['signatures'].append(parts)
                self.assertEqual(records[PRIMARY]['kind'], 'pub')
                self.assertEqual(records[SIGNING]['kind'], 'sub')
                self.assertNotEqual(records[SIGNING]['validity'], 'r')
                self.assertEqual(records[REVOKED]['validity'], 'r')
                self.assertTrue(any(s[1] == '!' and s[4] == PRIMARY[-16:]
                                    for s in records[SIGNING]['signatures']))


if __name__ == '__main__':
    unittest.main()
