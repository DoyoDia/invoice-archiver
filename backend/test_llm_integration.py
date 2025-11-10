"""
测试 LLM 解析流程
用法: python test_llm_integration.py <pdf文件路径>
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from app.config import load_settings
from app.llm_service import LLMService


async def test_llm_parse(pdf_path: str):
    """测试 LLM 解析单个 PDF"""
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"❌ 文件不存在: {pdf_path}")
        return
    
    print(f"📄 测试文件: {pdf_file.name}")
    print("="*80)
    
    # 加载配置
    settings = load_settings()
    print(f"🔧 LLM 配置:")
    print(f"  Base URL: {settings.llm_base_url}")
    print(f"  Model: {settings.llm_model}")
    print(f"  Enabled: {settings.llm_enabled}")
    print()
    
    if not settings.llm_enabled:
        print("❌ LLM 未启用，请设置 LLM_ENABLED=true")
        return
    
    # 创建服务
    service = LLMService.from_settings(settings)
    
    try:
        print("🚀 开始解析...")
        result = await service.parse_invoice(pdf_file)
        
        print("\n✅ 解析成功!")
        print(f"\n使用方法: {'直接提取' if result.fallback_used == 'direct' else 'OCR' if result.fallback_used == 'ocr' else '未知'}")
        
        print(f"\n--- Markdown 源文本（前500字符）---")
        print(result.source_markdown[:500])
        print("...\n")
        
        print("--- 解析结果 ---")
        data = result.data
        print(f"发票类型: {data.get('发票类型')}")
        print(f"发票号码: {data.get('发票号码')}")
        print(f"开票日期: {data.get('开票日期')}")
        
        buyer = data.get('购买方信息', {})
        print(f"购买方: {buyer.get('名称')} (税号: {buyer.get('纳税人识别号')})")
        
        seller = data.get('销售方信息', {})
        print(f"销售方: {seller.get('名称')} (税号: {seller.get('纳税人识别号')})")
        
        items = data.get('项目', [])
        print(f"\n项目数量: {len(items)}")
        for i, item in enumerate(items, 1):
            print(f"  项目{i}: {item.get('项目名称')} | {item.get('规格型号')}")
            print(f"    数量: {item.get('数量')} {item.get('单位')} | 单价: {item.get('单价')}")
            print(f"    金额: {item.get('金额')} | 税率: {item.get('税率')} | 税额: {item.get('税额')}")
        
        totals = data.get('合计', {})
        print(f"\n合计: 金额 {totals.get('金额')} | 税额 {totals.get('税额')}")
        
        grand = data.get('价税合计', {})
        print(f"价税合计: {grand.get('大写')} ({grand.get('小写')})")
        
        print(f"\n备注: {data.get('备注')}")
        print(f"开票人: {data.get('开票人')}")
        
        # 检查关键字段
        print("\n--- 字段完整性检查 ---")
        has_invoice_no = data.get('发票号码') is not None
        has_items = len(items) > 0
        all_items_valid = all(
            item.get('项目名称') is not None 
            for item in items
        )
        
        print(f"✓ 发票号码: {'有' if has_invoice_no else '❌ 缺失'}")
        print(f"✓ 项目数量: {len(items)}")
        print(f"✓ 项目名称完整: {'是' if all_items_valid else '❌ 否'}")
        
        if not has_invoice_no and not (has_items and all_items_valid):
            print("\n⚠️  解析质量不足（缺少发票号码且项目信息不完整）")
        
    except Exception as e:
        print(f"\n❌ 解析失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await service.aclose()
        print("\n🔚 测试完成")


async def main():
    # if len(sys.argv) < 2:
    #     print("用法: python test_llm_integration.py <pdf文件路径>")
    #     print("示例: python test_llm_integration.py data/invoices-test/2_*.pdf")
    #     return
    
    pdf_path = r"..\data\invoices-test\1_dzfp_25312000000190830857_上海杉达学院_20250620141647(1).pdf"
    await test_llm_parse(pdf_path)


if __name__ == "__main__":
    asyncio.run(main())
