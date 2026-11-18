"""One-file bounded text extraction process; never runs in the API process.
No network client or application credentials are loaded. This is resource
containment, not a full operating-system security sandbox.
"""
from contextlib import closing
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import warnings
import zipfile
import xml.etree.ElementTree as ET

MAX_TEXT=32768
MAX_PIXELS=8000000
class ExtractError(Exception): pass

def bounded(text):
    text=text.replace('\x00','').strip()
    if len(text.encode('utf-8'))>MAX_TEXT:raise ExtractError('EXTRACTED_TEXT_LIMIT')
    return text

def ocr(image_path,root,config):
    if not config['ocr_enabled']:raise ExtractError('OCR_DISABLED')
    lang={'English':'eng','Arabic':'ara','Bilingual':'eng+ara'}[config['language']]
    if not set(lang.split('+')).issubset(set(config['ocr_languages'].split('+'))):raise ExtractError('OCR_LANGUAGE_UNAVAILABLE')
    try:
        result=subprocess.run([config['tesseract'],str(image_path),str(root/'ocr'),'-l',lang,'--psm','3','quiet'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20,check=False)
    except FileNotFoundError:raise ExtractError('OCR_ENGINE_UNAVAILABLE') from None
    except subprocess.TimeoutExpired:raise ExtractError('OCR_TIMEOUT') from None
    if result.returncode:raise ExtractError('OCR_ENGINE_FAILED')
    output=root/'ocr.txt'
    if not output.exists() or output.stat().st_size>MAX_TEXT:raise ExtractError('EXTRACTED_TEXT_LIMIT')
    return bounded(output.read_text(encoding='utf-8'))

def image_file(path,root,config):
    from PIL import Image,ImageOps
    Image.MAX_IMAGE_PIXELS=MAX_PIXELS
    warnings.simplefilter('error',Image.DecompressionBombWarning)
    with Image.open(path) as image:
        if image.format not in ('PNG','JPEG') or image.width*image.height>MAX_PIXELS:raise ExtractError('IMAGE_LIMIT')
        image.load()
        normalized=ImageOps.exif_transpose(image).convert('RGB');normalized.save(root/'normalized.png');normalized.close()
    return ocr(root/'normalized.png',root,config),{'method':'image-ocr','pages':1,'ocr_pages':1,'review_required':True}

def pdf_file(path,root,config):
    import pypdfium2 as pdfium
    text=[];used=0
    with closing(pdfium.PdfDocument(str(path))) as pdf:
        if not 1<=len(pdf)<=12:raise ExtractError('PDF_PAGE_LIMIT')
        for n in range(len(pdf)):
            with closing(pdf[n]) as page:
                with closing(page.get_textpage()) as textpage:
                    if textpage.count_chars()>MAX_TEXT:raise ExtractError('EXTRACTED_TEXT_LIMIT')
                    value='' if config['mode']=='ocr' else bounded(textpage.get_text_range())
                if not value:
                    if not config['ocr_enabled']:raise ExtractError('OCR_REQUIRED')
                    w,h=page.get_size()
                    if not all(math.isfinite(x) and x>0 for x in (w,h)) or w*h*4>MAX_PIXELS:raise ExtractError('IMAGE_LIMIT')
                    with closing(page.render(scale=2)) as bitmap:
                        image=bitmap.to_pil();image.save(root/'page.png');image.close()
                    value=ocr(root/'page.png',root,config);used+=1
                text.append(value);bounded('\n\n'.join(text))
        return bounded('\n\n'.join(text)),{'method':'pdf-ocr' if used else 'pdf-text','pages':len(pdf),'ocr_pages':used,'review_required':True,'extraction_mode':config['mode']}

def docx_file(path,root,config):
    if config['mode']=='ocr':raise ExtractError('UNSUPPORTED_EXTRACTION_MODE')
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist()
        if len(entries)>200 or any(e.flag_bits&1 or e.filename.lower().endswith('vbaproject.bin') for e in entries):raise ExtractError('DOCX_CONTAINER_REJECTED')
        item=archive.getinfo('word/document.xml')
        if item.file_size>1048576 or item.file_size>100*max(1,item.compress_size):raise ExtractError('DOCX_CONTAINER_LIMIT')
        raw=archive.read(item)
        xml=raw.decode('utf-8')
        if '<!DOCTYPE' in xml.upper() or '<!ENTITY' in xml.upper():raise ExtractError('DOCX_XML_REJECTED')
        root_xml=ET.fromstring(xml);parts=[]
        for paragraph in root_xml.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
            parts.append(''.join(node.text or '' for node in paragraph.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t')))
        return bounded('\n'.join(parts)),{'method':'docx-text','pages':None,'ocr_pages':0,'review_required':True}

def main():
    # Limits apply before native PDF/image parsing. Windows needs equivalent
    # deployment memory limits; the parent enforces a process-tree wall timeout.
    if os.name=='posix':
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(1073741824,1073741824))
        resource.setrlimit(resource.RLIMIT_FSIZE,(16777216,16777216))
        resource.setrlimit(resource.RLIMIT_CPU,(25,25))
    source,config_path,output=map(Path,sys.argv[1:4]);config=json.loads(config_path.read_text());root=output.parent
    try:
        if not 1<=source.stat().st_size<=1048576:raise ExtractError('FILE_SIZE_LIMIT')
        ext=config['format']
        text,info=(pdf_file if ext=='pdf' else docx_file if ext=='docx' else image_file)(source,root,config)
        if not text:raise ExtractError('NO_EXTRACTABLE_TEXT')
        result={'text':text,'info':info}
    except ExtractError as exc:result={'error_code':str(exc)}
    except Exception:result={'error_code':'UNSUPPORTED_OR_MALFORMED_FILE'}
    output.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')

if __name__=='__main__':main()
