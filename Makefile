# g13d — developer / single-user install helpers.
PY ?= python3
PIP_FLAGS ?= --user --no-build-isolation
UNIT_DIR := $(HOME)/.config/systemd/user
UDEV_RULE := /etc/udev/rules.d/70-g13d.rules

.PHONY: help install install-udev enable uninstall uninstall-udev test lint

help:
	@echo "make install-udev   # (sudo) install udev rule, reload, trigger"
	@echo "make install        # pip install (editable, user site) + systemd user unit"
	@echo "make enable         # enable + start g13d.service"
	@echo "make uninstall      # stop service, remove unit, pip uninstall"
	@echo "make test           # run the test-suite"

install-udev:
	sudo install -Dm644 g13d/data/70-g13d.rules $(UDEV_RULE)
	sudo udevadm control --reload
	sudo udevadm trigger --subsystem-match=input --subsystem-match=hidraw --subsystem-match=leds --subsystem-match=misc

install:
	$(PY) -m pip install $(PIP_FLAGS) -e .
	install -Dm644 g13d/data/g13d.service $(UNIT_DIR)/g13d.service
	install -Dm644 g13d/data/org.g13d.Gui.desktop $(HOME)/.local/share/applications/org.g13d.Gui.desktop
	systemctl --user daemon-reload

enable:
	systemctl --user enable --now g13d.service
	systemctl --user --no-pager status g13d.service

uninstall:
	-systemctl --user disable --now g13d.service
	rm -f $(UNIT_DIR)/g13d.service $(HOME)/.local/share/applications/org.g13d.Gui.desktop
	systemctl --user daemon-reload
	-$(PY) -m pip uninstall -y g13d

uninstall-udev:
	sudo rm -f $(UDEV_RULE)
	sudo udevadm control --reload

test:
	$(PY) -m pytest -q
