SHELL   := $(shell which bash)
TARGETS := bootstrap deploy devenv docs env format lint rmenv test typecheck unittest

check = @$(if $(1),,$(error $(2)= argument required))

.PHONY: $(TARGETS)

all:
	$(error Valid targets are: $(TARGETS))

bootstrap:
	@bin/run bootstrap

deploy:
	$(call check,$(playbook),playbook)
	@bin/run deploy $(playbook)

devenv:
	@DEVMODE=1 bin/run makeenv

docs:
	@bin/run makedocs

env:
	@bin/run makeenv

format:
	@bin/run format

lint:
	@bin/run lint

rmenv:
	@bin/run rmenv

test: lint typecheck unittest

typecheck:
	@bin/run typecheck

unittest:
	@bin/run unittest
