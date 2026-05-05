VENV_DIR ?= ~/.venv/yums3
SUDO := $(shell [ "$$(id -u)" = 0 ] || echo sudo)

.PHONY: setup-venv

setup-venv:
	@echo "Installing system dependencies..."
	@if [ "$$(uname)" = "Darwin" ]; then \
		echo "  Detected macOS"; \
		brew install createrepo_c rpm lxml || true; \
	elif [ -f /etc/debian_version ]; then \
		echo "  Detected Debian/Ubuntu"; \
		$(SUDO) apt-get update && $(SUDO) apt-get install -y createrepo-c rpm python3-lxml; \
	elif [ -f /etc/redhat-release ]; then \
		echo "  Detected RHEL/Rocky"; \
		$(SUDO) dnf install -y createrepo_c rpm-build python3-lxml; \
	else \
		echo "  Unknown OS — install createrepo_c and rpm manually"; \
	fi
	@if [ ! -d $(VENV_DIR) ]; then \
		echo "Creating virtual environment at $(VENV_DIR)..."; \
		python3 -m venv $(VENV_DIR); \
	else \
		echo "Virtual environment already exists at $(VENV_DIR)"; \
	fi
	@echo "Installing Python dependencies..."
	@. $(VENV_DIR)/bin/activate && pip install -r requirements.txt
	@echo
	@echo "  Virtual environment setup at: $(VENV_DIR)"
	@echo "  To activate your virtual env:"
	@echo "      source $(VENV_DIR)/bin/activate"
