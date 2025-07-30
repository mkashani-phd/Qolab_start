from pathlib import Path
import sys
from colorama import Fore
import tomllib
from deepdiff import DeepDiff
import os
import shutil
import re

thispath = None
def setPath(path):
    global thispath
    thispath = path

def checkEnvFiles(envpath):
    missing = []
    if not Path(envpath).is_dir():
        missing.append('directory')
        print(f"{Fore.RED}Missing: Could not find directory {Fore.BLUE}" + str(envpath))
    if Path(envpath + '/pyproject.toml').is_file():
        with open(Path(envpath + '/pyproject.toml').resolve(),'rb') as f:
            toml = tomllib.load(f)
            try:
                tomlname = toml["metadata"]["environment_name"]
            except:
                return print(f"{Fore.RED}pyproject.toml: Could not identify environment name, exiting")
                sys.exit(1)
            print(f"{Fore.BLUE}Environment: {Fore.GREEN}" + str(tomlname))
            print(f"{Fore.BLUE}Found pyproject.toml at {Fore.GREEN}" + str(Path(envpath + '/pyproject.toml').resolve()))
    else:
        missing.append('pyproject.toml')
        print(f"{Fore.RED}Missing: Could not find pyproject.toml at {Fore.BLUE}" + str(
            Path(envpath + '/pyproject.toml').resolve()))
    if Path(envpath + '/uv.lock').is_file():
        print(f"{Fore.BLUE}Found uv.lock at {Fore.GREEN}" + str(Path(envpath + '/uv.lock').resolve()))
    else:
        missing.append('uv.lock')
        print(f"{Fore.RED}Missing: Could not find uv.lock at {Fore.BLUE}" + str(Path(envpath + '/uv.lock').resolve()))
    print("")
    return missing





