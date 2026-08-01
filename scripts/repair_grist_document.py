from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / '01_database' / '안심주택DB.grist'

REFERENCE_COLUMNS = [
    ('Documents', 'RelatedDocuments', 'Documents', 'Title'),
    ('Clauses', 'Document', 'Documents', 'Title'),
    ('Clauses', 'ParentClause', 'Clauses', 'ClauseID'),
    ('Visuals', 'Document', 'Documents', 'Title'),
    ('Visuals', 'Clause', 'Clauses', 'ClauseID'),
    ('Visuals', 'RelatedTable', 'ExtractedTables', 'TableID'),
    ('ExtractedTables', 'Document', 'Documents', 'Title'),
    ('ExtractedTables', 'Clause', 'Clauses', 'ClauseID'),
    ('Rules', 'Clause', 'Clauses', 'ClauseID'),
    ('Cases', 'Rule', 'Rules', 'RuleID'),
    ('Cases', 'Visual', 'Visuals', 'VisualID'),
    ('SourceElements', 'Document', 'Documents', 'Title'),
    ('SourceElements', 'Clause', 'Clauses', 'ClauseID'),
]

LIST_COLUMNS = [
    ('Documents', 'SourcePDF'),
    ('Documents', 'RelatedDocuments'),
    ('Visuals', 'Image'),
    ('ExtractedTables', 'TableImage'),
    ('Cases', 'CaseImage'),
]


