#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
[[ $(git -C .deps/aquamarine rev-parse HEAD) == f31c47a1b9d300847d8fc3108ad959448103dfc1 ]]
cross_root="$repo_root/build/aquamarine-sysroot"
source_root="$repo_root/build/aquamarine-src"
mkdir -p "$source_root"
git -C .deps/aquamarine archive HEAD | tar -x -C "$source_root"
patch -d "$source_root" -p1 < rootfs/aquamarine-simpledrm.patch
patch -d "$source_root" -p1 < rootfs/aquamarine-arm32-time.patch
python3 - <<'PY'
from pathlib import Path
root=Path('build/aquamarine-sysroot').resolve()
gcc=list((root/'usr/lib/gcc').glob('*/*'))
assert len(gcc)==1,gcc
Path('build/aquamarine-toolchain.cmake').write_text(f'''
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR arm)
set(CMAKE_SYSROOT "{root}")
set(CMAKE_C_COMPILER /usr/bin/clang)
set(CMAKE_CXX_COMPILER /usr/bin/clang++)
set(CMAKE_C_COMPILER_TARGET arm-linux-gnueabihf)
set(CMAKE_CXX_COMPILER_TARGET arm-linux-gnueabihf)
set(CMAKE_C_FLAGS_INIT "--gcc-install-dir={gcc[0]} -march=armv7-a -mfpu=neon -mfloat-abi=hard")
set(CMAKE_CXX_FLAGS_INIT "--gcc-install-dir={gcc[0]} -march=armv7-a -mfpu=neon -mfloat-abi=hard")
set(CMAKE_EXE_LINKER_FLAGS_INIT "-fuse-ld=lld")
set(CMAKE_SHARED_LINKER_FLAGS_INIT "-fuse-ld=lld")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE BOTH)
''')
PY
export PKG_CONFIG_SYSROOT_DIR="$cross_root"
export PKG_CONFIG_LIBDIR="$cross_root/usr/lib/pkgconfig:$cross_root/usr/share/pkgconfig"
unset PKG_CONFIG_PATH
cmake_tool="$repo_root/build/aquamarine-build-tools/bin/cmake"
"$cmake_tool" -S "$source_root" -B build/aquamarine-arm \
    -DCMAKE_TOOLCHAIN_FILE="$repo_root/build/aquamarine-toolchain.cmake" \
    -Dhyprwayland-scanner_DIR=/usr/lib/cmake/hyprwayland-scanner \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_INSTALL_PREFIX=/usr
"$cmake_tool" --build build/aquamarine-arm --target aquamarine -j4
mkdir -p build/arm/aquamarine-simpledrm
cp build/aquamarine-arm/libaquamarine.so.0.15.1 build/arm/aquamarine-simpledrm/
llvm-strip --strip-debug build/arm/aquamarine-simpledrm/libaquamarine.so.0.15.1
sha256sum build/arm/aquamarine-simpledrm/libaquamarine.so.0.15.1
readelf -h build/arm/aquamarine-simpledrm/libaquamarine.so.0.15.1
python3 - <<'PY'
from pathlib import Path
import hashlib,json,subprocess
p=Path('build/arm/aquamarine-simpledrm/libaquamarine.so.0.15.1')
m={'source_commit':'f31c47a1b9d300847d8fc3108ad959448103dfc1',
   'patches':{n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in
              ('rootfs/aquamarine-simpledrm.patch','rootfs/aquamarine-arm32-time.patch')},
   'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size,
   'compiler':subprocess.check_output(['clang++','--version'],text=True).splitlines()[0],
   'target':'armv7-a neon hard-float','load_directory':'/opt/a6/aquamarine-simpledrm',
   'official_packaged_library_preserved':True}
(p.parent/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
PY