def compareEnvConfig(env1=None,env2=None,verbose=False):
    # Initialize files
    pydiff = []
    uvdiff = {}
    if env1 is None:
        envpath1 = str(thispath.parent)
        with open (envpath1+'/pyproject.toml','rb') as f:
            env1name = tomllib.load(f)['metadata']['environment_name']
    else:
        if Path('./'+env1).is_dir():
            envpath1 = str(Path('./'+env1).resolve())
            env1name = env1
        else:
            print(f"{Fore.RED}Path Error while comparing {env1} and {env2}: Could not find Environment {Fore.BLUE}" + env1 + "\n")
            return "incomplete", []
    if env2 is None:
        envpath2 = str(thispath.parent)
        with open (envpath2+'/pyproject.toml','rb') as f:
            env2name = tomllib.load(f)['metadata']['environment_name']
    else:
        if Path('./'+env2).is_dir():
            envpath2 = str(Path('./'+env2).resolve())
            env2name = env2
        else:
            print(f"{Fore.RED}Path Error while comparing {env1} and {env2}: Could not find Environment {Fore.BLUE}"+env2+"\n")
            return "incomplete", []

    # Output formatting
    def strip_ansi(s):
        return re.sub(r'\x1b\[[0-9;]*m', '', s)
    if env1 == None: activeenv1 = " (active)"
    else: activeenv1 = ""
    if env2 == None: activeenv2 = " (active)"
    else: activeenv2 = ""
    envDiffLine = f"{Fore.RESET}=" * 20 + f" Env Diff: {Fore.RED}{env1name}{activeenv1}{Fore.RESET} --> {Fore.BLUE}{env2name}{activeenv2} {Fore.RESET}" + f"{Fore.RESET}=" * 20
    blankLine = f"{Fore.RESET}=" * len(strip_ansi(envDiffLine))
    if verbose: print(blankLine)
    if verbose: print(envDiffLine)
    if verbose: print(blankLine)

    # Diff pyproject.toml
    with open(envpath1+"/pyproject.toml",'rb') as f1, open(envpath2+"/pyproject.toml",'rb') as f2:
        pyidentical = f1.read() == f2.read()
        if not pyidentical:
            f1.seek(0)
            f2.seek(0)
            toml1 = tomllib.load(f1)
            toml2 = tomllib.load(f2)
            dDiff = DeepDiff(toml1, toml2, view='tree', ignore_order=True)
            paths = []
            for change_type in dDiff:
                for item in dDiff[change_type]:
                    if hasattr(item, "path"):
                        paths.append([".".join(str(x) for x in item.path(output_format='list')),item])
            if verbose: print(f"{Fore.MAGENTA}Differences in pyproject.toml:")
            for p in sorted(paths):
                if verbose: print(f"  {Fore.GREEN}{p[0]}: {Fore.RED}{p[1].t1}{Fore.YELLOW} --> {Fore.BLUE}{p[1].t2}")
                pydiff.append(p)

    # Diff uv.lock
    with open(envpath1+"/uv.lock",'rb') as f1, open(envpath2+"/uv.lock",'rb') as f2:
        uvidentical = f1.read() == f2.read()
        if not uvidentical:
            if verbose and not pyidentical: print("")
            if verbose: print(f"{Fore.MAGENTA}Differences in uv.lock:")
            f1.seek(0)
            f2.seek(0)
            lock1 = tomllib.load(f1)
            lock2 = tomllib.load(f2)
            keys = set(lock1.keys()) | set(lock2.keys())
            for key in sorted(keys):
                if key != 'package':
                    paths = []
                    newdiff = DeepDiff(lock1.get(key), lock2.get(key),view='tree',ignore_order=True)
                    if len(newdiff) != 0:
                        if f"changed_{key}" not in uvdiff.keys(): uvdiff[f"changed_{key}"] = []
                        for change_type in newdiff:
                            for item in newdiff[change_type]:
                                if hasattr(item, "path"):
                                    paths.append([".".join(str(x) for x in item.path(output_format='list')), item])
                        if verbose: print(f"  {Fore.MAGENTA}{key}:")
                        if len(paths) == 1 and paths[0][1].path()=='root':
                            if verbose: print(f"    {Fore.RED}{paths[0][1].t1}{Fore.YELLOW} --> {Fore.BLUE}{paths[0][1].t2}")
                        else:
                            for p in sorted(paths):
                                if verbose: print(
                                    f"    {Fore.GREEN}{p[0]}: {Fore.RED}{p[1].t1}{Fore.YELLOW} --> {Fore.BLUE}{p[1].t2}")
                                pydiff.append(p)
                if key == 'package':
                    printedPackages = False
                    pkg1 = {p['name']: p for p in lock1.get("package", [])}
                    pkg2 = {p['name']: p for p in lock2.get("package", [])}
                    pkgkey1 = set(pkg1.keys())
                    pkgkey2 = set(pkg2.keys())
                    added = pkgkey2-pkgkey1
                    removed = pkgkey1-pkgkey2
                    shared = pkgkey1 & pkgkey2
                    if len(added) != 0:
                        uvdiff[f"added_{key}"] = []
                    if len(removed) != 0:
                        uvdiff[f"removed_{key}"] = []
                    for name in sorted(added):
                        uvdiff[f"added_{key}"].append(pkg2[name])
                        if verbose and not printedPackages: print(f"  {Fore.MAGENTA}{key}:")
                        printedPackages = True
                        if verbose: print(f"{Fore.BLUE}   (+) added {name} == {pkg2[name]['version']}")
                    for name in sorted(removed):
                        uvdiff[f"removed_{key}"].append(pkg1[name])
                        if verbose and not printedPackages: print(f"  {Fore.MAGENTA}{key}:")
                        printedPackages = True
                        if verbose: print(f"{Fore.RED}   (-) removed {name} == {pkg1[name]['version']}")
                    for name in sorted(shared):
                        d1 = pkg1[name]
                        d2 = pkg2[name]
                        mydiff = DeepDiff(d1, d2, view='tree', ignore_order=True)
                        if len(mydiff) != 0:
                            if verbose and not printedPackages: print(f"  {Fore.MAGENTA}{key}:")
                            printedPackages = True
                            if f"changed_{key}" not in uvdiff.keys(): uvdiff[f"changed_{key}"] = []
                            items = []
                            for diffkey in mydiff.keys():
                                for item in mydiff[diffkey]:
                                    uvdiff[f"changed_{key}"].append(mydiff)
                                    itemchange = ".".join(str(x) for x in item.path(output_format='list'))
                                    if itemchange == 'version':
                                        itemchange += f" {Fore.LIGHTYELLOW_EX}({Fore.RED}{item.t1}{Fore.LIGHTYELLOW_EX} --> {Fore.BLUE}{item.t2}{Fore.LIGHTYELLOW_EX}){Fore.YELLOW}"
                                        items.insert(0,itemchange)
                                    else:
                                        items.append(itemchange)
                            if verbose: print(f"{Fore.YELLOW}   (~) {name}: changed {", ".join(str(x) for x in items)}")

    envDiffLine = f"{Fore.RESET}=" * 20 + f" End Env Diff: {Fore.RED}{env1name}{activeenv1}{Fore.RESET} --> {Fore.BLUE}{env2name}{activeenv2} {Fore.RESET}" + f"{Fore.RESET}=" * 20
    blankLine = f"{Fore.RESET}=" * len(strip_ansi(envDiffLine))
    if verbose: print(blankLine)
    if verbose: print(envDiffLine)
    if verbose: print(blankLine+"\n")

    return "complete", pydiff, uvdiff




