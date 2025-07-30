from pathlib import Path
import sys
from colorama import init, Fore, Style
import shutil, os
import tomllib
from deepdiff import DeepDiff
import subprocess

init(autoreset=True)


# Prompt for name
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