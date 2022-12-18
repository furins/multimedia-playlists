.PHONY: install_dev, setup_dev, minor

install_dev:
	python -m pip install -U -r ./requirements.txt

setup_dev:
	pre-commit install --hook-type commit-msg --hook-type pre-push
	pre-commit autoupdate
	cz init

minor:
	cz bump --changelog
