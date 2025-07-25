from pathlib import Path
import sys
from colorama import init, Fore, Style
import os
import tomllib
from deepdiff import DeepDiff

init(autoreset=True)

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





def compareEnvConfig(env1,env2=None):
    diff = []
    if Path('./'+env1).is_dir():
        envpath1 = str(Path('./'+env1).resolve())
    else:
        return print(f"{Fore.RED}Path Error while comparing {env1} and {env2}: Could not find Environment {Fore.BLUE}"+env1)
    if env2 is None:
        envpath2 = '..'
    else:
        if Path('./'+env2).is_dir():
            envpath2 = str(Path('./'+env2).resolve())
        else:
            return print(f"{Fore.RED}Path Error while comparing {env1} and {env2}: Could not find Environment {Fore.BLUE}"+env2)
    with open(envpath1+"/pyproject.toml",'rb') as f1, open(envpath2+"/pyproject.toml",'rb') as f2:
        identical = f1.read() == f2.read()
        if not identical:
            diff.append("pyproject.toml")
            f1.seek(0)
            f2.seek(0)
            toml1 = tomllib.load(f1)
            toml2 = tomllib.load(f2)
            dDiff = DeepDiff(toml1, toml2, view='tree')
            paths = []
            for change_type in dDiff:
                for item in dDiff[change_type]:
                    if hasattr(item, "path"):
                        paths.append(".".join(str(item.path(output_format='list'))))
            for p in sorted(paths):
                diff.append(p)
    with open(envpath1+"/uv.lock") as f1, open(envpath2+"/uv.lock") as f2:
        identical = f1.read() == f2.read()
        if not identical: diff.append("uv.lock")
    return diff




def getEnvName(filepath):
    with open(filepath,'rb') as f:
        return tomllib.load(f)['metadata']['environment_name']




def main():

    # Get environment folders, present choices to user
    dirs = [d for d in os.listdir() if os.path.isdir(d)]
    thispath = '.'
    if len(dirs)==0:
        return print(f"{Fore.RED}Warning: Did not find any environment folders at "+str(Path(thispath).resolve()))
    print(f"{Fore.MAGENTA}Found environment folders at " + str(Path(thispath).resolve()))
    for i, d in enumerate(dirs): print(f"{Fore.BLUE}{i + 1} - {Fore.GREEN}{d}")
    try:
        choice = input(f"{Fore.CYAN}\nSelect environment {Fore.YELLOW}(1-" + str(len(dirs)) + f"): {Fore.GREEN}")
        newenv = str(dirs[int(choice)-1])
    except:
        print(f"{Fore.RED}Invalid selection: Expected one of: {Fore.BLUE}" + (
            ', '.join(str(i) for i in range(1, len(dirs) + 1))) + f"{Fore.RED}, received {Fore.BLUE}" + str(choice))
        return sys.exit(1)

    # Check user's selection is a valid environment folder
    print(f"\n{Fore.MAGENTA}New Environment to be Loaded:")
    checkEnvFiles(envpath = thispath + '/' + newenv)

    # Check the current environment is valid
    print(f"{Fore.MAGENTA}Active Version of Current Environment:")
    currentpath = thispath + '.'
    currentenv = getEnvName(currentpath + '/pyproject.toml')
    checkEnvFiles(envpath = currentpath)

    # Check that the current environment has somewhere to be stored
    print(f"{Fore.MAGENTA}Saved Version of Current Environment:")
    savedpath = thispath + '/' + currentenv
    savedenv = getEnvName(savedpath + '/pyproject.toml')
    checkEnvFiles(envpath = savedpath)

    # Check for changes between current active environment and saved active environment

    changes = [c for c in compareEnvConfig(savedpath) if c not in {'pyproject.toml','metadata.QOP_version','metadata.environment_name'}]
    if len(changes) != 0:
        print(f"{Fore.CYAN}The active environment {savedenv} contains differences from the saved version {currentenv}.")
        response = ''
        while response not in ['save','discard']:
            response = input(
                f"{Fore.CYAN}Would you like to save these changes, or discard? {Fore.YELLOW}(save, discard) ")
            if response == 'save':
                print("saving")
            elif response == 'discard':
                print("discarding")

        # Ask user if they'd like to check out save/store the current environment
            # test ./<prev-metadata.environment_name>
                # If doesn't exist, warn the user it couldn't store the old environment, exit with code 1
                # If it does, proceed to store
                    # If any error is detected, graceful backout
                        # mv -f ./<prev-metadata.environment_name>/pyproject.toml ..
                        # mv -f ./<prev-metadata.environment_name>/uv.lock ..
                    # mv -f ../pyproject.toml ./<prev-metadata.environment_name>/pyproject.toml
                    # mv -f ../uv.lock ./<prev-metadata.environment_name>/uv.lock
                    # cp ./<new-metadata.environment_name>/pyproject.toml ..
                    # cp ./<new-metadata.environment_name>/uv.lock
                    # uv sync

main()

