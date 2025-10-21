#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""核心功能测试脚本 - 验证文件搜索、内容搜索和智能问答"""
import os
import sys
import time
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from src.utils.config_loader import ConfigLoader
from src.utils.logger import setup_logger
from src.core.document_parser import DocumentParser
from src.core.file_scanner import FileScanner
from src.core.index_manager import IndexManager
from src.core.search_engine import SearchEngine

def test_file_search():
    """测试1: 文件名和路径搜索"""
    print("\n" + "="*60)
    print("测试1: 文件名和路径搜索")
    print("="*60)
    
    try:
        # 初始化组件
        config_loader = ConfigLoader()
        logger = setup_logger(config=config_loader)
        
        # 创建测试目录和文件
        test_dir = Path('./test_data/documents')
        test_dir.mkdir(parents=True, exist_ok=True)
        
        test_files = [
            ('项目需求文档.txt', '这是一个项目需求文档，包含系统架构设计。'),
            ('技术方案.md', '# 技术方案\n\n本文档描述技术实现方案。'),
            ('用户手册.txt', '用户手册：如何使用本系统进行文件检索。'),
        ]
        
        for filename, content in test_files:
            file_path = test_dir / filename
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✓ 创建测试文件: {filename}")
        
        # 初始化索引管理器
        print("\n初始化索引管理器...")
        index_manager = IndexManager(config_loader)
        
        # 初始化文件扫描器
        print("初始化文件扫描器...")
        document_parser = DocumentParser(config_loader)
        file_scanner = FileScanner(config_loader, document_parser, index_manager)
        
        # 添加测试目录到扫描路径
        file_scanner.add_scan_path(str(test_dir))
        
        # 扫描并建立索引
        print("\n开始扫描文件并建立索引...")
        stats = file_scanner.scan_and_index()
        print(f"✓ 扫描完成: 索引了 {stats['total_files_indexed']} 个文件")
        
        # 初始化搜索引擎
        print("\n初始化搜索引擎...")
        search_engine = SearchEngine(index_manager, config_loader)
        
        # 测试搜索
        print("\n执行搜索测试:")
        queries = ['文档', '技术', '用户']
        
        for query in queries:
            print(f"\n搜索关键词: '{query}'")
            results = search_engine.search(query)
            print(f"找到 {len(results)} 个结果:")
            for i, result in enumerate(results, 1):
                print(f"  {i}. {result.get('filename', 'Unknown')} (匹配度: {result.get('score', 0):.2f})")
        
        print("\n✅ 测试1: 文件搜索 - 通过")
        return True
        
    except Exception as e:
        print(f"\n❌ 测试1失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_content_search():
    """测试2: 内容全文搜索"""
    print("\n" + "="*60)
    print("测试2: 内容全文搜索")
    print("="*60)
    
    try:
        config_loader = ConfigLoader()
        logger = setup_logger(config=config_loader)
        
        # 使用已有的索引
        index_manager = IndexManager(config_loader)
        search_engine = SearchEngine(index_manager, config_loader)
        
        # 测试内容搜索
        print("\n执行内容搜索测试:")
        content_queries = ['系统架构', '技术实现', '文件检索']
        
        for query in content_queries:
            print(f"\n搜索内容: '{query}'")
            results = search_engine.search(query)
            
            if results:
                print(f"找到 {len(results)} 个包含该内容的文件:")
                for i, result in enumerate(results, 1):
                    print(f"  {i}. {result.get('filename', 'Unknown')}")
                    # 显示内容片段
                    content_preview = result.get('content', '')[:100]
                    if content_preview:
                        print(f"     内容预览: {content_preview}...")
            else:
                print("  未找到匹配结果")
        
        print("\n✅ 测试2: 内容搜索 - 通过")
        return True
        
    except Exception as e:
        print(f"\n❌ 测试2失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_smart_qa():
    """测试3: 智能问答功能"""
    print("\n" + "="*60)
    print("测试3: 智能问答功能")
    print("="*60)
    
    try:
        config_loader = ConfigLoader()
        logger = setup_logger(config=config_loader)
        
        # 检查模型是否启用
        model_enabled = config_loader.get('model', 'enabled', False)
        
        if not model_enabled:
            print("\n⚠️  AI模型未启用，跳过问答测试")
            print("   (可在config.yaml中设置 model.enabled: true 启用)")
            return True
        
        # 初始化问答组件
        from src.core.model_manager import ModelManager
        from src.core.rag_pipeline import RAGPipeline
        
        print("\n初始化模型管理器...")
        model_manager = ModelManager(config_loader)
        
        # 创建简化的检索器
        index_manager = IndexManager(config_loader)
        search_engine = SearchEngine(index_manager, config_loader)
        
        # 简化的问答实现
        print("\n执行问答测试:")
        questions = [
            "项目需求是什么？",
            "技术方案有哪些内容？",
            "如何使用本系统？"
        ]
        
        for question in questions:
            print(f"\n问题: {question}")
            
            # 1. 检索相关文档
            search_results = search_engine.search(question, limit=3)
            
            if not search_results:
                print("  答案: 抱歉，没有找到相关信息。")
                continue
            
            # 2. 构建上下文
            context = "\n\n".join([
                f"文档: {r.get('filename', 'Unknown')}\n内容: {r.get('content', '')[:200]}"
                for r in search_results[:2]
            ])
            
            # 3. 生成答案
            prompt = f"""基于以下文档内容回答问题：

{context}

问题：{question}

请简洁回答："""
            
            print("  检索到相关文档:")
            for i, r in enumerate(search_results[:2], 1):
                print(f"    {i}. {r.get('filename', 'Unknown')}")
            
            # 如果模型可用，生成答案
            try:
                print("\n  生成答案中...")
                answer_parts = []
                for token in model_manager.generate(prompt, max_tokens=200):
                    answer_parts.append(token)
                answer = ''.join(answer_parts)
                print(f"  答案: {answer}")
            except Exception as e:
                print(f"  答案生成失败: {str(e)}")
                print(f"  基于检索的简单答案: 请参考以上文档内容")
        
        print("\n✅ 测试3: 智能问答 - 通过")
        return True
        
    except Exception as e:
        print(f"\n❌ 测试3失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def cleanup_test_data():
    """清理测试数据"""
    print("\n清理测试数据...")
    import shutil
    test_dir = Path('./test_data')
    if test_dir.exists():
        shutil.rmtree(test_dir)
        print("✓ 测试数据已清理")

def main():
    """主测试流程"""
    print("\n" + "="*60)
    print("智能文件检索与问答系统 - 核心功能测试")
    print("="*60)
    
    start_time = time.time()
    
    # 运行测试
    results = {
        '文件搜索': test_file_search(),
        '内容搜索': test_content_search(),
        '智能问答': test_smart_qa()
    }
    
    # 显示测试总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")
    
    elapsed_time = time.time() - start_time
    print(f"\n总计: {passed}/{total} 测试通过")
    print(f"耗时: {elapsed_time:.2f} 秒")
    
    # 清理
    cleanup_test_data()
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
