.PHONY: setup-venv

setup-venv:
	@if [ ! -d ~/.venv/yums3 ]; then \
		echo "Creating virtual environment..."; \
		python3 -m venv ~/.venv/yums3; \
	else \
		echo "Virtual environment already exists at ~/.venv/yums3"; \
	fi
	@echo "Installing dependencies..."
	@. ~/.venv/yums3/bin/activate && pip install -r requirements.txt
	@echo
	@echo "  Virtual environment setup at: ~/.venv/yums3"
	@echo "  To activate your virtual env:"
	@echo "      source ~/.venv/yums3/bin/activate"
