# Convenience wrapper around build.py. Sets up a local Python venv on first use.
#   make              build the site into docs/
#   make serve        build and preview at http://localhost:8000/
#   make preview      same, including drafts (built into .preview/, not docs/)
#   make new TITLE="My post title"

PY    := .venv/bin/python
STAMP := .venv/.installed

build: $(STAMP)
	$(PY) build.py

serve: $(STAMP)
	$(PY) build.py serve

preview: $(STAMP)
	$(PY) build.py serve --drafts

new: $(STAMP)
	$(PY) build.py new "$(TITLE)"

$(STAMP): requirements.txt
	python3 -m venv .venv
	.venv/bin/pip install --quiet --disable-pip-version-check -r requirements.txt
	touch $(STAMP)

.PHONY: build serve preview new
