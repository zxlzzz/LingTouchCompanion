"""Build and run native core tests without an Android SDK or model weights."""
from pathlib import Path
import argparse,os,shutil,subprocess,sys
from vision import ROOT,BUILD,execute,executable

def compiler_environment():
    env=os.environ.copy()
    if os.name=='nt' and not env.get('INCLUDE'):
        installer=Path(env.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Microsoft Visual Studio/Installer/vswhere.exe'
        if installer.is_file():
            vs=execute([installer,'-latest','-products','*','-requires','Microsoft.VisualStudio.Component.VC.Tools.x86.x64','-property','installationPath']).strip()
            if vs:
                setup=Path(vs)/'Common7/Tools/VsDevCmd.bat'
                result=subprocess.run(f'cmd.exe /d /s /c ""{setup}" -arch=amd64 -host_arch=amd64 >nul && set"',capture_output=True)
                if result.returncode:raise RuntimeError('Visual Studio toolchain environment initialization failed')
                for line in result.stdout.decode('utf-8','replace').splitlines():
                    if '=' in line:
                        k,v=line.split('=',1)
                        if k:env[k.upper()]=v
    return env

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cmake');p.add_argument('--ninja');a=p.parse_args()
    cmake=executable(a.cmake,'cmake');ninja=executable(a.ninja,'ninja')
    if not cmake:raise RuntimeError('Install CMake or pass --cmake PATH')
    env=compiler_environment()
    folder=BUILD/'host'
    args=[cmake,'-S',ROOT/'core','-B',folder,'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_TRY_COMPILE_CONFIGURATION=Release',f'-DPython3_EXECUTABLE={sys.executable}']
    if ninja:args+=['-G','Ninja',f'-DCMAKE_MAKE_PROGRAM={ninja}']
    execute(args,BUILD/'logs/host-configure.log',env=env)
    execute([cmake,'--build',folder,'--config','Release','--parallel','4'],BUILD/'logs/host-build.log',env=env)
    ctest=cmake.parent/('ctest.exe' if os.name=='nt' else 'ctest')
    print(execute([ctest,'--test-dir',folder,'-C','Release','--output-on-failure'],BUILD/'logs/host-test.log',env=env))

if __name__=='__main__':main()
