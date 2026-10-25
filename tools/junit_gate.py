"""CI gate: the authoritative pytest verdict is the junit XML file.

The macOS runner can segfault at PySide6/Qt teardown *after* the [100%]
line (ledger runs 40175625436 / 40177659243), which masks pytest's real
exit code. The suite is then judged by the file pytest wrote at
sessionfinish - and a missing report is always a failure, never a guess
of green.
"""
import os
import sys
import xml.etree.ElementTree as ET


def main(argv):
    path = argv[1] if len(argv) > 1 else "pytest.xml"
    if not os.path.isfile(path):
        sys.exit(f"FATAL: no junit report at {path} - pytest never reached sessionfinish")

    root = ET.parse(path).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    bad = int(suite.get("failures") or 0) + int(suite.get("errors") or 0)
    print(f"junit verdict: tests={suite.get('tests')} failures={suite.get('failures')} "
          f"errors={suite.get('errors')} skipped={suite.get('skips')}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main(sys.argv)
