from pathlib import Path
import sys
from colorama import init, Fore, Style
import shutil, os
import tomllib
from deepdiff import DeepDiff
import subprocess

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
        return print(f"{Fore.RED}Path Error while comparing {env1} and {env2}: Could not find Environment {Fore.BLUE}"+env1+"\n")
    if env2 is None:
        envpath2 = str(thispath.parent)
    else:
        if Path('./'+env2).is_dir():
            envpath2 = str(Path('./'+env2).resolve())
        else:
            return print(f"{Fore.RED}Path Error while comparing {env1} and {env2}: Could not find Environment {Fore.BLUE}"+env2+"\n")
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
                        paths.append(".".join(str(x) for x in item.path(output_format='list')))
            for p in sorted(paths):
                diff.append(p)
    with open(envpath1+"/uv.lock") as f1, open(envpath2+"/uv.lock") as f2:
        identical = f1.read() == f2.read()
        if not identical: diff.append("uv.lock")
    return diff




def getEnvName(filepath=None):
    if filepath is None:
        filepath = str(Path(str(thispath.parent)+'/pyproject.toml').resolve())
    with open(filepath,'rb') as f:
        return tomllib.load(f)['metadata']['environment_name']




def main():

    edited = ''
    activechanges = compareEnvConfig(getEnvName())
    if len(activechanges) != 0: edited = ' (edited)'

    # Get current environment name
    print(f"{Fore.MAGENTA}Current Environment:")
    print(f"{Fore.GREEN}{getEnvName()}{edited}\n")

    # Get environment folders, present choices to user
    dirs = [d.name for d in thispath.iterdir() if d.is_dir()]
    if len(dirs)==0:
        return print(f"{Fore.RED}Warning: Did not find any environment folders at "+str(Path(thispath).resolve()))
    print(f"{Fore.MAGENTA}Found environment folders at " + str(Path(thispath).resolve()))
    for i, d in enumerate(dirs): print(f"{Fore.BLUE}{i + 1} - {Fore.GREEN}{d}")
    try:
        print("\n# You can quit at any time with exit/quit")
        choice = input(f"{Fore.CYAN}Select environment {Fore.YELLOW}(1-" + str(len(dirs)) + f"): {Fore.GREEN}")
        if choice == 'quit' or choice == 'exit':
            print(f"{Fore.YELLOW}Quitting...")
            sys.exit(0)
        newenv = str(dirs[int(choice)-1])
    except:
        print(f"{Fore.RED}Invalid selection: Expected one of: {Fore.BLUE}" + (
            ', '.join(str(i) for i in range(1, len(dirs) + 1))) + f"{Fore.RED}, received {Fore.BLUE}" + str(choice))
        return sys.exit(1)

    # Check user's selection is a valid environment folder
    print(f"\n{Fore.MAGENTA}New Environment to be Loaded:")
    newpath = str(thispath) + '/' + newenv
    newenv = getEnvName(newpath + '/pyproject.toml')
    checkEnvFiles(envpath = newpath)

    # Check the current environment is valid
    print(f"{Fore.MAGENTA}Active Version of Current Environment:")
    currentpath = str(thispath.parent)
    currentenv = getEnvName(currentpath + '/pyproject.toml')
    checkEnvFiles(envpath = currentpath)

    # Check that the current environment has somewhere to be stored
    print(f"{Fore.MAGENTA}Saved Version of Current Environment:")
    savedpath = str(thispath) + '/' + currentenv
    savedenv = getEnvName(savedpath + '/pyproject.toml')
    checkEnvFiles(envpath = savedpath)

    # Check for changes between current active environment and saved active environment
    action = None
    changes = [c for c in compareEnvConfig(savedenv) if c not in {'pyproject.toml','metadata.QOP_version','metadata.environment_name'}]
    if len(changes) != 0:
        print("# You can quit at any time with exit/quit")
        print(f"{Fore.CYAN}The active environment {savedenv} contains differences from the saved version of {currentenv}.")
        while action not in ['save','discard']:
            action = input(
                f"{Fore.CYAN}Would you like to save these changes, or discard? {Fore.YELLOW}(save, discard) ")
            if action == 'quit' or action == 'exit':
                print(f"{Fore.YELLOW}Quitting...")
                sys.exit(0)

    # Execute package change
    print("")
    if action == 'save':
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
    # Shelf current config, copy over new config
    try:
        os.rename(currentpath+'/pyproject.toml',currentpath+'/trsh-current-pyproject.toml')
        os.rename(currentpath+'/uv.lock',currentpath+'/trsh-current-uv.lock')
        shutil.copy(newpath+'/pyproject.toml',currentpath+'/pyproject.toml')
        shutil.copy(newpath+'/uv.lock',currentpath+'/uv.lock')
        print(f"{Fore.MAGENTA}Executing uv sync:{Fore.GREEN}")
        print(Style.RESET_ALL, end="", flush=True)
        subprocess.run(["uv","sync"], check=True)
    # Back out by restoring old active config
    except:
        try:
            print(f"{Fore.RED}Error: An error has occurred while loading new config, safely backing out of change.")
            os.rename(currentpath + '/trsh-current-pyproject.toml', currentpath + '/pyproject.toml')
            os.rename(currentpath + '/trsh-current-uv.lock', currentpath + '/uv.lock')
            print(f"{Fore.RED}Backed out successfully.")
            sys.exit(1)
        except:
            print(f"{Fore.RED}ERROR: An unhandled error has occurred, unable to back out safely.")
            sys.exit(1)
    # Clean up old config after successfully loading new config
    try:
        os.remove(currentpath + '/trsh-current-pyproject.toml')
        os.remove(currentpath + '/trsh-current-uv.lock')
    except:
        print(f"{Fore.RED}Error: Successfully copied over new config, but failed to clean up old config")
        print(f"{Fore.RED}Error: Old config saved as trsh-current-pyproject.toml, trsh-current-uv.lock")
    print("")
    savemsg=''
    if action == 'save':
        savemsg = f" saved {currentenv} and"
    endmsg = f"Successfully{savemsg} loaded {newenv}!"
    endmsg = "+"+"~" * 6 + " " + endmsg + " " + "~" * 6+"+"
    line = "+"+"~" * (len(endmsg)-2)+"+"
    print(f"{Fore.GREEN}{line}")
    print(f"{Fore.GREEN}{endmsg}")
    print(f"{Fore.GREEN}{line}")
    sys.exit(0)

thispath = Path(__file__).parent.resolve()

if __name__ == "__main__":
    main()

