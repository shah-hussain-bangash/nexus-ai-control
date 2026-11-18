"""Regenerate portable function inventories after editing the interface catalog."""
from pathlib import Path
import csv
import json

root=Path(__file__).resolve().parents[1]
catalog=json.loads((root/'backend/nexus/interface_catalog.json').read_text())
modules=catalog['modules']
out=root/'docs'
with (out/'PLATFORM_FUNCTION_INVENTORY.csv').open('w',newline='') as handle:
    writer=csv.writer(handle)
    writer.writerow(['Module','Function ID','Function','Priority','Intended roles','Controls','Screen states','Planned endpoint','Dependencies','Runtime activation'])
    for module in modules:
        for feature in module['features']:
            writer.writerow([module['title'],feature['id'],feature['title'],feature['priority'],'; '.join(feature['roles']),'; '.join(field['label'] for field in feature['fields']),'; '.join(feature['states']),feature['planned_path'],'; '.join(feature['dependencies']),feature.get('implementation_note','Inactive: future backend implementation') if feature.get('working_view') else 'Inactive: future backend implementation'])
(out/'PLATFORM_FUNCTION_INVENTORY.json').write_text(json.dumps({'version':catalog['version'],'scope':catalog['scope_boundary'],'modules':[{'id':module['id'],'title':module['title'],'features':module['features']} for module in modules]},indent=2)+'\n')
print(f"Exported {sum(len(module['features']) for module in modules)} function designs. UI reviews do not activate runtime services.")
