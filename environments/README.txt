All three folders were tested on their respective QOP and changing back to qm-qua==1.2.3a1.
Note, the (KNOWN BUG) mentioned later only occurs on QOP 3.3.0 and 3.4.1, normal sequential qubit measurements should work on QOP 3.2.4

To Create the .lock and requirements.txt from scratch

1) uv venv name --python C:\path\to\python
2) name\Scripts\activate
3) git clone qolab_hackathon -> switch to correct branch 2Q1C_develop_yutaka_iSWAP for example
4) uv pip install qm-qua --prerelease=allow
5) uv pip install qualang-tools
6) uv pip install -e . after navigating to \...\qolab_hackathon\ *2Q1C_develop_yutaka_iSWAP branch (or other modified quam_libs branch)
7) uv pip install qm-qua==1.2.3a1
8) uv pip install
	1) lmfit
	2) pyvisa
	3) pyvisa-py
	4) google-api-core
	5) google-api-python-client
	6) google-auth
	7) google-auth-httplib2
	8) google-auth-oauthlib
	9) googleapis-common-protos
	10)Copy and paste this: (uv pip install lmfit pyvisa pyvisa-py google-api-core google-api-python-client google-auth google-auth-httplib2 google-auth-oauthlib googleapis-common-protos)

9) Change qualibrate config settings
	1) --project
	2) --storage-location
	3) --calibration-library-folder
	4) --quam-state-path
10) Edit QUAM State environment variable
11) Verify execution from IDE and Qualibrate front end

Note: KNOWN BUG -> Sequential measurements hang for some scripts indicated by repeating progress bar, need multiplexing or single qubit at a time. Not that the experiment still runs and data is collected but will not plot until ctrl+c'd.

To generate the requirements.txt & .lock file

1) Revert back to qua 1.2.1 using uv pip install qm-qua==1.2.1 because quam_libs requires this for .lock compilation
2) uv pip freeze > requirements.txt
3) uv pip compile requirements.txt --output-file .lock
4) Verify requirements.txt and .lock file exist in working directory and are not empty

To create a new environment from existing .lock file:

1) Create new venv (uv venv Env_Name --python C:\path\to\python)
2) copy .lock and requirements.txt to new project directory
3) uv pip sync .lock
4) clone repo, or use existing working directory as long as qualibrate config has been set appropriately. Verify script execution in IDE
5) Verify qualibrate start works

To append the requirements.txt and .lock file using "seaborn" package as an example:

1) Activate existing venv
2) uv pip install seaborn; verify things work
3) Append the existing requirements.txt manually: warning, do not re-use "uv pip freeze > requirements.txt". Instead copy and paste "seaborn==0.13.2" at the end of the requirements.txt and save the file.
4) Re-run: uv pip compile requirements.txt --output-file .lock
5) Then verify with a new environment created from the .lock file using uv pip sync .lock (ensuring to re-update qm-qua to 1.2.3a1 if on QOP 3.3.0 or higher)
