#!/usr/bin/env node
/**
 * Release Body 生成脚本
 * 从 CHANGELOG.md 提取内容并生成专业格式的 Release Body
 * 类似 Clash Verge 的发布格式
 */

const fs = require('fs');
const path = require('path');

const VERSION = process.env.VERSION;
const CHANGELOG_PATH = process.env.CHANGELOG_PATH || 'CHANGELOG.md';
const OUTPUT_PATH = process.env.OUTPUT_PATH || 'release-body.md';

if (!VERSION) {
  console.error('Error: VERSION not provided');
  process.exit(1);
}

const REPO_URL = 'https://github.com/Dry-U/File-tools';

function parseChangelog(content, version) {
  const sections = {
    added: [],
    changed: [],
    fixed: [],
    security: [],
    deprecated: [],
    removed: []
  };

  // 提取版本内容 - 匹配 ## [version] - date 到下一个 ## [ 或文件结束
  const versionRegex = new RegExp(`## \\[${version}\\].*?(?=## \\[|$)`, 's');
  const match = content.match(versionRegex);

  if (!match) {
    return null;
  }

  const versionContent = match[0];

  // 解析各个部分 (### Added, ### Changed, ### Fixed, etc.)
  const sectionRegex = /### (\w+)\n([\s\S]*?)(?=### |$)/g;
  let sectionMatch;

  while ((sectionMatch = sectionRegex.exec(versionContent)) !== null) {
    const sectionName = sectionMatch[1].toLowerCase();
    const sectionContent = sectionMatch[2].trim();

    // 提取列表项 (支持 - 和 * 开头的列表)
    const items = sectionContent
      .split('\n')
      .map(line => line.trim())
      .filter(line => line.startsWith('-') || line.startsWith('*'))
      .map(line => line.substring(1).trim());

    if (sections[sectionName] !== undefined) {
      sections[sectionName] = items;
    }
  }

  return sections;
}

function formatReleaseBody(sections, version) {
  const lines = [];

  // 标题
  lines.push(`## FileTools v${version}`);
  lines.push('');

  // 重要提示
  lines.push('### 重要提示');
  lines.push('⚠️ **升级前请备份数据目录**（默认位于：');
  lines.push('- Windows: `%APPDATA%/com.filetools.app`');
  lines.push('- macOS: `~/Library/Application Support/com.filetools.app`');
  lines.push('- Linux: `~/.local/share/com.filetools.app`');
  lines.push('');

  // 根据是否有变更内容，添加描述性文字
  const hasChanges = Object.values(sections).some(arr => arr.length > 0);
  if (hasChanges) {
    lines.push('此版本包含重要修复和优化，建议所有用户升级。');
    lines.push('');
  }

  // 修复问题
  if (sections.fixed.length > 0) {
    lines.push('### 修复问题');
    for (const item of sections.fixed) {
      lines.push(`- 🐞 ${item}`);
    }
    lines.push('');
  }

  // 新增功能
  if (sections.added.length > 0) {
    lines.push('### 新增功能');
    for (const item of sections.added) {
      lines.push(`- ✨ ${item}`);
    }
    lines.push('');
  }

  // 优化改进
  if (sections.changed.length > 0) {
    lines.push('### 优化改进');
    for (const item of sections.changed) {
      lines.push(`- 🚀 ${item}`);
    }
    lines.push('');
  }

  // 安全更新
  if (sections.security.length > 0) {
    lines.push('### 安全更新');
    for (const item of sections.security) {
      lines.push(`- 🔒 ${item}`);
    }
    lines.push('');
  }

  // 下载地址 - 使用 Tauri 原生格式: FileTools_{version}_{arch}-{type}.{ext}
  lines.push('## 下载地址');
  lines.push('');

  // Windows
  lines.push('### Windows (不再支持 Win7)');
  lines.push('');
  lines.push('**正常版本（推荐）**');
  lines.push(`- [64位](${REPO_URL}/releases/download/v${version}/FileTools_${version}_x64-setup.exe)`);
  lines.push('');
  lines.push('**便携版（免安装）**');
  lines.push(`- [64位](${REPO_URL}/releases/download/v${version}/FileTools_${version}_x64-portable.zip)`);
  lines.push('');
  lines.push('**MSI 安装包（企业部署）**');
  lines.push(`- [64位](${REPO_URL}/releases/download/v${version}/FileTools_${version}_x64.msi)`);
  lines.push('');

  // macOS
  lines.push('### macOS');
  lines.push('');
  lines.push(`- [Apple M 芯片](${REPO_URL}/releases/download/v${version}/FileTools_${version}_aarch64.dmg)`);
  lines.push(`- [Intel 芯片](${REPO_URL}/releases/download/v${version}/FileTools_${version}_x64.dmg)`);
  lines.push('');

  // Linux
  lines.push('### Linux');
  lines.push('');
  lines.push('**DEB 包（Debian/Ubuntu 系）**');
  lines.push('使用 `sudo apt install ./文件路径` 安装');
  lines.push(`- [64位](${REPO_URL}/releases/download/v${version}/FileTools_${version}_amd64.deb)`);
  lines.push('');
  lines.push('**AppImage（通用，免安装）**');
  lines.push(`- [64位](${REPO_URL}/releases/download/v${version}/FileTools_${version}_amd64.AppImage)`);
  lines.push('');

  // 系统要求
  lines.push('## 系统要求');
  lines.push('');
  lines.push('- **Windows**: Windows 10/11 64位');
  lines.push('- **Linux**: Ubuntu 20.04+ / Debian 11+ / Fedora 35+ (64位)');
  lines.push('- **macOS**: macOS 10.15+ (Apple Silicon 或 Intel)');
  lines.push('- **内存**: 建议 8GB+ (索引大量文件时需要更多)');
  lines.push('');

  // 快速开始
  lines.push('## 快速开始');
  lines.push('');
  lines.push('1. 根据系统选择对应版本下载');
  lines.push('2. Windows/macOS 运行安装程序；Linux AppImage 赋予执行权限后直接运行');
  lines.push('3. 启动后浏览器自动打开 `http://127.0.0.1:18642`');
  lines.push('4. 在设置中添加要索引的目录，等待索引完成即可搜索');
  lines.push('');

  // FAQ
  lines.push('## FAQ');
  lines.push('');
  lines.push('**Q: 便携版和安装版有什么区别？**');
  lines.push('A: 便携版解压即可使用，不会在系统中注册，适合在多台电脑使用或U盘携带。安装版会创建开始菜单快捷方式并注册为系统应用。');
  lines.push('');
  lines.push('**Q: 索引会占用多少磁盘空间？**');
  lines.push('A: 索引文件约为原始文档大小的 10-20%。10GB 文档约需 1-2GB 索引空间。');
  lines.push('');
  lines.push('**Q: 如何升级？**');
  lines.push('A: 安装版直接运行新版本安装程序即可自动升级；便携版下载新版本 ZIP 解压覆盖。');
  lines.push('');
  lines.push('**Q: 支持多少文件数量？**');
  lines.push('A: 测试支持 10 万+ 文档，检索延迟 < 1 秒。');
  lines.push('');
  lines.push('**Q: 文件修改后索引会自动更新吗？**');
  lines.push('A: 是的，启用文件监控后，文件变更会在后台自动增量更新索引。');
  lines.push('');

  // 完整变更日志链接
  lines.push('---');
  lines.push('');
  lines.push(`**完整变更日志**: [CHANGELOG.md](${REPO_URL}/blob/main/CHANGELOG.md)`);
  lines.push('');
  lines.push(`**问题反馈**: [GitHub Issues](${REPO_URL}/issues)`);

  return lines.join('\n');
}

