"""Local fixed-command launcher. Attached processes are never stopped or adopted."""
import asyncio
import configparser
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import threading
import time
import urllib.request
import zipfile
import psutil
from app_runtime import component_command

PATHS=('llama_exe','model_file','factorio_exe','client_exe','server_config','server_mods',
       'server_settings','save_path','client_config','client_mods','mcp_server_dll','profile_root')


def normalized(path):
    return os.path.normcase(str(Path(path).resolve()))


def flag_value(args,flag):
    try:return args[args.index(flag)+1]
    except (ValueError,IndexError):return None


class Profile:
    def __init__(self,path):
        self.path=Path(path).resolve()
        self.data=json.loads(self.path.read_text(encoding='utf-8-sig'))
        allowed=set(PATHS)|{'game_port','rcon_port','llm_port','world_id','dotnet_command','secret_file','game_mode','test_profile'}
        if set(self.data)-allowed:raise ValueError('Unknown setup fields')
        if self.data.get('test_profile') is not True:raise ValueError('An explicitly isolated test profile is required')
        if self.data.get('game_mode','graphical-host') not in ('graphical-host','dedicated'):raise ValueError('Unsupported game mode')
        self.data.setdefault('game_mode','graphical-host')
        for key in PATHS:
            p=Path(self.data[key]);p=p if p.is_absolute() else self.path.parent/p
            if not p.exists():raise ValueError('Missing setup path: '+key)
            self.data[key]=str(p.resolve())
        for key in ('game_port','rcon_port','llm_port'):
            if type(self.data.get(key)) is not int or not 1024<=self.data[key]<=65535:
                raise ValueError('Invalid service port')
        if len({self.data[k] for k in ('game_port','rcon_port','llm_port')})!=3:
            raise ValueError('Service ports must be distinct')
        if not isinstance(self.data.get('world_id'),str) or not self.data['world_id'].strip():
            raise ValueError('World identifier required')
        root=Path(self.data['profile_root'])
        for key in ('server_config','server_settings','save_path','client_config'):
            if not Path(self.data[key]).is_relative_to(root):raise ValueError('Game profile must be isolated')
        for key in ('server_config','client_config'):
            ini=configparser.ConfigParser();ini.read(self.data[key],encoding='utf-8-sig')
            write=Path(ini['path']['write-data']).resolve()
            if not write.is_relative_to(root):raise ValueError('Game write-data must stay in the isolated profile')
            if key=='server_config' and Path(self.data['save_path']).parent!=write/'saves':
                raise ValueError('Save must be in the isolated server write-data saves folder')
        if not all(c.isalnum() or c in '-_' for c in Path(self.data['save_path']).stem):
            raise ValueError('Unsupported save name')
        settings=json.loads(Path(self.data['server_settings']).read_text(encoding='utf-8-sig'))
        if settings.get('visibility',{}).get('public') is not False or settings.get('visibility',{}).get('lan') is not False:
            raise ValueError('Test host must not be publicly listed or LAN advertised')
        with zipfile.ZipFile(self.data['save_path']) as archive:
            if archive.testzip() is not None:raise ValueError('Test save failed integrity check')
        self.runtime=root/'.local/launcher';self.runtime.mkdir(parents=True,exist_ok=True)
        secret_path=self.data.get('secret_file')
        if secret_path:
            p=Path(secret_path);p=p if p.is_absolute() else self.path.parent/p
            self.password=json.loads(p.read_text(encoding='utf-8-sig'))['rcon_password']
        else:
            p=self.runtime/'rcon.secret.json'
            if not p.exists():p.write_text(json.dumps({'rcon_password':secrets.token_urlsafe(32)}))
            self.password=json.loads(p.read_text())['rcon_password']
        if not isinstance(self.password,str) or not self.password:raise ValueError('RCON secret missing')
        if self.data['game_mode']=='graphical-host':
            ini=configparser.ConfigParser();ini.read(self.data['client_config'],encoding='utf-8-sig')
            if Path(ini['path']['write-data']).resolve()!=Path(self.data['save_path']).parent.parent:
                raise ValueError('Graphical host must use the isolated save data directory')
            if ini.get('other','local-rcon-socket',fallback='')!=f"127.0.0.1:{self.data['rcon_port']}":
                raise ValueError('Configure graphical host loopback RCON in its private INI')
            if ini.get('other','local-rcon-password',fallback='')!=self.password:
                raise ValueError('Graphical host RCON secret does not match private setup')
        self.identity=hashlib.sha256((self.data['save_path']+self.data['world_id']).encode()).hexdigest()[:20]


