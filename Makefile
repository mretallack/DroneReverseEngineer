
PYTHON=python3.11

run: venv/bin/activate
	@. venv/bin/activate && ${PYTHON} stream_video.py



venv/bin/activate: requirements.txt
	@rm -rf venv
	@${PYTHON} -m venv venv
	@. venv/bin/activate && ${PYTHON} -m pip install -r requirements.txt


