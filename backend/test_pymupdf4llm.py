import pymupdf4llm
from pathlib import Path

pdf_path = r'data/invoices-test/2_25952000000181354038_深圳市亚博智能科技有限公司_20250901163647.pdf'

if not Path(pdf_path).exists():
    print(f'❌ 文件不存在: {pdf_path}')
else:
    md_text = pymupdf4llm.to_markdown(pdf_path)
    print(md_text)
    print('\n=== 总长度:', len(md_text))