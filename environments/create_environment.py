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