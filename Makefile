# g13d — developer / single-user install helpers.
PY ?= python3
PIP_FLAGS ?= --user --no-build-isolation
UNIT_DIR := $(HOME)/.config/systemd/user
UDEV_RULE := /etc/udev/rules.d/70-g13d.rules

EXT_UUID := g13d@g13d.org
EXT_DIR := $(HOME)/.local/share/gnome-shell/extensions/$(EXT_UUID)

.PHONY: help dev install install-udev install-extension enable uninstall uninstall-udev test lint

help:
	@echo "make dev            # everything below in one go: udev rule, install, extension, enable"
	@echo "make install-udev   # (sudo) install udev rule, reload, trigger"
	@echo "make install        # pip install (editable, user site) + systemd user unit"
	@echo "make install-extension  # GNOME Shell extension for per-application profiles (then log out / in)"
	@echo "make enable         # enable + start g13d.service"
	@echo "make uninstall      # stop service, remove unit, pip uninstall"
	@echo "make test           # run the test-suite"

# The whole developer install. The Fedora package (COPR) installs the same pieces system-wide: remove it first
# (sudo dnf remove g13d gnome-shell-extension-g13d), the files in your home would hide it anyway.
dev:
	@if rpm -q g13d >/dev/null 2>&1; then echo "The g13d package is installed: sudo dnf remove g13d gnome-shell-extension-g13d first"; exit 1; fi
	$(MAKE) install-udev install install-extension enable

install-udev:
	sudo install -Dm644 g13d/data/70-g13d.rules $(UDEV_RULE)
	sudo udevadm control --reload
	sudo udevadm trigger --subsystem-match=input --subsystem-match=hidraw --subsystem-match=leds --subsystem-match=misc

install:
	$(PY) -m pip install $(PIP_FLAGS) -e .
	install -Dm644 g13d/data/g13d.service $(UNIT_DIR)/g13d.service
	install -Dm644 g13d/data/org.g13d.Gui.desktop $(HOME)/.local/share/applications/org.g13d.Gui.desktop
	sed -i 's|^Exec=.*|Exec=$(HOME)/.local/bin/g13-gui|' $(HOME)/.local/share/applications/org.g13d.Gui.desktop
	-update-desktop-database $(HOME)/.local/share/applications 2>/dev/null
	systemctl --user daemon-reload

install-extension:
	rm -rf $(EXT_DIR)
	cp -r g13d/data/gnome-shell/$(EXT_UUID) $(EXT_DIR)
	-gnome-extensions enable $(EXT_UUID) 2>/dev/null
	@echo "Extension installed. GNOME loads new extensions at login: log out and back in, then check 'g13ctl status'."

enable:
	systemctl --user enable --now g13d.service
	systemctl --user --no-pager status g13d.service

uninstall:
	-systemctl --user disable --now g13d.service
	rm -f $(UNIT_DIR)/g13d.service $(HOME)/.local/share/applications/org.g13d.Gui.desktop
	-gnome-extensions disable $(EXT_UUID) 2>/dev/null
	rm -rf $(EXT_DIR)
	systemctl --user daemon-reload
	-$(PY) -m pip uninstall -y g13d

uninstall-udev:
	sudo rm -f $(UDEV_RULE)
	sudo udevadm control --reload

test:
	$(PY) -m pytest -q
