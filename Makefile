# FM-1 Clock: the everyday commands. The firmware itself is built by ./build.sh (docs/DINGHY_README.md: the toolchain).
#   make test       the clock's host tests: the sound against the reference, the time, the strike, the screen
#   make host       the app on the host with Dinghy's default script: build/host/fm1clock.wav and its screens
#   make tables     firmware/gen/clk_tables.h from tools/clk_model.json and tools/clk_cuckoo.json
#   make art        firmware/gen/clk_art.h from assets/design.png, clk_art_cuckoo.h drawn by tools/gen_art_cuckoo.py
#   make fit        tools/clk_model.json, tools/clk_cuckoo.json from the measurements (~1 min each)
#   make analyze REF=recording.wav   the measurements from the wall clock's recording (numpy, scipy)
#   make analyze-cuckoo REF=recording.wav   and from the cuckoo clock's
#   make fw         the FM-1 package build/fm1clock.fwsc (JieLi toolchain in ~/.jieli, SDK in ~/fw-AC79_AIoT_SDK)
#   make check      what CI runs after the package: the clock's tests, Dinghy's platform tests, fm1-emu
PY ?= python3

.PHONY: test host tables art fit analyze analyze-cuckoo fw check emu clean
test:
	sh tests/run_clock.sh
host:
	sh tests/run_host.sh
tables:
	$(PY) tools/gen_tables.py
art:
	$(PY) tools/gen_art.py
	$(PY) tools/gen_art_cuckoo.py
fit:
	$(PY) -I tools/fit_model.py
	$(PY) -I tools/fit_cuckoo.py
	$(PY) tools/gen_tables.py
analyze:
	$(PY) -I tools/analyze_ref.py $(REF)
analyze-cuckoo:
	$(PY) -I tools/analyze_cuckoo.py $(REF)
fw:
	PYTHON=$(PY) sh build.sh
	sha256sum build/fm1clock.fwsc
emu:
	sh tools/emu_check.sh build/fm1clock.fwsc
check: fw
	sh tests/run_clock.sh
	sh tests/run_tests.sh
	sh tools/emu_ci.sh
clean:
	rm -rf build/host build/gen build/loader build/audio build/emu build/fm1clock* build/clk_*
