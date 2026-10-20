# Fedora COPR, SCM source with the "make_srpm" method: copr runs
#   make -f .copr/Makefile srpm outdir=<dir> spec=<spec>
# The spec downloads the tagged release tarball from GitHub (Source0).
SPEC := $(dir $(lastword $(MAKEFILE_LIST)))../packaging/g13d.spec

srpm:
	dnf -y install rpmdevtools rpm-build
	spectool -g -C $(outdir) $(SPEC)
	rpmbuild -bs --define "_sourcedir $(outdir)" --define "_srcrpmdir $(outdir)" $(SPEC)
