from __future__ import annotations

import csv
import hashlib
import json
import mimetypes
import shutil
import sqlite3
import time
from collections import defaultdict
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

ROOT = Path(__file__).resolve().parents[1] if Path(__file__).resolve().parent.name == 'scripts' else Path('/mnt/data/안심주택DB_workspace')
DB_PATH = ROOT / '01_database' / '안심주택DB.grist'
SRC_DIR = ROOT / '02_source_pdf'
EXTRACTED_DIR = ROOT / '03_extracted_images' / 'pdf_embedded'
VISUAL_ROOT = ROOT / '04_visuals'
PAGE_DIR = VISUAL_ROOT / 'page_renders'
IMAGE_CROP_DIR = VISUAL_ROOT / 'image_context_crops'
TABLE_CROP_DIR = VISUAL_ROOT / 'table_crops'
COMPOSITE_DIR = VISUAL_ROOT / 'composite_diagrams'
MANIFEST_DIR = VISUAL_ROOT / 'manifests'

DPI_CROP = 220
DPI_PAGE = 150

for d in [PAGE_DIR, IMAGE_CROP_DIR, TABLE_CROP_DIR, COMPOSITE_DIR, MANIFEST_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def bottom_bbox_to_fitz(page: fitz.Page, bbox: tuple[float, float, float, float], margin: float = 0) -> fitz.Rect:
    x0, y_bottom, x1, y_top = map(float, bbox)
    rect = fitz.Rect(x0 - margin, page.rect.height - y_top - margin, x1 + margin, page.rect.height - y_bottom + margin)
    return rect & page.rect


def fitz_bbox_to_bottom(page: fitz.Page, rect: fitz.Rect) -> tuple[float, float, float, float]:
    return (
        round(rect.x0, 3),
        round(page.rect.height - rect.y1, 3),
        round(rect.x1, 3),
        round(page.rect.height - rect.y0, 3),
    )


def render_clip(page: fitz.Page, rect: fitz.Rect, out: Path, dpi: int = DPI_CROP) -> tuple[int, int, str]:
    rect = rect & page.rect
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), clip=rect, alpha=False)
    pix.save(str(out))
    return pix.width, pix.height, sha256_file(out)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields or ['empty'], extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def ensure_column(con: sqlite3.Connection, table_id: str, col_id: str, label: str, col_type: str,
                  description: str = '', widget_options: str = '', display_target: tuple[str, str] | None = None) -> int:
    cur = con.cursor()
    table_ref = cur.execute('SELECT id FROM _grist_Tables WHERE tableId=?', (table_id,)).fetchone()[0]
    found = cur.execute('SELECT id FROM _grist_Tables_column WHERE parentId=? AND colId=?', (table_ref, col_id)).fetchone()
    if found:
        return int(found[0])

    physical_type = 'INTEGER' if col_type.startswith('Ref:') else ('TEXT' if col_type in ('Text', 'Choice', 'Attachments') else 'NUMERIC')
    default = '0' if physical_type != 'TEXT' or col_type.startswith('Ref:') else "''"
    if col_type == 'Attachments':
        default = 'NULL'
    con.execute(f'ALTER TABLE "{table_id}" ADD COLUMN "{col_id}" {physical_type} DEFAULT {default}')

    col_ref = int(cur.execute('SELECT COALESCE(MAX(id),0)+1 FROM _grist_Tables_column').fetchone()[0])
    parent_pos = float(cur.execute('SELECT COALESCE(MAX(parentPos),0)+1 FROM _grist_Tables_column WHERE parentId=?', (table_ref,)).fetchone()[0])
    display_col = 0
    if display_target:
        target_ref = cur.execute('SELECT id FROM _grist_Tables WHERE tableId=?', (display_target[0],)).fetchone()[0]
        display_col = cur.execute('SELECT id FROM _grist_Tables_column WHERE parentId=? AND colId=?', (target_ref, display_target[1])).fetchone()[0]
    cur.execute('''INSERT INTO _grist_Tables_column
        (id,parentId,parentPos,colId,type,widgetOptions,isFormula,formula,label,description,untieColIdFromLabel,
         summarySourceCol,displayCol,visibleCol,rules,reverseCol,recalcWhen,recalcDeps)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (col_ref, table_ref, parent_pos, col_id, col_type, widget_options or '', 0, '', label, description,
         0, 0, display_col, 0, None, 0, 0, None))

    section_ids = [r[0] for r in cur.execute('SELECT id FROM _grist_Views_section WHERE tableRef=?', (table_ref,))]
    next_field = int(cur.execute('SELECT COALESCE(MAX(id),0)+1 FROM _grist_Views_section_field').fetchone()[0])
    for sid in section_ids:
        pos = float(cur.execute('SELECT COALESCE(MAX(parentPos),0)+1 FROM _grist_Views_section_field WHERE parentId=?', (sid,)).fetchone()[0])
        cur.execute('''INSERT INTO _grist_Views_section_field
            (id,parentId,parentPos,colRef,width,widgetOptions,displayCol,visibleCol,filter,rules)
            VALUES(?,?,?,?,?,?,?,?,?,?)''', (next_field, sid, pos, col_ref, 140, '', 0, 0, '', None))
        next_field += 1
    return col_ref


def add_attachment(con: sqlite3.Connection, path: Path, display_name: str | None = None) -> int:
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    ext = path.suffix.lower()
    ident = f'{digest}{ext}'
    row = con.execute('SELECT id FROM _grist_Attachments WHERE fileIdent=?', (ident,)).fetchone()
    if row:
        return int(row[0])
    aid = int(con.execute('SELECT COALESCE(MAX(id),0)+1 FROM _grist_Attachments').fetchone()[0])
    mime = mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
    width = height = 0
    if mime.startswith('image/'):
        try:
            with Image.open(path) as im:
                width, height = im.size
        except Exception:
            pass
    now = int(time.time())
    con.execute('''INSERT INTO _grist_Attachments
        (id,fileIdent,fileName,fileType,fileSize,fileExt,imageHeight,imageWidth,timeDeleted,timeUploaded)
        VALUES(?,?,?,?,?,?,?,?,?,?)''',
        (aid, ident, display_name or path.name, mime, len(data), ext, height, width, None, now))
    con.execute('INSERT INTO _gristsys_Files(id,ident,data,storageId) VALUES(?,?,?,?)',
                (aid, ident, sqlite3.Binary(data), ''))
    return aid


def grist_attachment(aid: int | None) -> str | None:
    return json.dumps([aid], ensure_ascii=False, separators=(',', ':')) if aid else None


def clause_for_bbox(con: sqlite3.Connection, doc_id: int, page_no: int, bbox_bottom: tuple[float, float, float, float]) -> int:
    x0, y0, x1, y1 = bbox_bottom
    cy = (y0 + y1) / 2
    rows = con.execute('''SELECT Clause,BBoxLeft,BBoxBottom,BBoxRight,BBoxTop,OrderNo
                          FROM SourceElements
                          WHERE Document=? AND Page=? AND Clause>0 AND ElementType NOT IN ('image','table')''',
                       (doc_id, page_no)).fetchall()
    best = None
    for clause, ex0, ey0, ex1, ey1, order_no in rows:
        if not ey0 and not ey1:
            continue
        ecy = (float(ey0) + float(ey1)) / 2
        if y0 <= ecy <= y1:
            dist = 0
        else:
            dist = min(abs(ecy - y0), abs(ecy - y1))
        # Prefer text above the visual when equally close.
        above_penalty = 0 if ecy >= cy else 3
        score = dist + above_penalty
        if best is None or score < best[0]:
            best = (score, int(clause))
    if best:
        return best[1]
    rows = con.execute('''SELECT id,StartPage,EndPage FROM Clauses
                          WHERE Document=? AND StartPage<=? AND EndPage>=?
                          ORDER BY StartPage DESC,id DESC''', (doc_id, page_no, page_no)).fetchall()
    return int(rows[0][0]) if rows else 0


def clause_context(con: sqlite3.Connection, clause_id: int) -> str:
    if not clause_id:
        return ''
    row = con.execute('SELECT ClauseID,RawText FROM Clauses WHERE id=?', (clause_id,)).fetchone()
    if not row:
        return ''
    return f'{row[0]} / {str(row[1] or "")[:900]}'


def load_occurrence_rows(doc_code: str) -> list[dict]:
    p = EXTRACTED_DIR / doc_code.lower().replace('law', 'law-') / 'visible_occurrences_manifest.csv'
    # Folder is law-1/law-2; normalize explicitly.
    p = EXTRACTED_DIR / ('law-1' if doc_code == 'LAW1' else 'law-2') / 'visible_occurrences_manifest.csv'
    if not p.exists():
        return []
    with p.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def load_unique_rows(doc_code: str) -> list[dict]:
    p = EXTRACTED_DIR / ('law-1' if doc_code == 'LAW1' else 'law-2') / 'visible_unique_images_manifest.csv'
    if not p.exists():
        return []
    with p.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    con.execute('PRAGMA foreign_keys=OFF')

    ensure_column(con, 'Visuals', 'SourceKey', '원본키', 'Text', 'PDF xref, OpenDataLoader 요소 또는 표 ID')
    ensure_column(con, 'Visuals', 'RelatedTable', '연결표', 'Ref:ExtractedTables', '표 크롭의 원본 표', display_target=('ExtractedTables', 'TableID'))
    ensure_column(con, 'Visuals', 'PixelWidth', '픽셀너비', 'Int', '첨부 이미지 너비')
    ensure_column(con, 'Visuals', 'PixelHeight', '픽셀높이', 'Int', '첨부 이미지 높이')
    ensure_column(con, 'ExtractedTables', 'TableImage', '표이미지', 'Attachments', 'PDF 페이지 렌더링 기반 표 크롭')

    # Extend VisualType choices.
    visual_tref = con.execute("SELECT id FROM _grist_Tables WHERE tableId='Visuals'").fetchone()[0]
    cinfo = con.execute("SELECT id,widgetOptions FROM _grist_Tables_column WHERE parentId=? AND colId='VisualType'", (visual_tref,)).fetchone()
    try:
        opts = json.loads(cinfo[1] or '{}')
    except Exception:
        opts = {}
    choices = list(opts.get('choices') or [])
    for choice in ['PDF 고유 이미지', '페이지 배치 이미지', '도식 크롭', '표 크롭', '복합 도식', '페이지 전체']:
        if choice not in choices:
            choices.append(choice)
    opts.update({'widget': 'TextBox', 'choices': choices, 'alignment': 'left', 'choiceOptions': opts.get('choiceOptions', {})})
    con.execute('UPDATE _grist_Tables_column SET widgetOptions=? WHERE id=?',
                (json.dumps(opts, ensure_ascii=False, separators=(',', ':')), cinfo[0]))

    documents = {row[1]: {'id': row[0], 'code': row[1]} for row in con.execute('SELECT id,DocumentCode FROM Documents')}
    clause_code = {row[0]: row[1] for row in con.execute('SELECT id,ClauseID FROM Clauses')}
    table_by_id = {row[1]: {'row_id': row[0], 'doc': row[2], 'clause': row[3], 'page': row[4],
                            'bbox': (row[5], row[6], row[7], row[8])}
                   for row in con.execute('SELECT id,TableID,Document,Clause,StartPage,BBoxLeft,BBoxBottom,BBoxRight,BBoxTop FROM ExtractedTables')}

    # Remove previous generated crop records when rebuilding, but preserve original OpenDataLoader image rows.
    generated_prefixes = ('PDF-', 'OCC-', 'TBL-', 'COMP-', 'PAGE-')
    old_rows = con.execute('SELECT id,VisualID FROM Visuals').fetchall()
    for rid, vid in old_rows:
        if any(str(vid).startswith(prefix) for prefix in generated_prefixes):
            con.execute('DELETE FROM Visuals WHERE id=?', (rid,))

    manifests: list[dict] = []
    page_manifest: list[dict] = []
    composite_candidates: dict[tuple[int, int, int], list[dict]] = defaultdict(list)
    next_visual_row = int(con.execute('SELECT COALESCE(MAX(id),0)+1 FROM Visuals').fetchone()[0])
    next_sort = float(con.execute('SELECT COALESCE(MAX(manualSort),0)+1 FROM Visuals').fetchone()[0])

    def insert_visual(*, visual_id: str, doc_id: int, clause_id: int, page_no: int, visual_type: str,
                      path: Path, source_path: str, bbox_bottom: tuple[float, float, float, float],
                      source_key: str = '', related_table: int = 0, description: str = '', review_memo: str = '') -> None:
        nonlocal next_visual_row, next_sort
        aid = add_attachment(con, path, path.name)
        with Image.open(path) as im:
            pw, ph = im.size
        digest = sha256_file(path)
        context = clause_context(con, clause_id)
        duplicate_group = f'VIS-{digest[:12].upper()}'
        con.execute('''INSERT INTO Visuals
            (id,manualSort,VisualID,Document,Clause,Page,VisualType,Image,SourcePath,
             BBoxLeft,BBoxBottom,BBoxRight,BBoxTop,OCRText,Description,ContextText,SHA256,
             DuplicateGroup,IsPrimary,ReviewStatus,ReviewMemo,SourceKey,RelatedTable,PixelWidth,PixelHeight)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (next_visual_row, next_sort, visual_id, doc_id, clause_id, page_no, visual_type,
             grist_attachment(aid), source_path, *bbox_bottom, '', description, context, digest,
             duplicate_group, 1, '자동 추출', review_memo or 'PDF 페이지 렌더링 기반 자동 생성. 원본 대조 필요.',
             source_key, related_table, pw, ph))
        manifests.append({
            'visual_id': visual_id,
            'document_id': doc_id,
            'clause_row_id': clause_id,
            'clause_id': clause_code.get(clause_id, ''),
            'page': page_no,
            'visual_type': visual_type,
            'source_key': source_key,
            'related_table_row_id': related_table,
            'source_path': source_path,
            'crop_path': str(path.relative_to(ROOT)).replace('\\', '/'),
            'bbox_left': bbox_bottom[0], 'bbox_bottom': bbox_bottom[1],
            'bbox_right': bbox_bottom[2], 'bbox_top': bbox_bottom[3],
            'pixel_width': pw, 'pixel_height': ph, 'sha256': digest,
        })
        next_visual_row += 1
        next_sort += 1

    for doc_code, stem in [('LAW1', 'law-1'), ('LAW2', 'law-2')]:
        doc_id = documents[doc_code]['id']
        pdf_path = SRC_DIR / f'{stem}.pdf'
        pdf = fitz.open(pdf_path)
        occurrence_rows = load_occurrence_rows(doc_code)
        unique_rows = load_unique_rows(doc_code)

        # Exact occurrence bboxes indexed by xref; used to assign page and clause to unique images.
        occ_by_xref: dict[str, list[dict]] = defaultdict(list)
        for row in occurrence_rows:
            if row.get('xref'):
                occ_by_xref[str(row['xref'])].append(row)

        # All visible unique PDF images.
        for idx, row in enumerate(unique_rows, start=1):
            file_name = row.get('file') or ''
            if not file_name:
                continue
            src = EXTRACTED_DIR / stem / '02_visible_unique_images' / file_name
            if not src.exists():
                continue
            xref = str(row.get('xref') or '')
            first = occ_by_xref.get(xref, [{}])[0]
            page_no = int(float(first.get('page') or 0))
            if page_no:
                page = pdf[page_no - 1]
                top_rect = fitz.Rect(float(first.get('bbox_left') or 0), float(first.get('bbox_top') or 0),
                                     float(first.get('bbox_right') or 0), float(first.get('bbox_bottom') or 0))
                bbox_bottom = fitz_bbox_to_bottom(page, top_rect)
                clause_id = clause_for_bbox(con, doc_id, page_no, bbox_bottom)
            else:
                bbox_bottom = (0, 0, 0, 0)
                clause_id = 0
            insert_visual(
                visual_id=f'PDF-{doc_code}-U{idx:03d}', doc_id=doc_id, clause_id=clause_id,
                page_no=page_no, visual_type='PDF 고유 이미지', path=src,
                source_path=str(src.relative_to(ROOT)).replace('\\', '/'), bbox_bottom=bbox_bottom,
                source_key=f'xref:{xref}', description='PDF 내부에서 직접 추출하고 투명 마스크를 합성한 고유 이미지.',
                review_memo='동일 이미지가 여러 페이지에 배치될 수 있음. 정확한 위치는 페이지 배치 이미지 레코드 확인.'
            )

        # Actual page placements with context margin.
        pages_with_visuals: set[int] = set()
        for idx, row in enumerate(occurrence_rows, start=1):
            page_no = int(float(row.get('page') or 0))
            crop_name = row.get('crop_file') or ''
            if not page_no or not crop_name:
                continue
            page = pdf[page_no - 1]
            top_rect = fitz.Rect(float(row['bbox_left']), float(row['bbox_top']), float(row['bbox_right']), float(row['bbox_bottom']))
            expanded = (top_rect + (-22, -22, 22, 22)) & page.rect
            out = IMAGE_CROP_DIR / f'{stem}_p{page_no:03d}_occ{idx:03d}_xref{int(float(row.get("xref") or 0)):05d}.png'
            pw, ph, digest = render_clip(page, expanded, out)
            bbox_bottom = fitz_bbox_to_bottom(page, expanded)
            clause_id = clause_for_bbox(con, doc_id, page_no, bbox_bottom)
            source_key = f'xref:{row.get("xref")};occurrence:{row.get("occurrence") or idx}'
            insert_visual(
                visual_id=f'OCC-{doc_code}-{idx:03d}', doc_id=doc_id, clause_id=clause_id,
                page_no=page_no, visual_type='페이지 배치 이미지', path=out,
                source_path=str(out.relative_to(ROOT)).replace('\\', '/'), bbox_bottom=bbox_bottom,
                source_key=source_key, description='PDF 페이지에 실제 배치된 이미지와 주변 여백을 포함한 문맥 크롭.'
            )
            pages_with_visuals.add(page_no)
            composite_candidates[(doc_id, page_no, clause_id)].append({'rect': expanded, 'kind': 'image', 'source_key': source_key})

        # Tables as visual crops, linked back to ExtractedTables.
        table_items = [(tid, info) for tid, info in table_by_id.items() if info['doc'] == doc_id]
        for idx, (table_id, info) in enumerate(table_items, start=1):
            page_no = int(info['page'])
            page = pdf[page_no - 1]
            rect = bottom_bbox_to_fitz(page, info['bbox'], margin=10)
            out = TABLE_CROP_DIR / f'{stem}_p{page_no:03d}_{table_id}.png'
            pw, ph, digest = render_clip(page, rect, out)
            bbox_bottom = fitz_bbox_to_bottom(page, rect)
            aid = add_attachment(con, out, out.name)
            con.execute('UPDATE ExtractedTables SET TableImage=? WHERE id=?', (grist_attachment(aid), info['row_id']))
            insert_visual(
                visual_id=f'TBL-{doc_code}-{idx:03d}', doc_id=doc_id, clause_id=int(info['clause'] or 0),
                page_no=page_no, visual_type='표 크롭', path=out,
                source_path=str(out.relative_to(ROOT)).replace('\\', '/'), bbox_bottom=bbox_bottom,
                source_key=table_id, related_table=info['row_id'], description=f'{table_id}의 PDF 페이지 렌더링 기반 표 크롭.'
            )
            pages_with_visuals.add(page_no)
            composite_candidates[(doc_id, page_no, int(info['clause'] or 0))].append({'rect': rect, 'kind': 'table', 'source_key': table_id})

        # Composite crops when two or more visual elements belong to the same clause on one page.
        comp_idx = 0
        for (g_doc, page_no, clause_id), items in sorted(composite_candidates.items()):
            if g_doc != doc_id or len(items) < 2:
                continue
            page = pdf[page_no - 1]
            union = fitz.Rect(items[0]['rect'])
            for item in items[1:]:
                union |= item['rect']
            union = (union + (-18, -20, 18, 22)) & page.rect
            # Avoid near-full-page composites; page render already provides that context.
            if union.get_area() > page.rect.get_area() * 0.82:
                continue
            comp_idx += 1
            out = COMPOSITE_DIR / f'{stem}_p{page_no:03d}_clause{clause_id:04d}_composite{comp_idx:03d}.png'
            render_clip(page, union, out)
            bbox_bottom = fitz_bbox_to_bottom(page, union)
            kinds = sorted({i['kind'] for i in items})
            insert_visual(
                visual_id=f'COMP-{doc_code}-{comp_idx:03d}', doc_id=doc_id, clause_id=clause_id,
                page_no=page_no, visual_type='복합 도식', path=out,
                source_path=str(out.relative_to(ROOT)).replace('\\', '/'), bbox_bottom=bbox_bottom,
                source_key=';'.join(i['source_key'] for i in items),
                description=f'같은 페이지·조항의 시각요소 {len(items)}개({", ".join(kinds)})를 통합한 복합 도식 크롭.'
            )
            pages_with_visuals.add(page_no)

        # Full-page context render for every page that contains a generated visual.
        for page_no in sorted(pages_with_visuals):
            page = pdf[page_no - 1]
            out = PAGE_DIR / f'{stem}_page_{page_no:03d}.png'
            pix = page.get_pixmap(matrix=fitz.Matrix(DPI_PAGE / 72, DPI_PAGE / 72), alpha=False)
            pix.save(str(out))
            bbox_bottom = (0.0, 0.0, round(page.rect.width, 3), round(page.rect.height, 3))
            insert_visual(
                visual_id=f'PAGE-{doc_code}-{page_no:03d}', doc_id=doc_id, clause_id=0,
                page_no=page_no, visual_type='페이지 전체', path=out,
                source_path=str(out.relative_to(ROOT)).replace('\\', '/'), bbox_bottom=bbox_bottom,
                source_key=f'page:{page_no}', description='시각자료 위치 확인용 PDF 전체 페이지 렌더링.',
                review_memo='문맥 확인용. 규칙·사례의 직접 근거로 사용할 때는 세부 크롭과 원본 PDF를 함께 확인.'
            )
            with Image.open(out) as im:
                page_manifest.append({'document': doc_code, 'page': page_no,
                                      'file': str(out.relative_to(ROOT)).replace('\\', '/'),
                                      'pixel_width': im.width, 'pixel_height': im.height,
                                      'sha256': sha256_file(out)})
        pdf.close()

    # Guide additions.
    guide_existing = {r[0] for r in con.execute('SELECT Topic FROM Guide')}
    guide_add = [
        ('시각자료 구성', '도식 테이블에는 OpenDataLoader 이미지, PDF 고유 이미지, 페이지 배치 이미지, 표 크롭, 복합 도식, 전체 페이지 렌더링이 함께 저장됩니다. 유형 필터로 필요한 자료만 표시하십시오.'),
        ('이미지 연결', '표 테이블의 표이미지 열은 PDF 렌더링 기반 크롭과 연결됩니다. 도식의 연결표 열로 같은 이미지를 표 레코드와 교차 확인할 수 있습니다.'),
        ('재생성', '원본 PDF 또는 JSON이 바뀌면 scripts/rebuild_visuals_and_grist.py를 실행하고 scripts/validate_workspace.py로 검증하십시오.'),
    ]
    next_guide = int(con.execute('SELECT COALESCE(MAX(id),0)+1 FROM Guide').fetchone()[0])
    next_order = int(con.execute('SELECT COALESCE(MAX(OrderNo),0)+1 FROM Guide').fetchone()[0])
    for topic, content in guide_add:
        if topic in guide_existing:
            con.execute('UPDATE Guide SET Content=? WHERE Topic=?', (content, topic))
        else:
            con.execute('INSERT INTO Guide(id,manualSort,Topic,Content,OrderNo) VALUES(?,?,?,?,?)',
                        (next_guide, next_guide, topic, content, next_order))
            next_guide += 1
            next_order += 1

    con.commit()
    check = con.execute('PRAGMA integrity_check').fetchone()[0]
    if check != 'ok':
        raise RuntimeError(f'Grist SQLite integrity check failed: {check}')

    # Verify all attachment references resolve.
    attachment_ids = {r[0] for r in con.execute('SELECT id FROM _grist_Attachments')}
    broken = []
    for table, col in [('Documents', 'SourcePDF'), ('Visuals', 'Image'), ('ExtractedTables', 'TableImage'), ('Cases', 'CaseImage')]:
        for rid, raw in con.execute(f'SELECT id,{col} FROM {table} WHERE {col} IS NOT NULL AND {col} != ""'):
            try:
                val = json.loads(raw)
                for aid in val if isinstance(val, list) and (not val or val[0] != 'L') else []:
                    if aid not in attachment_ids:
                        broken.append((table, rid, col, aid))
            except Exception:
                broken.append((table, rid, col, raw))
    if broken:
        raise RuntimeError(f'Broken attachment references: {broken[:10]}')

    con.execute('VACUUM')
    con.close()

    from repair_grist_document import repair_grist_document
    repair_grist_document(DB_PATH)

    write_csv(MANIFEST_DIR / 'visual_manifest.csv', manifests)
    write_csv(MANIFEST_DIR / 'page_render_manifest.csv', page_manifest)
    summary = [
        {'item': 'visual_records_generated', 'count': len(manifests)},
        {'item': 'page_renders', 'count': len(page_manifest)},
        {'item': 'image_context_crops', 'count': len(list(IMAGE_CROP_DIR.glob('*.png')))},
        {'item': 'table_crops', 'count': len(list(TABLE_CROP_DIR.glob('*.png')))},
        {'item': 'composite_diagrams', 'count': len(list(COMPOSITE_DIR.glob('*.png')))},
        {'item': 'grist_bytes', 'count': DB_PATH.stat().st_size},
    ]
    write_csv(MANIFEST_DIR / 'summary.csv', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
