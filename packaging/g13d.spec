Name:           g13d
Version:        1.5.0
Release:        1%{?dist}
Summary:        Native Linux driver for the Logitech G13 gameboard, with a GTK4 GUI

License:        MIT
URL:            https://github.com/MrPanda88/g13d
Source0:        %{url}/archive/v%{version}/%{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros
BuildRequires:  systemd-rpm-macros
BuildRequires:  desktop-file-utils
# test-suite
BuildRequires:  python3-pytest
BuildRequires:  python3-evdev
BuildRequires:  python3-dbus-next
BuildRequires:  python3-pillow
BuildRequires:  python3-pyudev
BuildRequires:  python3-psutil

# the Python dependencies come from pyproject.toml; the GUI's are optional there
Requires:       python3-gobject
# loaded through GObject introspection at run time (no automatic dependency)
Requires:       gtk4
Requires:       libadwaita
Recommends:     gnome-shell-extension-g13d
%{?systemd_requires}

%description
g13d drives the Logitech G13 gameboard (046d:c21c) from user space on top of
the kernel driver hid-lg-g15 (G13 support since Linux 6.19): no libusb, the
kernel driver stays bound. It remaps the G keys, LCD keys and thumbstick per
profile and M1/M2/M3 mode, plays macros, draws pages on the 160x43 LCD, sets
the RGB backlight, and switches profiles with the focused application.

The package ships the g13d daemon (systemd user service), the g13ctl command
line tool, the g13-gui configuration application (GTK4 / libadwaita) and the
udev rule giving the logged-in user access to the device.

%package -n gnome-shell-extension-g13d
Summary:        GNOME Shell extension telling g13d which window is focused
Requires:       %{name} = %{version}-%{release}
Requires:       gnome-shell

%description -n gnome-shell-extension-g13d
Wayland does not let a program see the focused window. This small GNOME Shell
extension tells the g13d daemon which application has the focus, so the G13 can
switch to the profile linked to it. Enable it with
"gnome-extensions enable g13d@g13d.org", then log out and back in.

%prep
%autosetup -n %{name}-%{version}

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files g13d

install -Dpm 0644 g13d/data/70-g13d.rules %{buildroot}%{_udevrulesdir}/70-g13d.rules
install -Dpm 0644 g13d/data/g13d.service %{buildroot}%{_userunitdir}/g13d.service
sed -i 's|^ExecStart=.*|ExecStart=%{_bindir}/g13d|' %{buildroot}%{_userunitdir}/g13d.service
install -Dpm 0644 g13d/data/org.g13d.Gui.desktop %{buildroot}%{_datadir}/applications/org.g13d.Gui.desktop
desktop-file-validate %{buildroot}%{_datadir}/applications/org.g13d.Gui.desktop
install -Dpm 0644 g13d/data/icons/org.g13d.Gui.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/org.g13d.Gui.svg
mkdir -p %{buildroot}%{_datadir}/gnome-shell/extensions
cp -a g13d/data/gnome-shell/g13d@g13d.org %{buildroot}%{_datadir}/gnome-shell/extensions/

%check
%pytest -q

%post
%udev_rules_update
%systemd_user_post g13d.service

%preun
%systemd_user_preun g13d.service

%postun
%udev_rules_update
%systemd_user_postun_with_restart g13d.service

%files -f %{pyproject_files}
%license LICENSE
%doc README.md
%{_bindir}/g13d
%{_bindir}/g13ctl
%{_bindir}/g13-gui
%{_udevrulesdir}/70-g13d.rules
%{_userunitdir}/g13d.service
%{_datadir}/applications/org.g13d.Gui.desktop
%{_datadir}/icons/hicolor/scalable/apps/org.g13d.Gui.svg

%files -n gnome-shell-extension-g13d
%{_datadir}/gnome-shell/extensions/g13d@g13d.org/

%changelog
* Sun Oct 25 2026 Raphaël Lang <42946274+MrPanda88@users.noreply.github.com> - 1.5.0-1
- g13d 1.5.0: per-profile assignments and macros, app icon

* Tue Oct 20 2026 Raphaël Lang <42946274+MrPanda88@users.noreply.github.com> - 1.4.0-1
- First package: g13d 1.4.0