class Rcon:
    def __init__(self,port,password):
        self.sock=socket.create_connection(('127.0.0.1',port),timeout=3);self.sock.settimeout(3);self.ident=1
        try:
            self.send(3,password)
            for _ in range(6):
                ident,kind,_=self.receive()
                if ident==-1:raise ConnectionError('RCON authentication failed')
                if ident==self.ident and kind==2:break
            else:raise ConnectionError('RCON authentication not acknowledged')
        except Exception:
            self.sock.close();raise

    def exact(self,count):
        data=b''
        while len(data)<count:
            part=self.sock.recv(count-len(data))
            if not part:raise ConnectionError('RCON closed')
            data+=part
        return data

    def send(self,kind,text):
        self.ident+=1;p=struct.pack('<ii',self.ident,kind)+text.encode()+b'\0\0'
        self.sock.sendall(struct.pack('<i',len(p))+p)

    def receive(self):
        size=struct.unpack('<i',self.exact(4))[0]
        if not 10<=size<=2097152:raise ValueError('Invalid RCON reply')
        p=self.exact(size);return *struct.unpack('<ii',p[:8]),p[8:-2].decode()

    def command(self,text):
        self.send(2,text)
        for _ in range(10):
            ident,_,body=self.receive()
            if ident==self.ident:return body.strip()
        raise ConnectionError('RCON response missing')

    def health(self):
        return json.loads(self.command('/silent-command local p=game.connected_players[1];rcon.print(helpers.table_to_json({players=#game.connected_players,character=p and p.character~=nil,tick=game.tick,stopped=not storage.autoengineer_safety or storage.autoengineer_safety.stopped,walking=p and p.character and p.character.walking_state.walking,x=p and p.character and p.character.position.x,y=p and p.character and p.character.position.y,game_speed=game.speed,speed_modifier=p and p.character_running_speed_modifier}))'))

    def close(self):self.sock.close()


