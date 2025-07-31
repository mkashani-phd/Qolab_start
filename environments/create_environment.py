from pathlib import Path
import sys
from colorama import init, Fore, Style
import shutil, os
import tomllib
from deepdiff import DeepDiff
import subprocess
from env_utils import setPath, getEnvName, compareEnvConfig, saveEnv, checkEnvFiles, getEnvList

init(autoreset=True)

def main():
# Prompt for name
    build = ''
    dirs = getEnvList()

    print(f"{Fore.RESET}\n# You can quit at any time with exit/quit")
    print(f"{Fore.CYAN}Would you like to:")
    print(f"{Fore.CYAN} - create a new environment")
    print(f"{Fore.CYAN} - clone an existing folder")
    print(f"{Fore.CYAN} - build from one of the following:")
    print(f"{Fore.CYAN}    - pyproject.toml")
    print(f"{Fore.CYAN}    - uv.lock")
    print(f"{Fore.CYAN}    - pip freeze (requirements.txt)")
    print(f"{Fore.CYAN}    - pip-compatible lockfile (requirements.lock)")

    while build not in ['new', 'clone', 'pyproject', 'lock', 'pip', 'piplock']:
        build = input(f"{Fore.YELLOW}Choose one (new, clone, pyproject, lock, pip, piplock): ")
        if build in ['quit', 'exit']:
            print(f"{Fore.YELLOW}Quitting...")
            sys.exit(0)

    return
# Get environment folders, present choices to user
# test ./<name>
    # If exists, let user know they need a different name, exit code 1
# Net new or use existing pyproject/lock?
# If apply to existing,
    # Change [metadata.environment_name] in ../pyproject.toml
    # mkdir ./<name>
    # mkdir ./<name>/legacy
    # cp ../pyproject.toml ./<name>
    # cp ../uv.lock ./<name>
    # cd ..
    # uv pip freeze > ./environments/legacy/requirements.txt
    # cd environments
    # uv pip compile ../uv.lock -o ./legacy/pip.lock
# If net new,
    #TBD
    #Copy metadata?


        # Initializing pyproject.toml
            # If no, exit with code 2
            # If yes, check for legacy, check for requirements.txt
                # If either is missing, exit with code 2
                # If not
                    # uv init --bare
                    # uv add -r ./<env>/legacy/requirements.txt
                    # prompt for QOP version, add to pyproject.toml as
                        # [metadata]
                        # QOP_version = "<version>"
                    # prompt for overrides, prompt for constraints, add to pyproject.toml as
                        # [tool.uv]
                        # override-dependencies = ["<override1>","<override2>"]
                        # constraint-dependencies = ["<constraint1>","<constraint2>"]

thispath = Path(__file__).parent.resolve()
setPath(thispath)

if __name__ == "__main__":
    main()