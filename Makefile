ACTIVATE   = . $(INSTALLDIR)/etc/profile.d/conda.sh && conda activate
DEVPKGS    = $(shell cat devpkgs)
ENVNAME    = aigfs
ENVPATH    = $(shell ls $(CONDA_PREFIX)/envs/$(ENVNAME) 2>/dev/null)
INSTALLDIR = conda
TARGETS    = conda devenv docs env format lint rmenv test unittest

.PHONY: $(TARGETS)

all:
	$(error Valid targets are: $(TARGETS))

conda:
	CONDA_DIR=$(INSTALLDIR) ./setup

devenv: env
	$(ACTIVATE) && mamba install -y -n $(ENVNAME) $(DEVPKGS)

docs:
	$(ACTIVATE) $(ENVNAME) && pdoc --output-dir docs/api drivers

env: conda
	$(ACTIVATE) && mamba env create -y -f environment.yml

format:
	@./format

lint:
	ruff check .

rmenv:
	$(if $(ENVPATH),conda env remove -y -n $(ENVNAME))

test: lint unittest

unittest:
	pytest --cov tests
