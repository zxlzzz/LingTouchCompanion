"""Portable vision build/test entry point. Python standard library only."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'apps/android-cs30-live'
BUILD=ROOT/'.build/vision'

def execute(args,log=None,cwd=None,env=None,timeout=300):
    result=subprocess.run(list(map(str,args)),cwd=cwd,env=env,capture_output=True,timeout=timeout)
    if log:
        Path(log).parent.mkdir(parents=True,exist_ok=True)
        Path(log).write_bytes(result.stdout+b'\n'+result.stderr)
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}); see {log}\n'+
            result.stdout.decode('utf-8','replace')[-5000:]+result.stderr.decode('utf-8','replace')[-3000:])
    return result.stdout.decode('utf-8','replace')

def executable(value,name):
    if value:
        p=Path(value).expanduser().resolve()
        if p.is_dir():p=p/'bin'/(name+'.exe' if os.name=='nt' else name)
        if not p.is_file():raise RuntimeError(f'Missing executable: {p}')
        return p
    result=shutil.which(name)
    return Path(result) if result else None

def properties():
    path=APP/'local.properties'
    if not path.exists():return {}
    result={}
    for line in path.read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1);result[k.strip()]=v.strip().replace('\\:',':').replace('\\\\','\\')
    return result

def configure(args):
    env=os.environ.copy();props=properties()
    sdk=args.sdk or env.get('ANDROID_HOME') or env.get('ANDROID_SDK_ROOT') or props.get('sdk.dir')
    if not sdk:raise RuntimeError('Set ANDROID_HOME or pass --sdk PATH')
    sdk=Path(sdk).expanduser().resolve()
    if not (sdk/'platform-tools').is_dir():raise RuntimeError(f'Invalid Android SDK: {sdk}')
    props['sdk.dir']=sdk.as_posix();env['ANDROID_HOME']=str(sdk)
    java=args.java_home or env.get('JAVA_HOME')
    if java:env['JAVA_HOME']=str(Path(java).expanduser().resolve())
    ndk=args.ndk or env.get('ANDROID_NDK_HOME') or props.get('cs30.ndk.path')
    if not ndk:
        candidate=sdk/'ndk/27.2.12479018'
        if candidate.is_dir():ndk=str(candidate)
    if ndk:
        ndk=Path(ndk).expanduser().resolve()
        if not (ndk/'build/cmake/android.toolchain.cmake').is_file():raise RuntimeError(f'Invalid NDK: {ndk}')
        props['cs30.ndk.path']=ndk.as_posix()
    cmake=executable(args.cmake,'cmake')
    if cmake:
        props['cmake.dir']=cmake.parent.parent.as_posix()
        version=execute([cmake,'--version']).splitlines()[0]
        props['cs30.cmake.version']=re.search(r'(\d+\.\d+\.\d+)',version).group(1)
    elif props.get('cmake.dir'):
        cmake=executable(props['cmake.dir'],'cmake')
    else:
        installed=sorted((sdk/'cmake').glob('*/bin/cmake*'))
        cmake=next((p for p in installed if p.is_file() and p.name in ['cmake','cmake.exe']),None)
    ninja=executable(args.ninja,'ninja')
    if ninja:props['cs30.ninja.path']=ninja.as_posix()
    elif props.get('cs30.ninja.path'):ninja=Path(props['cs30.ninja.path'])
    elif cmake and (cmake.parent/('ninja.exe' if os.name=='nt' else 'ninja')).is_file():
        ninja=cmake.parent/('ninja.exe' if os.name=='nt' else 'ninja')
    if cmake:env['PATH']=str(cmake.parent)+os.pathsep+env.get('PATH','')
    if ninja:env['PATH']=str(ninja.parent)+os.pathsep+env.get('PATH','')
    text='# Generated local machine settings; excluded from Git.\n'
    for k,v in props.items():text+=k+'='+v.replace('\\','/').replace(':','\\:')+'\n'
    (APP/'local.properties').write_text(text,encoding='utf-8')
    return env,sdk,Path(ndk) if ndk else None,cmake,ninja

def gradle(tasks,env,offline=False):
    env=env.copy()
    cached=None
    if offline:
        home=Path(env.get('GRADLE_USER_HOME',str(Path.home()/'.gradle')))
        cached=next(home.glob('wrapper/dists/gradle-8.14.3-bin/*/gradle-8.14.3/bin/gradle.bat'),None)
        if os.name!='nt':cached=next(home.glob('wrapper/dists/gradle-8.14.3-bin/*/gradle-8.14.3/bin/gradle'),None)
        if not cached:raise RuntimeError('Gradle 8.14.3 is not cached; run once online before using --offline')
    if cached and os.name=='nt':
        env['PATH']=str(cached.parent)+os.pathsep+env.get('PATH','')
        wrapper=['cmd.exe','/d','/c','gradle.bat']
    elif cached:wrapper=[str(cached)]
    else:wrapper=['cmd.exe','/d','/c','gradlew.bat'] if os.name=='nt' else ['sh','./gradlew']
    args=wrapper+['--no-daemon']+(['--offline'] if offline else [])+tasks
    print('Gradle:',', '.join(tasks),flush=True)
    output=execute(args,BUILD/'logs/gradle.log',APP,env)
    print('\n'.join(output.splitlines()[-16:]))

def fixtures():
    target=BUILD/'test-assets';target.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(ROOT/'tests/vision/fixtures/cs30-regression.zip') as z:
        for name in z.namelist():
            path=(target/name).resolve()
            if not path.is_relative_to(target.resolve()):raise RuntimeError('Invalid fixture archive path')
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(name))
    provenance=json.loads((target/'provenance.json').read_text())
    for name,wanted in provenance['files'].items():
        actual=hashlib.sha256((target/name).read_bytes()).hexdigest()
        if actual!=wanted:raise RuntimeError(f'Fixture checksum differs: {name}')

def prepare_android_tests(ndk,cmake,ninja,abis):
    if not ndk or not cmake or not ninja:raise RuntimeError('Tests require NDK, CMake and Ninja; pass --ndk/--cmake/--ninja')
    fixtures()
    strip=next((ndk/'toolchains/llvm/prebuilt').glob('*/bin/llvm-strip*'))
    for abi in abis:
        folder=BUILD/'native-tests'/abi
        execute([cmake,'-S',APP/'native','-B',folder,'-G','Ninja',f'-DCMAKE_MAKE_PROGRAM={ninja}',
                 f'-DCMAKE_TOOLCHAIN_FILE={ndk}/build/cmake/android.toolchain.cmake',f'-DANDROID_ABI={abi}',
                 '-DANDROID_PLATFORM=android-29','-DANDROID_STL=c++_static','-DCMAKE_BUILD_TYPE=Release',
                 '-DLINGTOUCH_VISION_TESTS=ON'],BUILD/f'logs/test-configure-{abi}.log')
        execute([cmake,'--build',folder,'--target','cs30_live_test','--parallel','4'],BUILD/f'logs/test-build-{abi}.log')
        dest=BUILD/'test-jni'/abi/'libcs30_live_test.so';dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(folder/'libcs30_live_test.so',dest)
        execute([strip,'--strip-unneeded',dest],BUILD/'logs/strip.log')

def android_test(args,env,sdk):
    if not args.serial:raise RuntimeError('Specify --serial for the target Android emulator')
    adb=sdk/'platform-tools'/('adb.exe' if os.name=='nt' else 'adb')
    command=lambda *rest:execute([adb,'-s',args.serial,*rest],timeout=180)
    command('install','-r',str(APP/'app/build/outputs/apk/debug/app-debug.apk'))
    command('install','-r',str(APP/'app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk'))
    text=command('shell','am','instrument','-w','com.lingtouch.cs30live.test/com.lingtouch.cs30live.LiveCheck')
    folder=BUILD/'test-results';folder.mkdir(parents=True,exist_ok=True)
    (folder/'instrumentation.txt').write_text(text,encoding='utf-8')
    result=None
    for match in re.finditer(r'\{',text):
        try:
            data,_=json.JSONDecoder().raw_decode(text[match.start():])
            if isinstance(data,dict) and 'passed' in data:result=data;break
        except json.JSONDecodeError:pass
    if not result or not result.get('passed'):raise RuntimeError('Instrumentation failed; see '+str(folder/'instrumentation.txt')+'\n'+text[-4000:])
    (folder/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Android regression passed:',len(result['checks']),'checks;',result['threshold_bits'],'K bits')
    for remote,local in [('cs30-live-stopped.png','stopped.png'),('usb-diagnostics.txt','usb-diagnostics.txt'),('ui-export.json','export.json')]:
        command('pull','/sdcard/Android/data/com.lingtouch.cs30live/files/'+remote,str(folder/local))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['configure','build','test'])
    for flag in ['sdk','ndk','java-home','cmake','ninja','serial']:parser.add_argument('--'+flag)
    parser.add_argument('--offline',action='store_true');parser.add_argument('--test-abi',action='append',choices=['x86_64','arm64-v8a'])
    parser.add_argument('--publish',action='store_true',help='Copy the newly built APK to deliverables after validation')
    args=parser.parse_args();BUILD.mkdir(parents=True,exist_ok=True)
    env,sdk,ndk,cmake,ninja=configure(args)
    if args.action=='configure':print(APP/'local.properties');return
    tasks=[':app:assembleDebug']
    if args.action=='test':
        prepare_android_tests(ndk,cmake,ninja,args.test_abi or ['x86_64'])
        tasks.append(':app:assembleDebugAndroidTest')
    gradle(tasks,env,args.offline)
    if args.action=='test':android_test(args,env,sdk)
    apk=APP/'app/build/outputs/apk/debug/app-debug.apk'
    if args.publish:
        if args.action!='test':raise RuntimeError('--publish requires a successful test run')
        out=ROOT/'deliverables/vision/android';out.mkdir(parents=True,exist_ok=True)
        shutil.copy2(apk,out/'cs30-live-1.2.apk')
        digest=hashlib.sha256(apk.read_bytes()).hexdigest()
        (out/'cs30-live-1.2.apk.sha256').write_text(digest+'  cs30-live-1.2.apk\n',encoding='ascii')
    print('APK:',apk)

if __name__=='__main__':main()
