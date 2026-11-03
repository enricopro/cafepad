CC ?= gcc
CFLAGS ?= -O3 -Wall -Wextra -fPIC -I./include
LDFLAGS ?= -shared -lm -lbluetooth
AR ?= ar

PREFIX ?= /usr/local
INCLUDEDIR ?= $(PREFIX)/include
LIBDIR ?= $(PREFIX)/lib
PKGCONFIGDIR ?= $(LIBDIR)/pkgconfig
BINDIR ?= $(PREFIX)/bin

TARGET_SO = libcafepad.so
TARGET_A  = libcafepad.a
TARGET_PC = cafepad.pc

COMPAT_SO = libwiiupro.so
COMPAT_A  = libwiiupro.a
COMPAT_PC = wiiupro.pc

all: $(TARGET_SO) $(TARGET_A) $(TARGET_PC) $(COMPAT_SO) $(COMPAT_A) $(COMPAT_PC) test_controller

$(TARGET_SO): src/cafepad.o
	$(CC) $(LDFLAGS) -o $@ $^

$(TARGET_A): src/cafepad.o
	$(AR) rcs $@ $^

src/cafepad.o: src/cafepad.c include/cafepad.h
	$(CC) $(CFLAGS) -c $< -o $@

$(TARGET_PC): cafepad.pc.in
	sed 's|@PREFIX@|$(PREFIX)|g' $< > $@

$(COMPAT_SO): $(TARGET_SO)
	ln -sf $(TARGET_SO) $@

$(COMPAT_A): $(TARGET_A)
	ln -sf $(TARGET_A) $@

$(COMPAT_PC): wiiupro.pc.in
	sed 's|@PREFIX@|$(PREFIX)|g' $< > $@

test_controller: examples/test_controller.c $(TARGET_A)
	$(CC) -O3 -Wall -I./include examples/test_controller.c $(TARGET_A) -lm -lbluetooth -o $@

install: all
	install -d $(DESTDIR)$(INCLUDEDIR)
	install -d $(DESTDIR)$(LIBDIR)
	install -d $(DESTDIR)$(PKGCONFIGDIR)
	install -m 644 include/cafepad.h $(DESTDIR)$(INCLUDEDIR)/
	install -m 644 include/wiiupro.h $(DESTDIR)$(INCLUDEDIR)/
	install -m 755 $(TARGET_SO) $(DESTDIR)$(LIBDIR)/
	install -m 644 $(TARGET_A) $(DESTDIR)$(LIBDIR)/
	install -m 644 $(TARGET_PC) $(DESTDIR)$(PKGCONFIGDIR)/
	ln -sf $(TARGET_SO) $(DESTDIR)$(LIBDIR)/$(COMPAT_SO)
	ln -sf $(TARGET_A) $(DESTDIR)$(LIBDIR)/$(COMPAT_A)
	install -m 644 $(COMPAT_PC) $(DESTDIR)$(PKGCONFIGDIR)/
	@if [ -x /sbin/ldconfig ] || [ -x /usr/sbin/ldconfig ]; then \
		ldconfig 2>/dev/null || true; \
	fi

uninstall:
	rm -f $(DESTDIR)$(INCLUDEDIR)/cafepad.h
	rm -f $(DESTDIR)$(INCLUDEDIR)/wiiupro.h
	rm -f $(DESTDIR)$(LIBDIR)/$(TARGET_SO)
	rm -f $(DESTDIR)$(LIBDIR)/$(TARGET_A)
	rm -f $(DESTDIR)$(LIBDIR)/$(COMPAT_SO)
	rm -f $(DESTDIR)$(LIBDIR)/$(COMPAT_A)
	rm -f $(DESTDIR)$(PKGCONFIGDIR)/$(TARGET_PC)
	rm -f $(DESTDIR)$(PKGCONFIGDIR)/$(COMPAT_PC)
	@if [ -x /sbin/ldconfig ] || [ -x /usr/sbin/ldconfig ]; then \
		ldconfig 2>/dev/null || true; \
	fi

clean:
	rm -f src/*.o *.so *.a $(TARGET_PC) $(COMPAT_PC) $(COMPAT_SO) $(COMPAT_A) test_controller

.PHONY: all clean install uninstall
