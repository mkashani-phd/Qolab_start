from pathlib import Path
import sys
from colorama import init, Fore, Style
import shutil, os
import subprocess
from env_utils import setPath, getEnvName, compareEnvConfig, checkEnvFiles, saveEnv, getEnvList

init(autoreset=True)

def main():

    # Get list of current + all environments
    dirs = getEnvList()

    try:
        print("\n# You can quit at any time with exit/quit")
        choice = input(f"{Fore.CYAN}Select environment {Fore.YELLOW}(1-" + str(len(dirs)) + f"): {Fore.GREEN}")
        if choice == 'quit' or choice == 'exit':
            print(f"{Fore.YELLOW}Quitting...")
            sys.exit(0)
        if int(choice) < 1:
            raise Exception
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
    changestatus, pychangelist, uvchangelist = compareEnvConfig(env1=savedenv,env2=None)
    if changestatus == 'complete':
        pychanges = [c for c in pychangelist if c[0] not in {'metadata.QOP_version', 'metadata.environment_name'}]
    elif changestatus == 'incomplete':
        print(f"{Fore.RED}Error: Incomplete while attempting to compare environments")
        sys.exit(1)
    else:
        print(f"{Fore.RED}Error: An unhandled error has occurred while comparing environments, exiting")
        sys.exit(1)
    if len(pychanges) != 0:
        compareEnvConfig(env1=savedenv,env2=None,verbose=True)
        print(f"{Fore.RESET}# You can quit at any time with exit/quit")
        print(f"{Fore.CYAN}The active environment {savedenv} contains differences from the saved version of {currentenv} (shown above).")
        while action not in ['save','discard']:
            action = input(
                f"{Fore.CYAN}Would you like to save these changes, or discard? {Fore.YELLOW}(save, discard) ")
            if action == 'quit' or action == 'exit':
                print(f"{Fore.YELLOW}Quitting, no action taken...")
                sys.exit(0)

    if action == 'save':
        changestatus, pychangelist, uvchangelist = compareEnvConfig(env1=None,env2=newenv)
    if action == 'discard':
        changestatus, pychangelist, uvchangelist = compareEnvConfig(env1=savedenv, env2=newenv)
    if changestatus == 'complete':
        pychanges = [c for c in pychangelist if c[0] not in {'metadata.QOP_version', 'metadata.environment_name'}]
    elif changestatus == 'incomplete':
        print(f"{Fore.RED}Error: Incomplete while attempting to compare environments")
        sys.exit(1)
    else:
        print(f"{Fore.RED}Error: An unhandled error has occurred while comparing environments, exiting")
        sys.exit(1)
    if len(pychanges) != 0:
        if action == 'save':
            compareEnvConfig(env1=None,env2=newenv, verbose=True)
        if action == 'discard':
            compareEnvConfig(env1=savedenv, env2=newenv, verbose=True)
        print(f"{Fore.RESET}# You can quit at any time with exit/quit")
        print(
            f"{Fore.CYAN}The new environment {newenv} contains differences from the active environment {currentenv} (shown above).")
        continueChange = ''
        while continueChange not in ['y', 'yes', 'n', 'no']:
            continueChange = input(
                f"{Fore.CYAN}Are you sure you'd like to continue? {Fore.YELLOW}(y/n) ")
            if continueChange in ['exit', 'quit', 'n', 'no']:
                print(f"{Fore.YELLOW}Quitting, no action taken...")
                sys.exit(0)
            if continueChange in ['y','yes']:
                break


    # Execute package change
    print("")
    if action == 'save':
        saveEnv(currentpath,savedpath)
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
    print(f"{Fore.LIGHTGREEN_EX}{line}")
    print(f"{Fore.LIGHTGREEN_EX}{endmsg}")
    print(f"{Fore.LIGHTGREEN_EX}{line}")
    sys.exit(0)

thispath = Path(__file__).parent.resolve()
setPath(thispath)

if __name__ == "__main__":
    main()

