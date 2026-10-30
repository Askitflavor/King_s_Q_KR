"""Portable offline patch manager. Windows GUI and Linux/ARM64 CLI share this engine."""
import argparse,contextlib,csv,io,json,os,re,shutil,subprocess,sys,time,zipfile
from pathlib import Path,PurePosixPath
from patch_codec import sha,apply_delta,package_raw,semantic_sha
BASE=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
STATE_DIR='.kq-ko-patch'

def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp')
    with tmp.open('w',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

def read_json(path):return json.loads(path.read_text(encoding='utf-8'))

def safe_target(root,relative):
    if root.is_symlink():raise ValueError('Symlinked asset/backup roots are not supported')
    p=PurePosixPath(relative)
    if p.is_absolute() or '\\' in relative or ':' in relative or '..' in p.parts or not p.parts:raise ValueError('Unsafe path')
    allowed=relative.startswith('GrahamsGame/') or re.match(r'^DLC/E[1-6]/Content/GrahamsGame/',relative)
    if not allowed or p.suffix.lower() not in ('.int','.upk'):raise ValueError('Unexpected game asset')
    result=root.joinpath(*p.parts)
    if root.resolve() not in result.resolve().parents:raise ValueError('Path escapes game directory')
    if any(part.is_symlink() for part in [result]+list(result.parents) if part!=root):raise ValueError('Symlinked targets are not supported')
    return result

def game_running():
    if os.name=='nt':
        p=subprocess.run(['tasklist','/FI','IMAGENAME eq KingsQuest.exe','/FO','CSV','/NH'],capture_output=True,text=True,errors='replace',creationflags=0x08000000)
        if p.returncode:raise RuntimeError('Cannot check running game processes')
        return any(r and r[0].lower()=='kingsquest.exe' for r in csv.reader(io.StringIO(p.stdout)))
    proc=Path('/proc')
    if not proc.is_dir():return False
    for p in proc.iterdir():
        if not p.name.isdigit() or int(p.name)==os.getpid():continue
        try:
            args=(p/'cmdline').read_bytes().split(b'\0')
            if any(a.replace(b'\\',b'/').split(b'/')[-1].lower()==b'kingsquest.exe' for a in args):return True
        except (OSError,PermissionError):continue
    return False

def locate_games():
    roots=[]
    if os.name=='nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Valve\Steam') as key:roots.append(Path(winreg.QueryValueEx(key,'SteamPath')[0]))
        except OSError:pass
        roots.extend([Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Steam'])
        for drive in 'CDEFGHIJKLMNOPQRSTUVWXYZ':roots.extend([Path(drive+':/SteamLibrary'),Path(drive+':/Steam')])
    roots.extend([Path.home()/'.local/share/Steam',Path.home()/'.steam/steam',Path.home()/'.var/app/com.valvesoftware.Steam/data/Steam'])
    found=[]
    for root in list(roots):
        vdf=root/'steamapps/libraryfolders.vdf'
        if vdf.is_file():
            roots.extend(Path(p.replace('\\\\','\\')) for p in re.findall(r'"path"\s+"([^"]+)"',vdf.read_text(encoding='utf-8',errors='replace')))
    for root in roots:
        path=root/"steamapps/common/King's Quest"
        if (path/'GrahamsGame').is_dir() and path.resolve() not in found:found.append(path.resolve())
    return found

class Manager:
    def __init__(self,game,bundle=BASE,log=print):
        self.game=Path(game).resolve();self.bundle=Path(bundle).resolve();self.log=log
        if not (self.game/'GrahamsGame').is_dir():raise ValueError("Select the King's Quest game folder containing GrahamsGame")
        self.manifest=read_json(self.bundle/'manifest.json')
        if self.manifest['format']!=1:raise ValueError('Unsupported patch manifest')
        paths=[r['path'] for r in self.manifest['files']]
        if len(paths)!=len(set(paths)):raise ValueError('Duplicate manifest paths')
        for rel in paths:safe_target(self.game,rel)
        self.home=self.game/STATE_DIR
        if self.home.is_symlink():raise ValueError('Backup directory must not be a symlink')
        self.statepath=self.home/'state.json';self.journal=self.home/'pending.json'

    def selected(self,chapters=None):
        if chapters is None:chapters={i for i in range(1,7) if (self.game/f'DLC/E{i}/Content/GrahamsGame/CookedPCConsole').is_dir()}
        if not chapters:raise ValueError('No installed chapter DLC directories found')
        return [r for r in self.manifest['files'] if r['chapter']==0 or r['chapter'] in chapters]

    def state(self):
        if not self.statepath.exists():return {'phase':'new','files':[]}
        state=read_json(self.statepath)
        for r in state['files']:safe_target(self.game,r['path'])
        return state

    def match_target(self,data,r):
        if sha(data)==r['target_sha256']:return True
        return r['codec']=='ue3-raw-bsdiff40-zlib' and semantic_sha(package_raw(data))==r['target_semantic_sha256']

    def scan(self,chapters=None):
        result=[];stored={r['path']:r for r in self.state()['files']}
        for r in self.selected(chapters):
            p=safe_target(self.game,r['path']);status='missing'
            if p.is_file():
                data=p.read_bytes();h=sha(data)
                if h==r['original_sha256']:status='original'
                elif r['path'] in stored and h==stored[r['path']]['patched_sha256']:status='patched'
                else:
                    try:status='patched' if self.match_target(data,r) else 'different'
                    except (ValueError,RuntimeError,IndexError):status='different'
            result.append({'path':r['path'],'status':status})
        return result

    @contextlib.contextmanager
    def lock(self):
        if game_running():raise RuntimeError('Close the game before installing/restoring')
        self.home.mkdir(parents=True,exist_ok=True);lock=self.home/'operation.lock'
        try:
            with lock.open('x',encoding='ascii') as f:f.write(str(os.getpid()))
        except FileExistsError:raise RuntimeError('Another operation or interrupted run exists. Close the other patcher, then use recover.')
        try:yield
        finally:lock.unlink(missing_ok=True)

    def install(self,chapters=None):
        with self.lock():
            if self.journal.exists():raise RuntimeError('Interrupted operation found; run recover first')
            records=self.selected(chapters);statuses={r['path']:r['status'] for r in self.scan(chapters)}
            bad=[p for p,s in statuses.items() if s in ('missing','different')]
            if bad:raise ValueError('Unsupported/missing files; nothing changed:\n'+'\n'.join(bad[:12]))
            todo=[r for r in records if statuses[r['path']]=='original']
            if not todo:self.log('Already patched. No files changed.');return
            managed={r['path'] for r in self.state()['files']}
            if any(statuses[r['path']]=='patched' and r['path'] not in managed for r in records):
                raise ValueError('Mixed prepatched assets without this installer backup. Use a clean game installation; no files changed.')
            if shutil.disk_usage(self.game).free<sum(r['original_size']+r['target_size'] for r in todo)+64*1024*1024:raise RuntimeError('Insufficient free disk space for backups and staging')
            state=self.state();previous={r['path']:r for r in state['files']};planned=[]
            with zipfile.ZipFile(self.bundle/'patch-data.zip') as payload:
                for i,r in enumerate(todo,1):
                    rel=r['path'];source=safe_target(self.game,rel).read_bytes()
                    if sha(source)!=r['original_sha256']:raise ValueError('File changed during preparation')
                    backup=safe_target(self.home/'original',rel);backup.parent.mkdir(parents=True,exist_ok=True)
                    if backup.exists():
                        if sha(backup.read_bytes())!=r['original_sha256']:raise ValueError('Original backup hash mismatch')
                    else:
                        temp=backup.with_suffix(backup.suffix+'.tmp');shutil.copy2(safe_target(self.game,rel),temp);os.replace(temp,backup)
                    if sha(backup.read_bytes())!=r['original_sha256']:raise ValueError('Backup verification failed before installation')
                    result=apply_delta(source,payload.read(r['delta']),r)
                    stage=safe_target(self.home/'stage',rel);stage.parent.mkdir(parents=True,exist_ok=True);stage.write_bytes(result)
                    entry={'path':rel,'original_sha256':r['original_sha256'],'patched_sha256':sha(result)}
                    planned.append(entry);previous[rel]=entry
                    self.log(f'Preparing {i}/{len(todo)}: {rel}')
            write_json(self.journal,{'operation':'install','files':planned,'previous_state':state})
            changed=[]
            try:
                for r in planned:
                    dest=safe_target(self.game,r['path'])
                    if sha(dest.read_bytes())!=r['original_sha256']:raise ValueError('Game file changed before commit')
                    os.replace(safe_target(self.home/'stage',r['path']),dest);changed.append(r)
                    if sha(dest.read_bytes())!=r['patched_sha256']:raise ValueError('Installed file hash mismatch')
                write_json(self.statepath,{'release':self.manifest['release'],'phase':'installed','files':list(previous.values())})
            except BaseException:
                self.rollback(changed,'original_sha256','original');self.journal.unlink();raise
            self.journal.unlink();self.log(f'Installed {len(planned)} files; original backups: {self.home}')

    def rollback(self,records,hashkey,folder):
        for r in records:
            source=safe_target(self.home/folder,r['path'])
            if sha(source.read_bytes())!=r[hashkey]:raise RuntimeError('Rollback backup verification failed; keep backup folder')
            dest=safe_target(self.game,r['path']);temp=dest.with_suffix(dest.suffix+'.kqtmp');shutil.copy2(source,temp);os.replace(temp,dest)

    def restore(self):
        with self.lock():
            if self.journal.exists():raise RuntimeError('Run recover before restore')
            state=self.state();records=state['files']
            if not records:raise ValueError('No backups created by this distribution installer. Do not restore the development patch with this tool.')
            for r in records:
                dest=safe_target(self.game,r['path']);backup=safe_target(self.home/'original',r['path'])
                if not backup.is_file() or sha(backup.read_bytes())!=r['original_sha256']:raise ValueError('Backup missing or changed')
                h=sha(dest.read_bytes())
                if h not in (r['original_sha256'],r['patched_sha256']):raise ValueError('Game modified after patch: '+r['path'])
            todo=[r for r in records if sha(safe_target(self.game,r['path']).read_bytes())!=r['original_sha256']]
            for r in todo:
                dest=safe_target(self.home/'restore',r['path']);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(safe_target(self.game,r['path']),dest)
            write_json(self.journal,{'operation':'restore','files':todo,'previous_state':state})
            try:
                self.rollback(todo,'original_sha256','original')
                write_json(self.statepath,{**state,'phase':'restored'})
            except BaseException:
                self.rollback(todo,'patched_sha256','restore');self.journal.unlink();raise
            self.journal.unlink();self.log(f'Restored {len(todo)} original files. Backups retained.')

    def recover(self):
        # Recover stale locks only after verifying the recorded process is gone.
        lock=self.home/'operation.lock'
        if lock.exists():
            pid=int(lock.read_text())
            if os.name=='nt':
                p=subprocess.run(['tasklist','/FI',f'PID eq {pid}','/FO','CSV','/NH'],capture_output=True,text=True,creationflags=0x08000000)
                alive=any(len(r)>1 and r[1]==str(pid) for r in csv.reader(io.StringIO(p.stdout)))
            else:alive=Path(f'/proc/{pid}').exists()
            if alive:raise RuntimeError('Recorded patcher process is still active')
            lock.unlink()
        with self.lock():
            if not self.journal.exists():self.log('No pending transaction.');return
            journal=read_json(self.journal)
            if journal['operation'] not in ('install','restore'):raise ValueError('Invalid recovery journal')
            records=journal['files'];install=journal['operation']=='install'
            for r in records:
                current=sha(safe_target(self.game,r['path']).read_bytes())
                if current not in (r['original_sha256'],r['patched_sha256']):raise ValueError('File changed after interruption; refusing overwrite')
            self.rollback(records,'original_sha256' if install else 'patched_sha256','original' if install else 'restore')
            write_json(self.statepath,journal['previous_state']);self.journal.unlink();self.log('Interrupted operation rolled back.')

def cli():
    parser=argparse.ArgumentParser(description='King\'s Quest Korean test patch: install, verify, restore, recover')
    parser.add_argument('action',choices=['install','verify','restore','recover']);parser.add_argument('--game',type=Path,required=True)
    parser.add_argument('--chapters',help='Optional installed chapters, e.g. 1,2,6 (6 = epilogue)');parser.add_argument('--bundle',type=Path,default=BASE)
    args=parser.parse_args();chapters=None
    if args.chapters:
        chapters={int(c) for c in args.chapters.split(',')}
        if not chapters or not chapters.issubset(set(range(1,7))):parser.error('chapters must be 1..6')
    mgr=Manager(args.game,args.bundle)
    if args.action=='verify':
        result=mgr.scan(chapters);counts={k:sum(r['status']==k for r in result) for k in ('original','patched','missing','different')}
        print(json.dumps({'release':mgr.manifest['release'],'files':len(result),'counts':counts,'details':[r for r in result if r['status'] in ('missing','different')]},ensure_ascii=False,indent=2))
        return 0 if not counts['missing'] and not counts['different'] else 2
    getattr(mgr,args.action)(chapters) if args.action=='install' else getattr(mgr,args.action)()
    return 0

if __name__=='__main__':
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='replace')
    try:sys.exit(cli())
    except Exception as exc:print('ERROR:',exc,file=sys.stderr);sys.exit(1)