// 生成基本模板（当 CHANGELOG.md 中没有找到对应版本时使用）
function generateBasicTemplate(version) {
  return `## FileTools v${version}

### 重要提示
⚠️ **升级前请备份数据目录**（默认位于：
- Windows: \`%APPDATA%/com.filetools.app\`
- macOS: \`~/Library/Application Support/com.filetools.app\`
- Linux: \`~/.local/share/com.filetools.app\`

### 更新内容

详见 [CHANGELOG.md](${REPO_URL}/blob/main/CHANGELOG.md)

## 下载地址

### Windows (不再支持 Win7)

**正常版本（推荐）**
- [64位](${REPO_URL}/releases/download/v${version}/FileTools_${version}_x64-setup.exe)

**便携版（免安装）**
- [64位](${REPO_URL}/releases/download/v${version}/FileTools_${version}_x64-portable.zip)

**MSI 安装包（企业部署）**
- [64位](${REPO_URL}/releases/download/v${version}/FileTools_${version}_x64.msi)

### macOS
- [Apple M 芯片](${REPO_URL}/releases/download/v${version}/FileTools_${version}_aarch64.dmg)
- [Intel 芯片](${REPO_URL}/releases/download/v${version}/FileTools_${version}_x64.dmg)

### Linux
**DEB 包（Debian/Ubuntu 系）**
- [64位](${REPO_URL}/releases/download/v${version}/FileTools_${version}_amd64.deb)

**AppImage（通用）**
- [64位](${REPO_URL}/releases/download/v${version}/FileTools_${version}_amd64.AppImage)

## 系统要求
- **Windows**: Windows 10/11 64位
- **Linux**: Ubuntu 20.04+ / Debian 11+ (64位)
- **macOS**: macOS 10.15+ (Apple Silicon 或 Intel)
- **内存**: 建议 8GB+

## 快速开始
1. 下载对应平台的安装包
2. 运行安装程序（或解压便携版）
3. 启动 FileTools，浏览器将自动打开 http://127.0.0.1:18642

## FAQ

**Q: 便携版如何使用？**
A: 下载 portable.zip 后解压到任意目录，运行 FileTools.exe 即可。

**Q: 索引会占用多少磁盘空间？**
A: 约为原始文档大小的 10-20%。

**Q: 如何升级？**
A: Windows 用户直接运行新版本安装程序即可自动升级。

---

**完整变更日志**: [CHANGELOG.md](${REPO_URL}/blob/main/CHANGELOG.md)
`;
}

// 主逻辑
console.log(`Generating release notes for v${VERSION}...\n`);

try {
  const changelog = fs.readFileSync(CHANGELOG_PATH, 'utf8');
  const sections = parseChangelog(changelog, VERSION);

  let releaseBody;
  if (!sections || Object.values(sections).every(arr => arr.length === 0)) {
    console.log(`Warning: Version ${VERSION} not found in ${CHANGELOG_PATH}`);
    console.log('Using basic template...\n');
    releaseBody = generateBasicTemplate(VERSION);
  } else {
    releaseBody = formatReleaseBody(sections, VERSION);
    console.log('Parsed changelog sections:');
    for (const [key, items] of Object.entries(sections)) {
      if (items.length > 0) {
        console.log(`  - ${key}: ${items.length} items`);
      }
    }
  }

  fs.writeFileSync(OUTPUT_PATH, releaseBody);
  console.log(`\n✓ Release notes generated: ${OUTPUT_PATH}`);

} catch (err) {
  console.error(`Error reading ${CHANGELOG_PATH}:`, err.message);
  console.log('Using basic template...\n');
  const releaseBody = generateBasicTemplate(VERSION);
  fs.writeFileSync(OUTPUT_PATH, releaseBody);
  console.log(`\n✓ Release notes generated (basic template): ${OUTPUT_PATH}`);
}
