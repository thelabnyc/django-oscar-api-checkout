.PHONY: translations install_precommit test_precommit fmt

# Create the .po and .mo files used for i18n
translations:
	cd src/oscarapicheckout && \
	django-admin makemessages -a && \
	django-admin compilemessages

install_precommit:
	prek install -t pre-commit && \
	prek install -t commit-msg && \
	prek install -t pre-push

test_precommit: install_precommit
	prek run --all-files

fmt:
	ruff format .
