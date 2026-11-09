#!/usr/bin/env python3
"""Drive the exact packaged Tauri/WebKitGTK executable; no production test hooks.

Rust's offline tests cover the AES/HLS transport transformation. This smoke uses
an injected in-memory HLS fixture loader for native WebKit playback, and checks
real hg:// routing/security separately. It does not claim an end-to-end fixture
network fetch through the production transport.
"""
import base64
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.error
import urllib.request

EVIDENCE = Path(os.environ['HGHUB_SMOKE_EVIDENCE'])
BINARY = str(Path(os.environ['HGHUB_SMOKE_BINARY']).resolve())
SOURCE = Path(os.environ['HGHUB_SMOKE_SOURCE'])
MEDIA = Path(os.environ['HGHUB_SMOKE_MEDIA'])
URL = 'http://127.0.0.1:4444'
ELEMENT = 'element-6066-11e4-a52e-4f735466cecf'


def request(method, path, body=None):
    payload = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(URL + path, data=payload, method=method,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=50) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        raise AssertionError(f'{method} {path}: {error.read().decode()}') from error
    value = result.get('value')
    if isinstance(value, dict) and 'error' in value:
        raise AssertionError(value)
    return value


def wait(check, description, seconds=25):
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        try:
            last = check()
            if last:
                return last
        except (OSError, AssertionError) as error:
            last = str(error)
        time.sleep(.2)
    raise AssertionError(f'Timed out: {description}; last={last}')


class Session:
    def __init__(self):
        value = request('POST', '/session', {'capabilities': {'alwaysMatch': {
            'tauri:options': {'application': BINARY},
        }}})
        self.id = value['sessionId']
        request('POST', f'/session/{self.id}/timeouts', {'script': 30000, 'implicit': 0, 'pageLoad': 30000})
        wait(lambda: self.js('return !!document.querySelector(".plat-linux")'), 'Linux desktop')
        self.js('window.__smokeErrors=[]; addEventListener("error",e=>window.__smokeErrors.push(e.message))')

    def command(self, method, path, body=None):
        return request(method, f'/session/{self.id}' + path, body)

    def js(self, script, *args):
        return self.command('POST', '/execute/sync', {'script': script, 'args': list(args)})

    def async_js(self, script, *args):
        result = self.command('POST', '/execute/async', {'script': script, 'args': list(args)})
        assert not isinstance(result, dict) or 'error' not in result, result
        return result

    def click(self, selector):
        element = self.command('POST', '/element', {'using': 'css selector', 'value': selector})
        self.command('POST', '/element/' + element[ELEMENT] + '/click', {})

    def settings(self):
        self.js('''const button=[...document.querySelectorAll('[aria-label="主导航"] button')]
          .find(b=>b.textContent.trim()==='设置'); if(!button)throw Error('Missing settings');button.click();''')
        wait(lambda: self.js('return !!document.querySelector(\'[aria-label="界面缩放"]\')'), 'scale setting')

    def scale(self, percent):
        # Dispatching the real select change keeps React and native IPC in the path.
        self.js('''const s=document.querySelector('[aria-label="界面缩放"]');
          const value=String(arguments[0]);
          const option=[...s.options].find(o=>Number(o.textContent.replace('%',''))===Number(value));
          if(!option)throw Error('Missing scale '+value);
          const setter=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set;
          setter.call(s,option.value);s.dispatchEvent(new Event('change',{bubbles:true}));''', percent)
        wait(lambda: self.js('''const s=document.querySelector('[aria-label="界面缩放"]');
          return s&&!s.disabled&&Number(s.selectedOptions[0].textContent.replace('%',''))===arguments[0]&&localStorage.getItem('hghub_interface_scale')===String(arguments[0]);''', percent), f'scale {percent}')

    def screenshot(self, name):
        raw = self.command('GET', '/screenshot')
        (EVIDENCE / (name + '.png')).write_bytes(base64.b64decode(raw))

    def close(self):
        if self.id:
            self.command('DELETE', '')
            self.id = None


