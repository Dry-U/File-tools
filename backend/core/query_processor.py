#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""查询预处理模块 - 扩展查询、同义词、缩写展开"""
import re
from typing import List, Dict, Set
import logging

logger = logging.getLogger(__name__)


class QueryProcessor:
    """查询预处理器 - 扩展查询、同义词、纠错"""

    # 常见缩写映射表
    ABBREVIATIONS = {
        # 技术和协议
        'rcp': ['remote control protocol', '远程控制协议', 'rich client platform'],
        'api': ['application programming interface', '应用程序接口', '应用编程接口'],
        'sdk': ['software development kit', '软件开发工具包'],
        'ui': ['user interface', '用户界面'],
        'ux': ['user experience', '用户体验'],
        'db': ['database', '数据库'],
        'sql': ['structured query language', '结构化查询语言'],
        'http': ['hypertext transfer protocol', '超文本传输协议'],
        'https': ['hypertext transfer protocol secure', '安全超文本传输协议'],
        'url': ['uniform resource locator', '统一资源定位符'],
        'json': ['javascript object notation'],
        'xml': ['extensible markup language', '可扩展标记语言'],
        'html': ['hypertext markup language', '超文本标记语言'],
        'css': ['cascading style sheets', '层叠样式表'],
        'pdf': ['portable document format', '便携式文档格式'],

        # 组织和标准
        'ieee': ['institute of electrical and electronics engineers', '电气电子工程师学会'],
        'iso': ['international organization for standardization', '国际标准化组织'],
        'ieee': ['institute of electrical and electronics engineers'],

        # 通用缩写
        'doc': ['document', '文档'],
        'docs': ['documents', '文档'],
        'info': ['information', '信息'],
        'config': ['configuration', '配置'],
        'conf': ['configuration', '会议', '配置'],
        'lib': ['library', '库'],
        'pkg': ['package', '包'],
        'src': ['source', '源代码'],
        'tmp': ['temporary', '临时'],
        'temp': ['temporary', '临时'],
        'img': ['image', '图像'],
        'pic': ['picture', '图片'],
        'ref': ['reference', '参考文献', '参考'],
        'intro': ['introduction', '简介', '引言'],
        'abs': ['abstract', '摘要'],
        'sum': ['summary', '总结'],
        'concl': ['conclusion', '结论'],
        'ack': ['acknowledgment', '致谢'],
        'bib': ['bibliography', '参考文献'],
        'app': ['appendix', '附录', 'application', '应用'],
        'fig': ['figure', '图'],
        'tab': ['table', '表'],
        'eq': ['equation', '公式'],
        'sec': ['section', '节', '章节'],
        'ch': ['chapter', '章'],
        'vol': ['volume', '卷'],
        'no': ['number', '编号'],
        'id': ['identifier', '标识符'],
        'idx': ['index', '索引'],
        'toc': ['table of contents', '目录'],
        'lof': ['list of figures', '图目录'],
        'lot': ['list of tables', '表目录'],

        # 学术相关
        'phd': ['doctor of philosophy', '博士'],
        'ms': ['master of science', '硕士'],
        'bs': ['bachelor of science', '学士'],
        'prof': ['professor', '教授'],
        'dr': ['doctor', '博士'],
        'et al': ['et alii', '等人'],
        'i.e': ['id est', '即'],
        'e.g': ['exempli gratia', '例如'],
        'etc': ['et cetera', '等等'],
        'cf': ['confer', '参见'],
        'vs': ['versus', '对比'],
        'wrt': ['with respect to', '关于'],
    }

    # 常见同义词映射
    SYNONYMS = {
        '说明': ['文档', '指南', '手册', '介绍', '简介', 'readme', 'guide', 'manual'],
        '文档': ['说明', '指南', '手册', '介绍', 'doc', 'document'],
        '指南': ['说明', '文档', '手册', 'guide', 'tutorial'],
        '手册': ['说明', '文档', '指南', 'manual', 'handbook'],
        '介绍': ['说明', '简介', '引言', 'introduction'],
        '简介': ['介绍', '概述', 'summary', 'overview'],
        '总结': ['概要', '概述', '结论', 'summary'],
        '报告': ['文档', '论文', 'report', 'paper'],
        '论文': ['报告', '文章', 'paper', 'article'],
        '代码': ['程序', '源码', '源代码', 'code', 'source'],
        '程序': ['代码', '应用', '软件', 'program', 'application'],
        '软件': ['程序', '应用', 'software', 'application'],
        '应用': ['程序', '软件', 'application', 'app'],
        '系统': ['平台', '框架', 'system', 'platform'],
        '平台': ['系统', '框架', 'platform', 'framework'],
        '框架': ['库', '平台', 'framework', 'library'],
        '库': ['框架', '包', 'library', 'package'],
        '包': ['库', '模块', 'package', 'module'],
        '模块': ['组件', '包', 'module', 'component'],
        '组件': ['模块', '部件', 'component', 'module'],
        '接口': ['api', '界面', 'interface'],
        '界面': ['接口', 'ui', 'interface'],
        '数据库': ['db', '数据存储', 'database'],
        '配置': ['设置', '选项', 'configuration', 'settings'],
        '设置': ['配置', '选项', 'settings', 'preferences'],
        '选项': ['设置', '配置', 'options', 'settings'],
        '功能': ['特性', '特点', 'feature', 'functionality'],
        '特性': ['功能', '特点', 'feature', 'characteristic'],
        '方法': ['方式', '手段', 'method', 'approach'],
        '算法': ['方法', '策略', 'algorithm'],
        '策略': ['方法', '方案', 'strategy', 'policy'],
        '方案': ['策略', '计划', 'solution', 'plan'],
        '解决方案': ['方案', '解决办法', 'solution'],
        '问题': ['疑问', '难题', 'question', 'problem', 'issue'],
        '错误': ['问题', '异常', 'error', 'bug'],
        '异常': ['错误', '问题', 'exception', 'error'],
        'bug': ['错误', '缺陷', '漏洞'],
        '缺陷': ['bug', '问题', 'defect'],
        '漏洞': ['bug', '安全问题', 'vulnerability'],
        '安全': ['防护', '保护', 'security', 'safety'],
        '性能': ['效率', '速度', 'performance'],
        '优化': ['改进', '提升', 'optimization'],
        '测试': ['检验', '验证', 'test', 'testing'],
        '验证': ['测试', '确认', 'verification', 'validation'],
        '部署': ['发布', '上线', 'deployment'],
        '发布': ['部署', '发行', 'release'],
        '版本': ['版', 'release', 'version'],
        '更新': ['升级', '改进', 'update', 'upgrade'],
        '升级': ['更新', '提升', 'upgrade'],
        '安装': ['配置', '部署', 'install', 'setup'],
        '卸载': ['删除', '移除', 'uninstall'],
        '删除': ['移除', '卸载', 'delete', 'remove'],
        '添加': ['增加', '插入', 'add', 'insert'],
        '修改': ['更改', '编辑', '修改', 'edit', 'modify'],
        '编辑': ['修改', '更改', 'edit'],
        '创建': ['新建', '生成', 'create', 'generate'],
        '新建': ['创建', '建立', 'new', 'create'],
        '生成': ['创建', '产生', 'generate', 'produce'],
        '导入': ['引入', '加载', 'import', 'load'],
        '导出': ['输出', '保存', 'export', 'save'],
        '保存': ['存储', '导出', 'save', 'store'],
        '加载': ['导入', '读取', 'load', 'read'],
        '读取': ['加载', '获取', 'read', 'fetch'],
        '写入': ['保存', '存储', 'write', 'save'],
        '搜索': ['查找', '检索', 'search', 'find'],
        '查找': ['搜索', '寻找', 'find', 'search'],
        '检索': ['搜索', '查询', 'retrieve', 'search'],
        '查询': ['检索', '搜索', 'query', 'search'],
        '过滤': ['筛选', '过滤', 'filter'],
        '排序': ['排列', '排序', 'sort', 'order'],
        '分组': ['分类', '聚合', 'group'],
        '分类': ['分组', '类别', 'category', 'classify'],
        '统计': ['计算', '分析', 'statistics', 'count'],
        '分析': ['统计', '研究', 'analysis', 'analyze'],
        '显示': ['展示', '呈现', 'display', 'show'],
        '隐藏': [' conceal', '隐藏', 'hide'],
        '展开': ['扩展', '展开', 'expand'],
        '折叠': ['收起', '压缩', 'collapse'],
        '启用': ['激活', '开启', 'enable', 'activate'],
        '禁用': ['关闭', '停用', 'disable', 'deactivate'],
    }

    # 文件名变体模式
    FILENAME_VARIANTS = [
        '{query}说明',
        '{query}文档',
        '{query}指南',
        '{query}手册',
        '{query}介绍',
        '{query}简介',
        '{query}总结',
        '{query}报告',
        '{query}论文',
        '{query}笔记',
        '{query}记录',
        '{query}备忘',
        '{query}清单',
        '{query}目录',
        '{query}索引',
        '{query}参考',
        '{query}资料',
        '{query}素材',
        '{query}示例',
        '{query}案例',
        '{query}模板',
        '{query}规范',
        '{query}标准',
        '{query}流程',
        '{query}步骤',
        '{query}教程',
        '{query}学习',
        '{query}研究',
        '{query}实验',
        '{query}测试',
        '{query}结果',
        '{query}分析',
        '{query}评估',
        '{query}评价',
        '{query}建议',
        '{query}方案',
        '{query}计划',
        '{query}设计',
        '{query}实现',
        '{query}开发',
        '{query}部署',
        '{query}维护',
        '{query}管理',
        '{query}操作',
        '{query}使用',
        '{query}配置',
        '{query}安装',
        '{query}卸载',
        '{query}更新',
        '{query}升级',
        '{query}修复',
        '{query}优化',
        '{query}改进',
        '{query}增强',
        '{query}扩展',
        '{query}定制',
        '{query}个性化',
    ]

    def __init__(self, config_loader=None):
        self.config_loader = config_loader
        self.logger = logging.getLogger(__name__)

    def process(self, query: str) -> List[str]:
        """
        处理查询，返回扩展后的查询列表

        策略：
        1. 原始查询
        2. 缩写展开
        3. 同义词扩展
        4. 文件名变体
        5. 中英文混合查询
        """
        if not query or not query.strip():
            return []

        query = query.strip()
        queries = [query]  # 原始查询

        # 缩写展开
        expanded = self._expand_abbreviations(query)
        queries.extend(expanded)

        # 同义词扩展
        synonyms = self._expand_synonyms(query)
        queries.extend(synonyms)

        # 文件名变体
        filename_variants = self._generate_filename_variants(query)
        queries.extend(filename_variants)

        # 清理和去重
        queries = self._clean_and_deduplicate(queries)

        self.logger.debug(f"查询扩展: '{query}' -> {queries}")
        return queries

    def _expand_abbreviations(self, query: str) -> List[str]:
        """展开常见缩写"""
        expanded = []
        query_lower = query.lower()

        # 检查整个查询是否是缩写
        if query_lower in self.ABBREVIATIONS:
            expanded.extend(self.ABBREVIATIONS[query_lower])

        # 检查查询中的每个词是否是缩写
        words = re.findall(r'\b\w+\b', query_lower)
        for word in words:
            if word in self.ABBREVIATIONS:
                expanded.extend(self.ABBREVIATIONS[word])

        return expanded

    def _expand_synonyms(self, query: str) -> List[str]:
        """扩展同义词"""
        expanded = []
        query_lower = query.lower()

        # 检查查询中的每个词是否有同义词
        for key, synonyms in self.SYNONYMS.items():
            if key in query_lower:
                # 为每个同义词创建一个变体查询
                for synonym in synonyms:
                    variant = query_lower.replace(key, synonym)
                    if variant != query_lower:
                        expanded.append(variant)

        return expanded

    def _generate_filename_variants(self, query: str) -> List[str]:
        """生成文件名匹配变体"""
        variants = []

        # 清理查询，去除常见停用词
        cleaned_query = self._clean_query_for_filename(query)
        if not cleaned_query:
            return variants

        # 生成文件名变体
        for pattern in self.FILENAME_VARIANTS:
            variant = pattern.format(query=cleaned_query)
            variants.append(variant)

        return variants

    def _clean_query_for_filename(self, query: str) -> str:
        """清理查询，去除停用词，适合用于文件名匹配"""
        # 常见停用词
        stopwords = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人',
                     '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去',
                     '你', '会', '着', '没有', '看', '好', '自己', '这', '那',
                     '什么', '怎么', '为什么', '哪里', '谁', '多少', '几',
                     'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                     'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                     'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                     'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
                     'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
                     'through', 'during', 'before', 'after', 'above', 'below',
                     'between', 'under', 'and', 'but', 'or', 'yet', 'so'}

        words = re.findall(r'\b\w+\b', query.lower())
        cleaned_words = [w for w in words if w not in stopwords and len(w) > 1]

        return ' '.join(cleaned_words) if cleaned_words else query

    def _clean_and_deduplicate(self, queries: List[str]) -> List[str]:
        """清理查询列表并去重"""
        seen = set()
        result = []

        for query in queries:
            # 标准化：去除多余空格，转为小写用于比较
            normalized = ' '.join(query.split()).lower()

            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(query.strip())

        return result

    def extract_keywords(self, query: str) -> List[str]:
        """从查询中提取关键词"""
        if not query:
            return []

        # 分词
        words = re.findall(r'\b\w+\b', query.lower())

        # 过滤停用词和短词
        stopwords = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人',
                     '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去',
                     '你', '会', '着', '没有', '看', '好', '自己', '这', '那',
                     'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                     'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would'}

        keywords = [w for w in words if w not in stopwords and len(w) > 1]

        return keywords

    def is_likely_filename_query(self, query: str) -> bool:
        """判断查询是否可能是针对文件名的搜索"""
        if not query:
            return False

        # 如果查询包含文件扩展名，很可能是文件名搜索
        if re.search(r'\.\w{2,5}$', query.lower()):
            return True

        # 如果查询很短（1-3个词），可能是文件名搜索
        words = query.split()
        if len(words) <= 3:
            return True

        # 如果查询包含特定文件名关键词
        filename_indicators = ['文件', '文档', 'doc', 'file', 'pdf', 'word',
                               'excel', 'ppt', 'txt', 'md', '文件名']
        query_lower = query.lower()
        for indicator in filename_indicators:
            if indicator in query_lower:
                return True

        return False
