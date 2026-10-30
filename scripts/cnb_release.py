"""Scoped, immutable CNB Release attachment operations shared by distributors."""
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

API = 'https://api.cnb.cool'

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()

def quote(value):
    return urllib.parse.quote(value, safe='')

def location(repository, tag, filename):
    return f'https://cnb.cool/{repository}/-/releases/download/{quote(tag)}/{quote(filename)}'

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        return None


class Client:
    def __init__(self, repository, token=None, *, owner, user_agent="fansionia-mirror"):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+', repository):
            raise ValueError('Invalid CNB repository')
        self.owner = owner
        self.user_agent = user_agent
        self.repository = repository
        self.token = token or os.environ.get('CNB_MIRROR_TOKEN')
        if not self.token:
            raise ValueError('CNB_MIRROR_TOKEN is required')
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, method, path, data=None, missing=False):
        # Never follow a redirect with the bearer token or include API response
        # bodies / pre-signed upload URLs in exceptions and Actions logs.
        url = API+path if path.startswith('/') else path
        if not url.startswith(API+'/'+self.repository+'/-/releases'):
            raise ValueError('CNB API request outside the configured Release scope')
        request = urllib.request.Request(url, method=method,
            data=canonical(data) if data is not None else None,
            headers={'Authorization': 'Bearer '+self.token, 'Accept': 'application/vnd.cnb.api+json',
                     'Content-Type': 'application/json', 'User-Agent': self.user_agent})
        try:
            with self.opener.open(request, timeout=90) as response:
                body = response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            if missing and error.code == 404:
                return None
            raise RuntimeError(f'CNB Release API {method} failed: HTTP {error.code}') from None
        except (OSError, ValueError):
            raise RuntimeError(f'CNB Release API {method} failed') from None

    def release(self, tag, create=False, title=None):
        path = f'/{self.repository}/-/releases'
        result = self.request('GET', path+'/tags/'+quote(tag), missing=True)
        if result is None and create:
            result = self.request('POST', path, {'tag_name': tag, 'target_commitish': 'main',
                'name': title or tag, 'body': self.owner, 'draft': False, 'make_latest': 'false'})
        if result is not None and result.get('body') != self.owner:
            raise ValueError('CNB release is not owned by the mirror: '+tag)
        if result is not None and title and result.get('name') != title:
            self.request('PATCH', path+'/'+quote(str(result['id'])), {'name': title})
            result['name'] = title
        return result

    def upload(self, item, source):
        release = self.release(item['tag'], create=True, title=item.get('title'))
        matches = [a for a in (release.get('assets') or []) if a['name'] == item['filename']]
        if len(matches) > 1:
            raise ValueError('Duplicate CNB attachment')
        if matches:
            asset = matches[0]
            if asset['size'] != item['size']:
                raise ValueError('Refusing to overwrite a different CNB attachment')
            if (asset.get('hash_algo') or '').lower().replace('-', '') == 'sha256' and \
                    asset['hash_value'].lower() != item['sha256']:
                raise ValueError('Refusing to overwrite a different CNB digest')
            # Full anonymous SHA-256 verification below also handles servers
            # that report a different hash algorithm, or no hash metadata.
            return False
        prefix = f'/{self.repository}/-/releases/{quote(str(release["id"]))}'
        result = self.request('POST', prefix+'/asset-upload-url', {
            'asset_name': item['filename'], 'size': item['size'], 'overwrite': False, 'ttl': 0})
        upload = urllib.parse.urlsplit(result['upload_url'])
        if upload.scheme != 'https' or not upload.hostname or upload.username:
            raise ValueError('Invalid CNB upload location')
        try:
            with Path(source).open('rb') as body:
                request = urllib.request.Request(result['upload_url'], data=body, method='PUT',
                    headers={'Content-Length': str(item['size']), 'Content-Type': 'application/octet-stream'})
                with self.opener.open(request, timeout=600) as response:
                    response.read()
        except (OSError, ValueError):
            raise RuntimeError('CNB attachment upload failed; retry the publication') from None
        verify = urllib.parse.urlsplit(result['verify_url'])
        if verify.scheme != 'https' or verify.netloc != 'api.cnb.cool' or \
                not verify.path.startswith(prefix+'/asset-upload-confirmation/'):
            raise ValueError('Invalid CNB upload confirmation location')
        # Set permanent retention explicitly at both steps. Store only the
        # stable public download URL, never this temporary credential.
        query = dict(urllib.parse.parse_qsl(verify.query))
        query['ttl'] = '0'
        self.request('POST', verify.path+'?'+urllib.parse.urlencode(query))
        return True

    def delete(self, item):
        release = self.release(item['tag'])
        if release is None:
            return
        prefix = f'/{self.repository}/-/releases/{quote(str(release["id"]))}'
        for asset in (release.get('assets') or []):
            if asset['name'] == item['filename']:
                self.request('DELETE', prefix+'/assets/'+quote(str(asset['id'])))
        # A user may have added other attachments: leave those untouched.
        release = self.release(item['tag'])
        if release is not None and not release.get('assets'):
            self.request('DELETE', prefix)