def repair_grist_document(db_path: Path = DEFAULT_DB, make_backup: bool = False) -> dict:
    db_path = Path(db_path)
    if make_backup:
        backup = db_path.with_suffix(db_path.suffix + '.before-repair')
        shutil.copy2(db_path, backup)

    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute('BEGIN IMMEDIATE')

    def table_ref(table: str) -> int:
        row = cur.execute('SELECT id FROM _grist_Tables WHERE tableId=?', (table,)).fetchone()
        if not row:
            raise KeyError(f'Grist table not found: {table}')
        return int(row[0])

    def col_meta_id(table: str, col: str) -> int:
        row = cur.execute(
            'SELECT id FROM _grist_Tables_column WHERE parentId=? AND colId=?',
            (table_ref(table), col),
        ).fetchone()
        if not row:
            raise KeyError(f'Grist column not found: {table}.{col}')
        return int(row[0])

    converted: dict[str, int] = {}
    for table, col in LIST_COLUMNS:
        table_names = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if table not in table_names:
            continue
        physical_cols = {r[1] for r in cur.execute(f'PRAGMA table_info("{table}")')}
        if col not in physical_cols:
            continue
        count = 0
        for row_id, raw in cur.execute(
            f'SELECT id,"{col}" FROM "{table}" WHERE "{col}" IS NOT NULL AND "{col}" != ""'
        ).fetchall():
            if not isinstance(raw, str):
                continue
            try:
                value = json.loads(raw)
            except Exception:
                continue
            # REST/API typed list values use ["L", ...], while .grist SQLite
            # typed list columns store the row/file ids as a plain JSON array.
            if isinstance(value, list) and value and value[0] == 'L':
                cur.execute(
                    f'UPDATE "{table}" SET "{col}"=? WHERE id=?',
                    (json.dumps(value[1:], ensure_ascii=False, separators=(',', ':')), row_id),
                )
                count += 1
        converted[f'{table}.{col}'] = count

    helper_count = 0
    for table, ref_col, target_table, target_col in REFERENCE_COLUMNS:
        try:
            source_table_ref = table_ref(table)
            target_visible_col = col_meta_id(target_table, target_col)
        except KeyError:
            continue

        ref_row = cur.execute(
            'SELECT id,type FROM _grist_Tables_column WHERE parentId=? AND colId=?',
            (source_table_ref, ref_col),
        ).fetchone()
        if not ref_row:
            continue
        ref_meta_id, ref_type = int(ref_row[0]), str(ref_row[1])
        formula = f'${ref_col}.{target_col}'

        helper = cur.execute(
            '''SELECT id,colId FROM _grist_Tables_column
               WHERE parentId=? AND isFormula=1 AND formula=?
                 AND colId LIKE 'gristHelper_Display%'
               ORDER BY id LIMIT 1''',
            (source_table_ref, formula),
        ).fetchone()

        if helper:
            helper_meta_id, helper_col_id = int(helper[0]), str(helper[1])
        else:
            used = {
                str(r[0]) for r in cur.execute(
                    'SELECT colId FROM _grist_Tables_column WHERE parentId=?',
                    (source_table_ref,),
                )
            }
            helper_col_id = 'gristHelper_Display'
            suffix = 2
            while helper_col_id in used:
                helper_col_id = f'gristHelper_Display{suffix}'
                suffix += 1

            physical_cols = {r[1] for r in cur.execute(f'PRAGMA table_info("{table}")')}
            if helper_col_id not in physical_cols:
                cur.execute(f'ALTER TABLE "{table}" ADD COLUMN "{helper_col_id}" BLOB DEFAULT NULL')

            helper_meta_id = int(
                cur.execute('SELECT COALESCE(MAX(id),0)+1 FROM _grist_Tables_column').fetchone()[0]
            )
            parent_pos = float(
                cur.execute(
                    'SELECT COALESCE(MAX(parentPos),0)+1 FROM _grist_Tables_column WHERE parentId=?',
                    (source_table_ref,),
                ).fetchone()[0]
            )
            cur.execute(
                '''INSERT INTO _grist_Tables_column
                   (id,parentId,parentPos,colId,type,widgetOptions,isFormula,formula,label,description,
                    untieColIdFromLabel,summarySourceCol,displayCol,visibleCol,rules,reverseCol,recalcWhen,recalcDeps)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (
                    helper_meta_id, source_table_ref, parent_pos, helper_col_id, 'Any', '', 1,
                    formula, helper_col_id, f'{ref_col} 표시용 숨김 수식 열',
                    0, 0, 0, 0, None, 0, 0, None,
                ),
            )
            helper_count += 1

        widget_options = json.dumps(
            {'widget': 'Reference', 'alignment': 'left', 'rulesOptions': []},
            ensure_ascii=False,
            separators=(',', ':'),
        )
        cur.execute(
            '''UPDATE _grist_Tables_column
               SET displayCol=?, visibleCol=?, widgetOptions=?
               WHERE id=?''',
            (helper_meta_id, target_visible_col, widget_options, ref_meta_id),
        )

        # Formula values will be recalculated by Grist. Pre-filling scalar helpers
        # also makes single-reference labels available immediately on first open.
        if ref_type.startswith('Ref:'):
            target_values = {
                row_id: value
                for row_id, value in cur.execute(
                    f'SELECT id,"{target_col}" FROM "{target_table}"'
                )
            }
            for source_row_id, target_row_id in cur.execute(
                f'SELECT id,"{ref_col}" FROM "{table}"'
            ).fetchall():
                value = None if target_row_id in (None, 0, '') else target_values.get(target_row_id)
                cur.execute(
                    f'UPDATE "{table}" SET "{helper_col_id}"=? WHERE id=?',
                    (value, source_row_id),
                )

    # View fields inherit display behavior from the underlying column.
    reference_meta_ids = []
    for table, ref_col, _, _ in REFERENCE_COLUMNS:
        try:
            reference_meta_ids.append(col_meta_id(table, ref_col))
        except KeyError:
            pass
    if reference_meta_ids:
        marks = ','.join('?' for _ in reference_meta_ids)
        cur.execute(
            f'UPDATE _grist_Views_section_field SET displayCol=0, visibleCol=0 '
            f'WHERE colRef IN ({marks})',
            reference_meta_ids,
        )

    con.commit()
    integrity = cur.execute('PRAGMA integrity_check').fetchone()[0]
    if integrity != 'ok':
        con.close()
        raise RuntimeError(f'SQLite integrity check failed: {integrity}')

    result = {
        'status': 'PASS',
        'database': str(db_path),
        'converted_list_cells': converted,
        'new_display_helpers': helper_count,
        'integrity': integrity,
    }
    con.close()
    return result


if __name__ == '__main__':
    print(json.dumps(repair_grist_document(make_backup=True), ensure_ascii=False, indent=2))