def getEnvName(filepath=None):
    if filepath is None:
        filepath = str(Path(str(thispath.parent)+'/pyproject.toml').resolve())
    with open(filepath,'rb') as f:
        return tomllib.load(f)['metadata']['environment_name']


def saveEnv(currentpath,savedpath):
        # Shelf old saved config, copy over current config
        try:
            os.rename(savedpath+'/pyproject.toml',savedpath+'/trsh-saved-pyproject.toml')
            os.rename(savedpath+'/uv.lock',savedpath+'/trsh-saved-uv.lock')
            shutil.copy(currentpath+'/pyproject.toml',savedpath+'/pyproject.toml')
            shutil.copy(currentpath+'/uv.lock',savedpath+'/uv.lock')
        except:
            # Back out by restoring old saved config
            try:
                print(f"{Fore.RED}Error: An error has occurred while saving existing config, safely backing out of change.")
                os.rename(currentpath + '/trsh-saved-pyproject.toml', currentpath + '/pyproject.toml')
                os.rename(currentpath + '/trsh-saved-uv.lock', currentpath + '/uv.lock')
                print(f"{Fore.RED}Backed out successfully.")
                sys.exit(1)
            except:
                print(f"{Fore.RED}ERROR: An unhandled error has occurred, unable to back out safely.")
                sys.exit(1)
        # Clean up old saved config after successful save of current
        try:
            os.remove(savedpath + '/trsh-saved-pyproject.toml')
            os.remove(savedpath + '/trsh-saved-uv.lock')
        except:
            print(f"{Fore.RED}Error: Successfully saved existing config, but failed to clean up prior saved version.")
            print(f"{Fore.RED}Error: Old config saved as trsh-saved-pyproject.toml, trsh-saved-uv.lock")

def getEnvList():
    edited = ''
    changestatus, pychanges, uvchanges = compareEnvConfig(getEnvName())
    if changestatus == "complete":
        if len(pychanges) != 0 or len(uvchanges) != 0: edited = ' (edited)'
    elif changestatus == "incomplete":
        print(f"{Fore.RED}Error: Incomplete while attempting to compare environments")
        sys.exit(1)
    else:
        print(f"{Fore.RED}Error: An unhandled error has occurred while comparing environments, exiting")
        sys.exit(1)

    # Get current environment name
    print(f"{Fore.MAGENTA}Current Environment:")
    print(f"{Fore.BLUE}0 - {Fore.GREEN}{getEnvName()}{edited}\n")

    # Get environment folders, present choices to user
    dirs = [d.name for d in thispath.iterdir() if d.is_dir() and d.name != '__pycache__']
    if len(dirs) == 0:
        return print(f"{Fore.RED}Warning: Did not find any environment folders at " + str(Path(thispath).resolve()))
    print(f"{Fore.MAGENTA}Found environment folders at " + str(Path(thispath).resolve()))
    for i, d in enumerate(dirs): print(f"{Fore.BLUE}{i + 1} - {Fore.GREEN}{d}")

    return dirs