def fixture_playback(session, percent):
    # Load the exact upstream hls.js version already used by this build.
    hls = (SOURCE / 'node_modules/hls.js/dist/hls.min.js').read_text()
    session.js(hls + '\nwindow.__smokeHlsClass=Hls;')
    files = {p.name: base64.b64encode(p.read_bytes()).decode() for p in MEDIA.iterdir()}
    session.js('''
      const files=arguments[0];
      const bytes=name=>Uint8Array.from(atob(files[name]),c=>c.charCodeAt(0));
      const raw=new TextDecoder().decode(bytes('list.m3u8'));
      const manifest=raw.split('\\n').map(line=>line&&!line.startsWith('#')?'hg://localhost/fixture/'+line:line).join('\\n');
      class FixtureLoader {
        constructor(){this.stats={aborted:false,loaded:0,total:0,retry:0,chunkCount:1,bwEstimate:10000000,
          loading:{start:0,first:0,end:0},parsing:{start:0,end:0},buffering:{start:0,first:0,end:0}}}
        load(context,_config,callbacks){
          this.context=context;const started=performance.now();this.stats.loading.start=started;
          const isManifest=context.url.includes('.m3u8');
          const data=isManifest?manifest:bytes(context.url.split('/').pop()).buffer;
          this.stats.loaded=this.stats.total=isManifest?data.length:data.byteLength;
          this.stats.loading.first=performance.now();this.stats.loading.end=performance.now();
          this.timer=setTimeout(()=>{this.complete=true;callbacks.onSuccess({url:context.url,data},this.stats,context,null)},20);
        }
        abort(){clearTimeout(this.timer);this.stats.aborted=true}
        destroy(){clearTimeout(this.timer);if(!this.complete)this.stats.aborted=true}
        getCacheAge(){return null}
      }
      const video=document.createElement('video');video.id='smoke-video';video.muted=true;video.controls=true;
      Object.assign(video.style,{position:'fixed',inset:'80px',width:'min(640px,80vw)',height:'min(480px,70vh)',zIndex:99999,background:'black'});
      document.body.append(video);window.__smokeVideo=video;window.__smokeMediaErrors=[];
      const Hls=window.__smokeHlsClass;if(!Hls.isSupported())throw Error('WebKit MediaSource HLS unsupported');
      const hls=new Hls({loader:FixtureLoader,enableWorker:false});window.__smokeHls=hls;
      hls.on(Hls.Events.ERROR,(_event,data)=>{if(data.fatal)window.__smokeMediaErrors.push(data.details)});
      hls.attachMedia(video);hls.loadSource('hg://localhost/fixture/list.m3u8');
      video.addEventListener('canplay',()=>video.play().catch(e=>window.__smokeMediaErrors.push(String(e))),{once:true});
    ''', files)
    wait(lambda: session.js('return window.__smokeVideo.currentTime>1'), 'native HLS playback advances', 30)
    assert session.js('return window.__smokeMediaErrors') == []
    before = session.js('window.__smokeVideo.pause();return window.__smokeVideo.currentTime')
    time.sleep(.5)
    assert abs(session.js('return window.__smokeVideo.currentTime') - before) < .15
    session.js('window.__smokeVideo.currentTime=7')
    wait(lambda: session.js('return Math.abs(window.__smokeVideo.currentTime-7)<.5'), 'paused seeking')
    session.async_js('const done=arguments[arguments.length-1];window.__smokeVideo.play().then(()=>done(true)).catch(e=>done({error:String(e)}))')
    wait(lambda: session.js('return window.__smokeVideo.currentTime>7.5'), 'playback resumes after seek')
    session.screenshot('native-hls-playing-' + str(percent))
    assert session.js('return window.__smokeMediaErrors') == []
    session.js('window.__smokeHls.destroy();window.__smokeVideo.remove()')


