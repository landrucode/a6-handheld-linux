"""Complete generated ARM runtime ELF dependencies from verified build inputs."""
import hashlib
from pathlib import Path
import re
import shutil
import subprocess

def arm_elf(path):
    with path.open('rb') as stream:
        header = stream.read(20)
    return header[:4] == b'\x7fELF' and header[4:6] == b'\x01\x01' and header[18:20] == b'\x28\x00'

def complete(runtime, global_libraries, library_roots, build_root):
    runtime = runtime.resolve()
    if not runtime.is_relative_to(build_root):
        raise ValueError('Generated runtime must be under build/')
    destination = runtime/'lib'
    queue = [p for folder in ('bin','lib') for p in (runtime/folder).rglob('*')
             if p.is_file() and arm_elf(p)]
    seen = set()
    copied = {}
    while queue:
        obj = queue.pop().resolve()
        if obj in seen:
            continue
        seen.add(obj)
        dynamic = subprocess.check_output(['llvm-readelf','-d',str(obj)],text=True)
        for name in re.findall(r'Shared library: \[([^]]+)\]',dynamic):
            if Path(name).name != name:
                raise ValueError('Unexpected ELF dependency path: '+name)
            target = destination/name
            library = target
            if not target.exists():
                if (global_libraries/name).is_file():
                    library = global_libraries/name
                else:
                    source = next((folder/name for folder in library_roots if (folder/name).is_file()),None)
                    if source is None:
                        raise ValueError('Missing verified ARM runtime dependency: '+name)
                    source = source.resolve()
                    if not source.is_relative_to(build_root) or not arm_elf(source):
                        raise ValueError('Runtime dependency is not a generated ARM input: '+name)
                    target.unlink(missing_ok=True)
                    shutil.copy2(source,target)
                    with target.open('rb') as stream:
                        copied[name] = hashlib.file_digest(stream,'sha256').hexdigest()
            if not library.resolve().is_relative_to(build_root) or not arm_elf(library):
                raise ValueError('Existing runtime dependency is not a generated ARM input: '+name)
            queue.append(library)
    return copied
