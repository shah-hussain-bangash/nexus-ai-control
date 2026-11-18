"""Copy shared UI into the isolated synthetic harness; never copy its real API client."""
from pathlib import Path
import shutil

root=Path(__file__).resolve().parents[1]
for source in (root/'frontend/src').iterdir():
    if source.is_file() and source.name!='api.ts':
        shutil.copyfile(source,root/'demo-preview/src'/source.name)
main=root/'demo-preview/src/main.tsx'
main.write_text(main.read_text().replace('SYNTHETIC DATA','PREVIEW DATA'))
print('Shared UI synchronized. The isolated demo API and synthetic snapshot were preserved.')
