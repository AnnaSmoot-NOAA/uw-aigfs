DEVPKGS    = $(shell cat devpkgs)
ENVNAME    = aigfs
ENVPATH    = $(shell ls $(CONDA_PREFIX)/envs/$(ENVNAME) 2>/dev/null)
TARGETS    = conda devenv env format lint rmenv test unittest
INSTALLDIR = conda
ACTIVATE   = . $(INSTALLDIR)/etc/profile.d/conda.sh && conda activate

.PHONY: $(TARGETS)

all:
	$(error Valid targets are: $(TARGETS))

conda:
	CONDA_DIR=$(INSTALLDIR) ./setup

devenv: env
	$(ACTIVATE) && mamba install -y -n $(ENVNAME) $(DEVPKGS)

env: conda
	$(ACTIVATE) && mamba env create -y -f environment.yml

format:
	@./format

lint:
	ruff check drivers

rmenv:
	$(if $(ENVPATH),conda env remove -y -n $(ENVNAME))

test: lint unittest

unittest:
	pytest --cov tests
