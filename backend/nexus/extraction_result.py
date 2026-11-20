"""Normalize the extraction process protocol before persisting its output."""
ERROR_CODES=frozenset({
    'FILE_SIZE_LIMIT','PDF_PAGE_LIMIT','EXTRACTED_TEXT_LIMIT','OCR_REQUIRED','OCR_DISABLED',
    'OCR_LANGUAGE_UNAVAILABLE','OCR_ENGINE_UNAVAILABLE','OCR_TIMEOUT','OCR_ENGINE_FAILED','IMAGE_LIMIT',
    'DOCX_CONTAINER_REJECTED','DOCX_CONTAINER_LIMIT','DOCX_XML_REJECTED','UNSUPPORTED_EXTRACTION_MODE',
    'NO_EXTRACTABLE_TEXT','UNSUPPORTED_OR_MALFORMED_FILE','EXTRACTION_TIMEOUT',
    'EXTRACTOR_RESOURCE_OR_PROCESS_FAILURE','EXTRACTOR_RESULT_INVALID','REQUESTER_REVOKED','EXTRACTION_UNAVAILABLE',
})
INFO_FIELDS=frozenset({'method','pages','ocr_pages','review_required','extraction_mode'})


def normalize_result(value):
    """Return a bounded success or a fixed failure code, without raw error details."""
    invalid={'error_code':'EXTRACTOR_RESULT_INVALID'}
    if type(value) is not dict or not set(value).issubset({'text','info','error_code'}):return invalid
    error=value.get('error_code')
    if error is not None:
        if type(error) is not str or (error and error not in ERROR_CODES):return invalid
        if error:return {'error_code':error}  # Never save text/metadata accompanying failure.
    if 'text' not in value or type(value['text']) is not str:return invalid
    text=value['text'];info=value.get('info',{})
    if type(info) is not dict or not set(info).issubset(INFO_FIELDS):return invalid
    try:
        if '\x00' in text or len(text.encode('utf-8'))>32768:return invalid
        if 'method' in info:
            method=info['method']
            if type(method) is not str or not method.strip() or len(method)>64 or any(ord(char)<32 or ord(char)==127 for char in method):return invalid
            method.encode('utf-8')
        if 'pages' in info and info['pages'] is not None and (type(info['pages']) is not int or not 1<=info['pages']<=12):return invalid
        if 'ocr_pages' in info:
            pages=info['ocr_pages']
            if type(pages) is not int or not 0<=pages<=12:return invalid
            if info.get('pages') is not None and pages>info['pages']:return invalid
        if 'review_required' in info and info['review_required'] is not True:return invalid
        if 'extraction_mode' in info and (type(info['extraction_mode']) is not str or info['extraction_mode'] not in ('auto','ocr')):return invalid
    except (TypeError,ValueError,UnicodeError):return invalid
    return {'text':text,'info':dict(info)}
