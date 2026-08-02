from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / '01_database' / '안심주택DB.grist'
CANONICAL_INSTRUCTION_FILE = 'AGENTS.md'


def _has_exact_filename(path: Path) -> bool:
    """Require exact directory-entry case on every supported filesystem."""
    try:
        return path.parent.is_dir() and any(
            entry.name == path.name and entry.is_file()
            for entry in path.parent.iterdir()
        )
    except OSError:
        return False


required = [
    ROOT / '02_source_pdf' / 'law-1.pdf', ROOT / '02_source_pdf' / 'law-1.json',
    ROOT / '02_source_pdf' / 'law-2.pdf', ROOT / '02_source_pdf' / 'law-2.json',
    DB, ROOT / CANONICAL_INSTRUCTION_FILE,
]
errors=[]
error_details=[]
for p in required:
    exists = _has_exact_filename(p) if p.name == CANONICAL_INSTRUCTION_FILE else p.exists()
    if not exists:
        relative_path = p.relative_to(ROOT).as_posix()
        errors.append(f'missing: {relative_path}')
        error_details.append({'code': 'MISSING_REQUIRED_FILE', 'path': relative_path})

if DB.exists():
    con=sqlite3.connect(DB); cur=con.cursor()
    check=cur.execute('PRAGMA integrity_check').fetchone()[0]
    if check!='ok': errors.append(f'sqlite integrity: {check}')
    names={r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ['Documents','Clauses','Visuals','ExtractedTables','Rules','Cases','SourceElements']:
        if t not in names: errors.append(f'missing Grist table: {t}')
    att={r[0] for r in cur.execute('SELECT id FROM _grist_Attachments')}
    files={r[0] for r in cur.execute('SELECT id FROM _gristsys_Files')}
    if att != files: errors.append(f'attachment/file id mismatch: attachments={len(att)}, files={len(files)}')
    for table,col in [('Documents','SourcePDF'),('Visuals','Image'),('ExtractedTables','TableImage'),('Cases','CaseImage')]:
        if table not in names: continue
        cols={r[1] for r in cur.execute(f'PRAGMA table_info({table})')}
        if col not in cols: continue
        for rid,raw in cur.execute(f'SELECT id,{col} FROM {table} WHERE {col} IS NOT NULL AND {col}!=""'):
            try:
                v=json.loads(raw)
                ids=v if isinstance(v,list) and (not v or v[0]!='L') else []
                for aid in ids:
                    if aid not in att: errors.append(f'broken attachment: {table}.{col} row {rid} -> {aid}')
            except Exception as e:
                errors.append(f'invalid attachment json: {table}.{col} row {rid}: {e}')
    # Reference display columns must point to a hidden helper formula in the source table.
    for table,col in [('Documents','RelatedDocuments'),('Clauses','Document'),('Clauses','ParentClause'),
                      ('Visuals','Document'),('Visuals','Clause'),('Visuals','RelatedTable'),
                      ('ExtractedTables','Document'),('ExtractedTables','Clause'),('Rules','Clause'),
                      ('Cases','Rule'),('Cases','Visual'),('SourceElements','Document'),('SourceElements','Clause')]:
        tr=cur.execute('SELECT id FROM _grist_Tables WHERE tableId=?',(table,)).fetchone()
        if not tr: continue
        ref=cur.execute('SELECT displayCol,visibleCol FROM _grist_Tables_column WHERE parentId=? AND colId=?',(tr[0],col)).fetchone()
        if not ref: continue
        helper=cur.execute('SELECT parentId,colId,isFormula,formula FROM _grist_Tables_column WHERE id=?',(ref[0],)).fetchone() if ref[0] else None
        if not helper or helper[0]!=tr[0] or not str(helper[1]).startswith('gristHelper_Display') or helper[2]!=1:
            errors.append(f'invalid reference display helper: {table}.{col}')
        if not ref[1]: errors.append(f'missing reference visibleCol: {table}.{col}')

    counts={t:cur.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ['Documents','Clauses','Visuals','ExtractedTables','SourceElements']}
    con.close()
else:
    counts={}

manifest=ROOT/'04_visuals'/'manifests'/'visual_manifest.csv'
if manifest.exists():
    with manifest.open(encoding='utf-8-sig') as f:
        rows=list(csv.DictReader(f))
    for r in rows:
        p=ROOT/r['crop_path']
        if not p.exists(): errors.append(f'manifest crop missing: {r["crop_path"]}')
else:
    errors.append('missing visual manifest')

result={
    'status':'PASS' if not errors else 'FAIL',
    'counts':counts,
    'errors':errors,
    'error_details':error_details,
}
print(json.dumps(result,ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors else 1)
