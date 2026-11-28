"""Bounded UTF-8 CSV-to-text extraction. No spreadsheet evaluation or network."""
import csv
import io
import json

MAX_FILE=1048576
MAX_TEXT=32768
MAX_ROWS=500
MAX_COLUMNS=32
MAX_CELL_BYTES=2048

class CsvError(Exception):pass


def csv_file(path,root,config):
    if config['mode']!='auto':raise CsvError('UNSUPPORTED_EXTRACTION_MODE')
    with path.open('rb') as stream:raw=stream.read(MAX_FILE+1)
    if not 1<=len(raw)<=MAX_FILE:raise CsvError('FILE_SIZE_LIMIT')
    try:text=raw.decode('utf-8-sig')
    except UnicodeError:raise CsvError('CSV_TEXT_ENCODING') from None
    if any((ord(char)<32 and char not in '\r\n\t') or ord(char)==127 for char in text):raise CsvError('CSV_TEXT_ENCODING')
    rows=[];columns=None;size=0;visible=False
    try:
        reader=csv.reader(io.StringIO(text,newline=''),delimiter=',',quotechar='"',doublequote=True,strict=True)
        for cells in reader:
            if not cells:continue
            if len(rows)>=MAX_ROWS:raise CsvError('CSV_ROW_LIMIT')
            if not 1<=len(cells)<=MAX_COLUMNS:raise CsvError('CSV_COLUMN_LIMIT')
            if columns is None:columns=len(cells)
            if len(cells)!=columns:raise CsvError('CSV_COLUMN_MISMATCH')
            if any(len(cell.encode('utf-8'))>MAX_CELL_BYTES for cell in cells):raise CsvError('CSV_CELL_LIMIT')
            visible=visible or any(cell.strip() for cell in cells)
            line='Row '+str(len(rows)+1)+': '+json.dumps(cells,ensure_ascii=False,separators=(',',':'))
            size+=len(line.encode('utf-8'))+(1 if rows else 0)
            if size>MAX_TEXT:raise CsvError('EXTRACTED_TEXT_LIMIT')
            rows.append(line)
    except csv.Error:raise CsvError('CSV_MALFORMED') from None
    if not rows or not visible:raise CsvError('NO_EXTRACTABLE_TEXT')
    return '\n'.join(rows),{'method':'csv-text','pages':None,'ocr_pages':0,'review_required':True,'extraction_mode':'auto','csv_rows':len(rows),'csv_columns':columns}
