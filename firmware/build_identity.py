"""PlatformIO hook: identify the actual project source used by each firmware build."""
from pathlib import Path
import hashlib

Import("env")  # noqa: F821 -- supplied by PlatformIO/SCons

root = Path(env.subst("$PROJECT_DIR")).resolve().parent
sources = [root / "firmware" / "platformio.ini", root / "BWifiKiller" / "platformio.ini",
           root / "BWifiKiller" / "include" / "app_config.h",
           root / "BWifiKiller" / "src" / "sentinel_main.cpp"]
sources += sorted((root / "firmware" / "include").glob("*.h"))
sources += sorted((root / "firmware" / "src").glob("*.cpp"))
digest = hashlib.sha256()
for source in sources:
    digest.update(source.relative_to(root).as_posix().encode())
    digest.update(source.read_bytes())
digest.update(env.subst("$PIOENV").encode())
env.Append(CPPDEFINES=[("SENTINEL_BUILD_ID", '\\"' + digest.hexdigest()[:16] + '\\"')])
