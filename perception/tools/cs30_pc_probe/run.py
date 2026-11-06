"""Windows physical CS30 test with an externally supplied libusb DLL. No driver changes."""
from pathlib import Path
import argparse,os,re,shutil,sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from vision import ROOT,BUILD,execute,executable
from host_test import compiler_environment

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--usb-dll',required=True)
    p.add_argument('--cmake');p.add_argument('--ninja');p.add_argument('--compile-only',action='store_true');a=p.parse_args()
    if os.name!='nt':raise RuntimeError('This helper currently targets Windows libusbK/WinUSB')
    cmake=executable(a.cmake,'cmake');ninja=executable(a.ninja,'ninja')
    if not cmake or not ninja:raise RuntimeError('Provide CMake and Ninja on PATH or via --cmake/--ninja')
    dll=Path(a.usb_dll).expanduser().resolve()
    if not dll.is_file():raise RuntimeError('Missing external libusb DLL')
    env=compiler_environment();folder=BUILD/'pc-probe';folder.mkdir(parents=True,exist_ok=True)
    dump=shutil.which('dumpbin.exe',path=env['PATH']);lib=shutil.which('lib.exe',path=env['PATH'])
    if not dump or not lib:raise RuntimeError('MSVC Build Tools are required')
    names=re.findall(r'^\s+\d+\s+[0-9A-F]+\s+[0-9A-F]+\s+(libusb_\w+)\s*$',execute([dump,'/exports',dll]),re.M)
    if not names:raise RuntimeError('DLL has no expected libusb exports')
    definition=folder/'usb.def';definition.write_text('LIBRARY '+dll.name+'\nEXPORTS\n'+'\n'.join(names),encoding='ascii')
    library=folder/'usb.lib';execute([lib,'/nologo','/machine:x64',f'/def:{definition}',f'/out:{library}'],folder/'import.log',env=env)
    build=folder/'build'
    execute([cmake,'-S',HERE,'-B',build,'-G','Ninja',f'-DCMAKE_MAKE_PROGRAM={ninja}',
             f'-DCS30_USB_LIBRARY={library}','-DCMAKE_BUILD_TYPE=Release','-DCMAKE_TRY_COMPILE_CONFIGURATION=Release'],folder/'configure.log',env=env)
    execute([cmake,'--build',build,'--parallel','4'],folder/'build.log',env=env)
    shutil.copy2(dll,build/dll.name)
    if a.compile_only:print('Physical test tool compiled; camera was not opened.');return
    output=folder/'capture';output.mkdir(exist_ok=True)
    print('Running two physical start/capture/stop cycles...',flush=True)
    print(execute([build/'cs30_pc_probe.exe',output/'physical'],folder/'console.log',env=env,timeout=120))
    print(output/'physical.json')

if __name__=='__main__':main()