class Supervisor:
    def __init__(self,profile,notify=lambda *args:None):
        self.profile=profile;self.p=profile.data;self.notify=notify;self.owned={};self.attached={}
        self.cancel=threading.Event();self.busy=threading.Lock();self.lock_file=None;self.last={};self.dashboard_status=None;self.runtime_env=None;self.started=False

    def status(self,name,text):
        self.last[name]=text;self.notify(name,text)

    def acquire(self):
        if self.lock_file is not None:return
        import msvcrt
        f=(self.profile.runtime/'launcher.lock').open('a+b');f.seek(0);f.write(b'0');f.flush();f.seek(0)
        try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:f.close();raise RuntimeError('Another launcher is using this profile') from None
        self.lock_file=f

    def release(self):
        if self.lock_file:
            import msvcrt
            self.lock_file.seek(0);msvcrt.locking(self.lock_file.fileno(),msvcrt.LK_UNLCK,1)
            self.lock_file.close();self.lock_file=None

    def processes(self,exe):
        found=[]
        for p in psutil.process_iter(['pid','exe','cmdline','create_time']):
            try:
                if p.info['exe'] and normalized(p.info['exe'])==normalized(exe):found.append(p)
            except (psutil.Error,OSError):pass
        return found

    def matching(self,exe,flag,value):
        return [p for p in self.processes(exe) if flag_value(p.info['cmdline'] or [],flag) is not None and
                normalized(flag_value(p.info['cmdline'],flag))==normalized(value)]

    def spawn(self,name,args,env=None,cwd=None):
        if self.cancel.is_set():raise RuntimeError('Startup cancelled')
        existing=self.owned.get(name)
        if existing is not None and existing.poll() is None:raise RuntimeError('Owned service already running')
        log=(self.profile.runtime/(name+'.private.log')).open('ab')
        try:
            proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=log,stderr=log,env=env,cwd=cwd,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        finally:log.close()
        self.owned[name]=proc;self.status(name,'Starting (launcher-owned)');return proc

    def wait(self,predicate,seconds,name):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if self.cancel.is_set():raise RuntimeError('Startup cancelled')
            try:
                result=predicate()
                if result:return result
            except (OSError,ValueError,ConnectionError,KeyError):pass
            if name in self.owned and self.owned[name].poll() is not None:raise RuntimeError(name+' exited; inspect its local private log')
            self.cancel.wait(.4)
        raise RuntimeError(name+' readiness timed out')

    def models(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.p['llm_port']}/v1/models",timeout=2) as response:
            data=json.loads(response.read(1048576))
        ids=[x.get('id') for x in data.get('data',[]) if isinstance(x,dict)]
        if len(ids)!=1 or not isinstance(ids[0],str) or not ids[0]:raise ValueError('Expected one selected local model')
        return ids[0]

    def game(self):
        r=Rcon(self.p['rcon_port'],self.profile.password)
        try:return r.health()
        finally:r.close()

    def port_open(self,port):
        # A free Windows loopback port may time out on connect rather than refuse.
        # Test exclusive binding, so a timeout cannot be mistaken for readiness.
        import errno
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
            if os.name=='nt':probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            try:probe.bind(('127.0.0.1',port));return False
            except OSError as exc:
                if exc.errno==errno.EADDRINUSE or getattr(exc,'winerror',None)==10048:return True
                raise RuntimeError('Service port cannot be safely reserved') from None

    def save_owned_game(self):
        first=self.game();time.sleep(.2);second=self.game()
        if second.get('players')!=1 or not second.get('stopped') or second.get('walking') or (first.get('x'),first.get('y'))!=(second.get('x'),second.get('y')):
            raise RuntimeError('Test character is not confirmed stopped; game left running')
        save=Path(self.p['save_path']);before=save.stat().st_mtime_ns
        r=Rcon(self.p['rcon_port'],self.profile.password)
        try:r.command('/server-save '+save.stem)
        finally:r.close()
        end=time.monotonic()+20
        while time.monotonic()<end:
            try:
                if save.stat().st_mtime_ns>before:
                    with zipfile.ZipFile(save) as archive:
                        if archive.testzip() is None:return
            except (OSError,zipfile.BadZipFile):pass
            time.sleep(.25)
        raise RuntimeError('Test save integrity not confirmed; game left running')

    def refresh_health(self):
        if not self.started or not self.busy.acquire(False):return
        try:
            try:
                health=self.game()
                if health.get('players')!=1 or not health.get('character'):raise ValueError()
            except Exception:
                self.status('server','Disconnected: stop gameplay before reconnecting')
                self.status('client','Unavailable: check test host')
            try:self.models()
            except Exception:self.status('llama','Unavailable: local model is not ready')
            if self.dashboard_status:
                try:
                    d=json.loads(self.dashboard_status.read_text())
                    if not d.get('live') or time.time()-self.dashboard_status.stat().st_mtime>6:raise ValueError()
                except Exception:self.status('dashboard','Unavailable: live observation lost')
        finally:self.busy.release()

    def start_all(self):
        if not self.busy.acquire(False):return
        try:
            self.acquire()
            if self.cancel.is_set():raise RuntimeError('Startup cancelled')
            if self.owned.get('dashboard') is not None and self.owned['dashboard'].poll() is None:
                self.status('dashboard','Already running (owned)');return
            if self.p['game_mode']=='graphical-host':
                hosts=self.matching(self.p['client_exe'],'--host',self.p['save_path'])
                if hosts:
                    args=hosts[0].info['cmdline'] or []
                    if len(hosts)!=1 or normalized(flag_value(args,'--config') or '')!=normalized(self.p['client_config']) or normalized(flag_value(args,'--mod-directory') or '')!=normalized(self.p['client_mods']) or normalized(flag_value(args,'--server-settings') or '')!=normalized(self.p['server_settings']):
                        raise RuntimeError('Existing graphical host does not match this test setup')
                    if not ('host' in self.owned and self.owned['host'].poll() is None and self.owned['host'].pid==hosts[0].pid):
                        self.attached['host']=hosts[0]
                    self.status('server','Attached to test host (not owned)' if 'host' in self.attached else 'Ready: owned graphical host')
                else:
                    if self.processes(self.p['client_exe']):raise RuntimeError('Factorio is already running with another profile')
                    if self.port_open(self.p['rcon_port']):raise RuntimeError('RCON port is already occupied')
                    env=dict(os.environ,SteamAppId='427520',SteamGameId='427520')
                    self.spawn('host',[self.p['client_exe'],'--config',self.p['client_config'],'--mod-directory',self.p['client_mods'],
                        '--host',self.p['save_path'],'--server-settings',self.p['server_settings']],env=env,cwd=str(Path(self.p['client_exe']).parent))
                self.wait(lambda:self.game().get('players')==1 and self.game().get('character'),60,'host')
                ownership='owned' if 'host' in self.owned and self.owned['host'].poll() is None else 'attached'
                self.status('server','Ready: graphical multiplayer host; '+ownership)
                self.status('client','Ready: same test save; '+ownership)
            else:
                # Refuse a different server or model bound to this profile's selected ports.
                servers=self.matching(self.p['factorio_exe'],'--start-server',self.p['save_path'])
                if servers:
                    if len(servers)!=1 or any(flag_value(servers[0].info['cmdline'],flag)!=value for flag,value in [('--rcon-bind',f"127.0.0.1:{self.p['rcon_port']}"),('--bind',f"127.0.0.1:{self.p['game_port']}")]) or normalized(flag_value(servers[0].info['cmdline'],'--config') or '')!=normalized(self.p['server_config']):
                        raise RuntimeError('Existing server profile does not match this setup')
                    self.attached['server']=servers[0];self.status('server','Attached to selected test save (not owned)')
                else:
                    try:
                        with socket.create_connection(('127.0.0.1',self.p['rcon_port']),timeout=.3):pass
                    except OSError:pass
                    else:raise RuntimeError('RCON port is already occupied by another service')
                    self.spawn('server',[self.p['factorio_exe'],'--config',self.p['server_config'],'--mod-directory',self.p['server_mods'],
                        '--start-server',self.p['save_path'],'--bind',f"127.0.0.1:{self.p['game_port']}",'--rcon-bind',f"127.0.0.1:{self.p['rcon_port']}",
                        '--rcon-password',self.profile.password,'--server-settings',self.p['server_settings']])
                self.wait(self.game,35,'server')
                clients=[p for p in self.matching(self.p['client_exe'],'--config',self.p['client_config']) if
                         flag_value(p.info['cmdline'],'--mp-connect')==f"127.0.0.1:{self.p['game_port']}"]
                if clients:
                    if len(clients)!=1:raise RuntimeError('Multiple clients match this profile')
                    self.attached['client']=clients[0];self.status('client','Attached to test client (not owned)')
                else:
                    other=[p for p in self.processes(self.p['client_exe']) if '--start-server' not in (p.info['cmdline'] or [])]
                    if other:raise RuntimeError('Factorio client is already running with another profile')
                    env=dict(os.environ,SteamAppId='427520',SteamGameId='427520')
                    self.spawn('client',[self.p['client_exe'],'--config',self.p['client_config'],'--mod-directory',self.p['client_mods'],
                        '--mp-connect',f"127.0.0.1:{self.p['game_port']}"],env=env,cwd=str(Path(self.p['client_exe']).parent))
                self.wait(lambda:self.game().get('character'),45,'client')
                self.status('server','Ready: selected save; '+('owned' if 'server' in self.owned else 'attached'))
                self.status('client','Ready: connected character; '+('owned' if 'client' in self.owned else 'attached'))
            models=self.matching(self.p['llama_exe'],'--model',self.p['model_file'])
            if models:
                if len(models)!=1 or flag_value(models[0].info['cmdline'],'--port')!=str(self.p['llm_port']) or flag_value(models[0].info['cmdline'],'--host')!='127.0.0.1':
                    raise RuntimeError('Existing llama.cpp profile does not match')
                self.attached['llama']=models[0];self.status('llama','Attached to selected model (not owned)')
            else:
                try:
                    with socket.create_connection(('127.0.0.1',self.p['llm_port']),timeout=.3):pass
                except OSError:pass
                else:raise RuntimeError('Model port is already occupied')
                self.spawn('llama',[self.p['llama_exe'],'--model',self.p['model_file'],'--host','127.0.0.1','--port',str(self.p['llm_port']),
                    '--ctx-size','4096','--n-gpu-layers','99','--alias','autoengineer-local'],cwd=str(Path(self.p['llama_exe']).parent))
            model=self.wait(self.models,120,'llama');self.status('llama','Ready: model API; '+('owned' if 'llama' in self.owned else 'attached'))
            config=dict(dotnet_command=self.p.get('dotnet_command','dotnet'),mcp_server_dll=self.p['mcp_server_dll'],rcon_host='127.0.0.1',
                rcon_port=self.p['rcon_port'],llm_api_url=f"http://127.0.0.1:{self.p['llm_port']}/v1",llm_model=model)
            config_path=self.profile.runtime/'agent.config.private.json';config_path.write_text(json.dumps(config))
            self.dashboard_status=self.profile.runtime/('dashboard-'+secrets.token_hex(8)+'.private.json')
            env=dict(os.environ,AUTOENGINEER_CONFIG=str(config_path),AUTOENGINEER_HOME=str(self.profile.runtime),
                FACTORIO_RCON_PASSWORD=self.profile.password,AUTOENGINEER_WORLD=self.p['world_id'],AUTOENGINEER_MODE='helper',
                AUTOENGINEER_LAUNCHER_STATUS=str(self.dashboard_status))
            self.runtime_env=env
            result=subprocess.run(component_command('backend_check'),env=env,cwd=str(self.profile.runtime),
                capture_output=True,timeout=20,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            if result.returncode or b'POLICY_7_VERIFIED' not in result.stdout:
                raise RuntimeError('Restricted backend policy 7 readiness check failed')
            self.status('mcp','Ready: policy 7; five-tile boundary verified')
            if 'dashboard' not in self.owned or self.owned['dashboard'].poll() is not None:
                self.spawn('dashboard',component_command('dashboard'),env=env,cwd=str(self.profile.runtime))
            def ready():
                if not self.dashboard_status.exists():return False
                d=json.loads(self.dashboard_status.read_text());return d.get('live') and time.time()-self.dashboard_status.stat().st_mtime<5
            self.wait(ready,35,'dashboard');self.status('dashboard','Ready: live Helper dashboard (owned)')
            self.started=True
        except Exception as exc:
            # Known launcher messages only; never display commands, credentials or tracebacks.
            self.status('error',str(exc) if isinstance(exc,RuntimeError) else 'Setup/startup failed; check selected paths and private logs')
            raise
        finally:self.busy.release()

    def request_dashboard_stop(self):
        p=self.owned.get('dashboard')
        if p and p.poll() is None:
            try:p.stdin.write(b'q\n');p.stdin.flush()
            except (OSError,ValueError):pass
            try:p.wait(timeout=20)
            except subprocess.TimeoutExpired:raise RuntimeError('Dashboard has not stopped safely; services left running') from None
        if self.dashboard_status and self.dashboard_status.exists():
            d=json.loads(self.dashboard_status.read_text())
            if d.get('ever_active') and not d.get('stop_confirmed'):
                raise RuntimeError('Game-side stop unconfirmed; services left running')

        self.started=False
        self.status('mcp','Stopped: dashboard transport closed')
        self.status('dashboard','Stopped by request')

    def stop_owned(self,include_game=False):
        self.cancel.set()
        with self.busy:
            self.request_dashboard_stop()
            game_name='host' if self.p['game_mode']=='graphical-host' else 'server'
            if include_game and game_name in self.owned and self.owned[game_name].poll() is None:
                self.save_owned_game()
                # Only a saved, stationary launcher-owned game may be closed.
                r=Rcon(self.p['rcon_port'],self.profile.password)
                try:r.command('/quit')
                except (OSError,ConnectionError):pass
                finally:r.close()
                try:self.owned[game_name].wait(timeout=3)
                except subprocess.TimeoutExpired:
                    if game_name!='host':raise RuntimeError('Server did not quit; left running') from None
                    # Graphical hosts may not support /quit. A verified saved test host
                    # can be closed under the explicit Stop owned services command.
                    self.owned[game_name].terminate();self.owned[game_name].wait(timeout=8)
                self.status('server','Stopped: test save verified')
                self.status('client','Stopped: launcher-owned game')
            # Explicit stop request permits closing only client/model processes spawned here.
            for name in (('client','llama') if include_game else ('llama',)):
                p=self.owned.get(name)
                if p and p.poll() is None:p.terminate();p.wait(timeout=8)
            self.started=False
            self.status('mcp','Stopped: dashboard transport closed')
            self.status('dashboard','Stopped (game-side cleanup checked)')
            self.status('llama','Stopped' if 'llama' in self.owned else 'Attached service left running')
