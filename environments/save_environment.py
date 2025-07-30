from pathlib import Path
import sys
from colorama import init, Fore
import subprocess
from env_utils import setPath, getEnvName, compareEnvConfig, saveEnv, checkEnvFiles

init(autoreset=True)

def main():

    # Get current environment name
    envName = getEnvName()
    envPath = str(thispath.parent)
    print(f"{Fore.MAGENTA}Current Environment {Fore.BLUE}{envName}{Fore.MAGENTA}:")
    print(f"{Fore.GREEN}{envPath+'/pyproject.toml'}\n")
    changestatus, pychanges, uvchanges = compareEnvConfig(envName)
    if changestatus == "complete":
        savedEnvPath = str(thispath)+ '/' + envName
        print(f"{Fore.MAGENTA}Saved Environment {Fore.BLUE}{envName}{Fore.MAGENTA}:")
        print(f"{Fore.GREEN}{savedEnvPath+'/pyproject.toml'}\n")
        if len(pychanges) == 0 and len(uvchanges) == 0:
            print(f"{Fore.LIGHTGREEN_EX}~~~ Environment is identical to the saved version, exiting ~~~")
            sys.exit(0)
        else:
            action = None
            compareEnvConfig(envName,verbose=True)
            print(f"{Fore.RESET}# You can quit at any time with exit/quit")
            while action not in ['y', 'yes', 'n', 'no']:
                action = input(
                    f"{Fore.CYAN}Are you sure you'd like to continue? {Fore.YELLOW}(y/n) ")
                if action in ['quit', 'exit']:
                    print(f"{Fore.YELLOW}Quitting...")
                    sys.exit(0)
                if action in ['n', 'no']:
                    print(f"{Fore.YELLOW}No changes were saved. Quitting...")
                    sys.exit(0)
            if action == 'y' or action == 'yes':
                saveEnv(envPath,savedEnvPath)
                print("")
                endmsg = f"Successfully saved {envName}!"
                endmsg = "+" + "~" * 6 + " " + endmsg + " " + "~" * 6 + "+"
                line = "+" + "~" * (len(endmsg) - 2) + "+"
                print(f"{Fore.LIGHTGREEN_EX}{line}")
                print(f"{Fore.LIGHTGREEN_EX}{endmsg}")
                print(f"{Fore.LIGHTGREEN_EX}{line}")
                sys.exit(0)
    elif changestatus == "incomplete":
        print(f"{Fore.RED}Error: Unable to save the environment {Fore.BLUE}{getEnvName()}.\n{Fore.RED}Could not find folder in {thispath}")
        sys.exit(1)
    else:
        print(f"{Fore.RED}Error: An unhandled error has occurred while comparing environments, exiting")
        sys.exit(1)



thispath = Path(__file__).parent.resolve()
setPath(thispath)

if __name__ == "__main__":
    main()