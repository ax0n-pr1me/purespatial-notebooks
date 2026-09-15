POETRY ?= poetry
SLUG ?=

.PHONY: install test lint fetch run clean-run

install:
	$(POETRY) install

test:
	$(POETRY) run pytest -q

lint:
	$(POETRY) run ruff check .

## make fetch SLUG=<post-folder>: download that post's public inputs into <post>/data/
fetch:
	@test -n "$(SLUG)" || (echo "usage: make fetch SLUG=<post-folder>" && exit 2)
	cd "$(SLUG)" && $(POETRY) run python fetch.py

## make run SLUG=<post-folder>: execute notebook.py top to bottom and save notebook.ipynb with outputs
run:
	@test -n "$(SLUG)" || (echo "usage: make run SLUG=<post-folder>" && exit 2)
	$(POETRY) run jupytext --to ipynb --execute --run-path "$(CURDIR)/$(SLUG)" -o "$(SLUG)/notebook.ipynb" "$(SLUG)/notebook.py"

## make clean-run SLUG=<post-folder>: drop cached viewsheds and figures (keeps the DEM downloads and field/)
clean-run:
	@test -n "$(SLUG)" || (echo "usage: make clean-run SLUG=<post-folder>" && exit 2)
	rm -f "$(SLUG)"/data/viewshed_*.tif "$(SLUG)"/figures/*.png "$(SLUG)"/result.json "$(SLUG)"/notebook.ipynb
