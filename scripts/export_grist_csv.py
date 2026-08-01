from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / '01_database' / '안심주택DB.grist'
OUT = ROOT / '05_exports'
OUT.mkdir(parents=True, exist_ok=True)

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()
if cur.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
    raise RuntimeError('Grist SQLite integrity check failed')

attachments = {r['id']: r['fileName'] for r in cur.execute('SELECT id,fileName FROM _grist_Attachments')}

def parse_list(v):
    if v in (None, '', 0): return []
    if isinstance(v, str):
        try: v = json.loads(v)
        except Exception: return [v]
    if isinstance(v, (list, tuple)) and v and v[0] == 'L': return list(v[1:])
    return list(v) if isinstance(v, (list, tuple)) else [v]

def attachment_names(v):
    return ';'.join(attachments.get(int(x), str(x)) for x in parse_list(v) if x not in (None, '', 0))

def iso_date(v):
    if v in (None, '', 0): return ''
    try: return datetime.fromtimestamp(float(v), timezone.utc).date().isoformat()
    except Exception: return str(v)

def b(v):
    if v in (None, ''): return ''
    return 'TRUE' if bool(v) else 'FALSE'

def write(name, rows, headers=None):
    path = OUT / name
    rows = list(rows)
    if headers is None:
        headers = list(rows[0].keys()) if rows else []
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
        w.writeheader(); w.writerows(rows)
    return {'file': name, 'rows': len(rows), 'bytes': path.stat().st_size}

D = {r['id']: r['DocumentCode'] for r in cur.execute('SELECT id,DocumentCode FROM Documents')}
C = {r['id']: r['ClauseID'] for r in cur.execute('SELECT id,ClauseID FROM Clauses')}
T = {r['id']: r['TableID'] for r in cur.execute('SELECT id,TableID FROM ExtractedTables')}
V = {r['id']: r['VisualID'] for r in cur.execute('SELECT id,VisualID FROM Visuals')}
R = {r['id']: r['RuleID'] for r in cur.execute('SELECT id,RuleID FROM Rules')}

def ref(v, lookup):
    if v in (None, '', 0): return ''
    try: return lookup.get(int(v), str(v))
    except Exception: return str(v)

def reflist(v, lookup): return ';'.join(ref(x, lookup) for x in parse_list(v))