def main():
    assert os.environ.get('CI') == 'true', 'CI only'
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    logs = (EVIDENCE / 'webdriver.log').open('w')
    wm = subprocess.Popen(['openbox'], stdout=logs, stderr=logs)
    driver = subprocess.Popen(['tauri-driver', '--native-driver', os.environ['HGHUB_NATIVE_DRIVER']],
                              stdout=logs, stderr=logs, start_new_session=True)
    session = None
    report = {'transport': 'Rust offline AES/HLS tests and real production hg:// rejection checks',
              'playback': 'production WebKitGTK engine; synthetic in-memory HLS loader', 'scales': []}
    try:
        wait(lambda: request('GET', '/status'), 'tauri-driver ready')
        session = Session()
        session.settings()
        initial_width = session.js('return innerWidth')
        for percent in (75, 100, 150, 200):
            session.scale(percent)
            expected = initial_width * 100 / percent
            wait(lambda: abs(session.js('return innerWidth') - expected) < 4, 'actual native zoom metric')
            session.screenshot('scale-' + str(percent))
            report['scales'].append(percent)
        session.scale(100)
        session.js("dispatchEvent(new KeyboardEvent('keydown',{key:'+',ctrlKey:true,bubbles:true,cancelable:true}))")
        wait(lambda: session.js('return innerWidth') < initial_width - 20, 'Ctrl+plus zoom')
        session.js("dispatchEvent(new KeyboardEvent('keydown',{key:'0',ctrlKey:true,bubbles:true,cancelable:true}))")
        wait(lambda: abs(session.js('return innerWidth') - initial_width) < 4, 'Ctrl+0 reset')
        session.js("dispatchEvent(new KeyboardEvent('keydown',{key:'-',ctrlKey:true,bubbles:true,cancelable:true}))")
        wait(lambda: session.js('return innerWidth') > initial_width + 20, 'Ctrl+minus zoom')
        session.scale(150)
        session.close()
        session = Session()
        wait(lambda: abs(session.js('return innerWidth') - initial_width / 1.5) < 4, 'restart restores zoom')
        session.js("localStorage.setItem('hghub_interface_scale','broken')")
        session.close()
        session = Session()
        wait(lambda: abs(session.js('return innerWidth') - initial_width) < 4, 'invalid saved zoom falls back to default')
        session.settings()
        session.scale(100)
        # Window controls go through the existing Tauri window ACL/IPC.
        session.click('button[aria-label="最大化"]')
        wait(lambda: session.js('return !!document.querySelector(\'button[aria-label="还原"]\')'), 'maximize')
        session.click('button[aria-label="还原"]')
        wait(lambda: session.js('return !!document.querySelector(\'button[aria-label="最大化"]\')'), 'restore')
        # Exercise actual registered custom scheme and network guard with no external requests.
        routes = session.async_js('''const done=arguments[arguments.length-1];
          Promise.all(['hg://localhost/unknown?u='+encodeURIComponent('https://fixture.invalid/none'),'hg://localhost/hls?u='+encodeURIComponent('http://127.0.0.1/private')]
          .map(async url=>{try{const r=await fetch(url);return {status:r.status,body:await r.text()}}catch(e){return {error:String(e)}}}))
          .then(done).catch(e=>done({error:String(e)}));''')
        assert routes[0].get('status') == 404, routes
        assert routes[1].get('status') == 502 and any(term in routes[1].get('body', '') for term in ('内网', '非公网', '私网', 'private', '不允许', '禁止', '拒绝')), routes
        report['protocol_checks'] = routes
        for percent in (75, 100, 150, 200):
            session.scale(percent)
            fixture_playback(session, percent)
        session.scale(100)
        assert session.js('return window.__smokeErrors') == []
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        if session:
            try:
                session.screenshot('failure')
            except Exception:
                pass
        raise
    finally:
        if session:
            try:
                session.close()
            except Exception:
                pass
        if driver.poll() is None:
            os.killpg(driver.pid, signal.SIGTERM)
            try:
                driver.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(driver.pid, signal.SIGKILL)
                driver.wait(timeout=5)
        if wm.poll() is None:
            wm.terminate()
            wm.wait(timeout=10)
        logs.close()
        (EVIDENCE / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('HGHUB_WEBKIT_SMOKE_OK ' + json.dumps(report))


if __name__ == '__main__':
    main()
