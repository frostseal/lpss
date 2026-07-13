# @file Makefile
# Simple installer for LPSS tools

PREFIX ?= /usr/local/bin
TOOLS = lpss_install.py lpss_import.py lpss_ctl.py

.PHONY: install uninstall

install:
	@echo "Installing LPSS tools to $(PREFIX)..."
	@mkdir -p $(PREFIX)
	@for tool in $(TOOLS); do \
		ln -sf "$(CURDIR)/$$tool" "$(PREFIX)/$${tool%.py}"; \
		echo "  $(PREFIX)/$${tool%.py} -> $(CURDIR)/$$tool"; \
	done
	@echo "Done. Make sure $(PREFIX) is in your PATH."

uninstall:
	@echo "Removing LPSS tools from $(PREFIX)..."
	@for tool in $(TOOLS); do \
		rm -f "$(PREFIX)/$${tool%.py}"; \
		echo "  removed $(PREFIX)/$${tool%.py}"; \
	done
	@echo "Done."