manifest=[]
manifest.append(write('00_guide.csv', ({'order_no':r['OrderNo'],'topic':r['Topic'],'content':r['Content']} for r in cur.execute('SELECT * FROM Guide ORDER BY OrderNo,id'))))
manifest.append(write('documents.csv', ({
    'document_id':r['DocumentCode'],'title':r['Title'],'document_type':r['DocumentType'],'page_count':r['PageCount'],
    'enacted_date':iso_date(r['EnactedDate']),'amended_date':iso_date(r['AmendedDate']),'effective_date':iso_date(r['EffectiveDate']),
    'ordinance_no':r['OrdinanceNo'],'source_pdf_file':attachment_names(r['SourcePDF']),'pdf_path':r['PDFPath'],'json_path':r['JSONPath'],
    'markdown_path':r['MarkdownPath'],'pdf_created_date':iso_date(r['PDFCreatedDate']),'pdf_modified_date':iso_date(r['PDFModifiedDate']),
    'related_document_ids':reflist(r['RelatedDocuments'],D),'status':r['Status'],'review_status':r['ReviewStatus'],'notes':r['Notes']
} for r in cur.execute('SELECT * FROM Documents ORDER BY manualSort,id'))))
manifest.append(write('clauses.csv', ({
    'clause_id':r['ClauseID'],'document_id':ref(r['Document'],D),'parent_clause_id':ref(r['ParentClause'],C),'chapter':r['Chapter'],
    'section':r['Section'],'clause_number':r['ClauseNumber'],'clause_title':r['ClauseTitle'],'start_page':r['StartPage'],'end_page':r['EndPage'],
    'raw_text':r['RawText'],'normalized_text':r['NormalizedText'],'summary':r['Summary'],'content_type':r['ContentType'],
    'source_element_ids':r['SourceElementIDs'],'review_status':r['ReviewStatus'],'review_memo':r['ReviewMemo']
} for r in cur.execute('SELECT * FROM Clauses ORDER BY manualSort,id'))))
manifest.append(write('visuals.csv', ({
    'visual_id':r['VisualID'],'document_id':ref(r['Document'],D),'clause_id':ref(r['Clause'],C),'page':r['Page'],'visual_type':r['VisualType'],
    'image_file':attachment_names(r['Image']),'source_path':r['SourcePath'],'source_key':r['SourceKey'],'related_table_id':ref(r['RelatedTable'],T),
    'bbox_left':r['BBoxLeft'],'bbox_bottom':r['BBoxBottom'],'bbox_right':r['BBoxRight'],'bbox_top':r['BBoxTop'],
    'pixel_width':r['PixelWidth'],'pixel_height':r['PixelHeight'],'ocr_text':r['OCRText'],'description':r['Description'],
    'context_text':r['ContextText'],'sha256':r['SHA256'],'duplicate_group':r['DuplicateGroup'],'is_primary':b(r['IsPrimary']),
    'review_status':r['ReviewStatus'],'review_memo':r['ReviewMemo']
} for r in cur.execute('SELECT * FROM Visuals ORDER BY manualSort,id'))))
manifest.append(write('extracted_tables.csv', ({
    'table_id':r['TableID'],'document_id':ref(r['Document'],D),'clause_id':ref(r['Clause'],C),'start_page':r['StartPage'],'end_page':r['EndPage'],
    'title':r['Title'],'row_count':r['RowCount'],'column_count':r['ColumnCount'],'table_text':r['TableText'],'table_html':r['TableHTML'],
    'rows_json':r['RowsJSON'],'table_image_file':attachment_names(r['TableImage']),'bbox_left':r['BBoxLeft'],'bbox_bottom':r['BBoxBottom'],
    'bbox_right':r['BBoxRight'],'bbox_top':r['BBoxTop'],'review_status':r['ReviewStatus'],'review_memo':r['ReviewMemo']
} for r in cur.execute('SELECT * FROM ExtractedTables ORDER BY manualSort,id'))))
rule_headers=['rule_id','clause_id','rule_name','rule_type','subject','condition_field','operator','numeric_value','text_value','unit','result','exception','source_quote','review_status','review_memo']
manifest.append(write('rules.csv', ({
    'rule_id':r['RuleID'],'clause_id':ref(r['Clause'],C),'rule_name':r['RuleName'],'rule_type':r['RuleType'],'subject':r['Subject'],
    'condition_field':r['ConditionField'],'operator':r['Operator'],'numeric_value':r['NumericValue'],'text_value':r['TextValue'],'unit':r['Unit'],
    'result':r['Result'],'exception':r['Exception'],'source_quote':r['SourceQuote'],'review_status':r['ReviewStatus'],'review_memo':r['ReviewMemo']
} for r in cur.execute('SELECT * FROM Rules ORDER BY manualSort,id')), rule_headers))
case_headers=['case_id','rule_id','visual_id','case_name','conditions','decision','decision_basis','case_image_file','review_status','review_memo']
manifest.append(write('cases.csv', ({
    'case_id':r['CaseID'],'rule_id':ref(r['Rule'],R),'visual_id':ref(r['Visual'],V),'case_name':r['CaseName'],'conditions':r['Conditions'],
    'decision':r['Decision'],'decision_basis':r['DecisionBasis'],'case_image_file':attachment_names(r['CaseImage']),
    'review_status':r['ReviewStatus'],'review_memo':r['ReviewMemo']
} for r in cur.execute('SELECT * FROM Cases ORDER BY manualSort,id')), case_headers))
manifest.append(write('source_elements.csv', ({
    'element_id':r['ElementID'],'document_id':ref(r['Document'],D),'clause_id':ref(r['Clause'],C),'source_id':r['SourceID'],'order_no':r['OrderNo'],
    'element_type':r['ElementType'],'page':r['Page'],'bbox_left':r['BBoxLeft'],'bbox_bottom':r['BBoxBottom'],'bbox_right':r['BBoxRight'],
    'bbox_top':r['BBoxTop'],'content':r['Content'],'source_image':r['SourceImage'],'raw_json':r['RawJSON'],'use_for_db':b(r['UseForDB'])
} for r in cur.execute('SELECT * FROM SourceElements ORDER BY manualSort,id'))))
write('manifest.csv', manifest, ['file','rows','bytes'])
con.close()
print(json.dumps(manifest, ensure_ascii=False, indent=2))
