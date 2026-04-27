#!/usr/bin/env node
/**
 * Release Body 生成脚本
 * 优先级：
 * 1. 从 GitHub API 获取 release-drafter 草稿（如果有）
 * 2. 从 CHANGELOG.md 提取（如果版本存在）
 * 3. 从 git commits 自动生成（fallback）
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const VERSION = process.env.VERSION;
const CHANGELOG_PATH = process.env.CHANGELOG_PATH || 'CHANGELOG.md';
const OUTPUT_PATH = process.env.OUTPUT_PATH || 'release-body.md';
const GITHUB_TOKEN = process.env.GITHUB_TOKEN;
const REPO = process.env.GITHUB_REPOSITORY || 'Dariandai/File-tools';

const REPO_URL = 'https://github.com/' + REPO;

async function getDraftReleaseBody() {
  if (!GITHUB_TOKEN) {
    console.log('GITHUB_TOKEN not available, skipping draft release check');
    return null;
  }

  try {
    const response = await fetch(
      `https://api.github.com/repos/${REPO}/releases?per_page=10`,
      {
        headers: {
          Authorization: `token ${GITHUB_TOKEN}`,
          Accept: 'application/vnd.github.v3+json',
          'User-Agent': 'FileTools-release-script',
        },
      }
    );

    if (!response.ok) {
      console.log(`GitHub API error: ${response.status}`);
      return null;
    }

    const releases = await response.json();

    // 查找 draft release
    const draft = releases.find((r) => r.draft && r.tag_name === `v${VERSION}`);
    if (draft && draft.body) {
      console.log(`Found draft release for v${VERSION}`);
      return draft.body;
    }

    console.log(`No draft release found for v${VERSION}`);
    return null;
  } catch (err) {
    console.log(`Error fetching draft release: ${err.message}`);
    return null;
  }
}

function parseChangelog(content, version) {
  const sections = {
    added: [],
    changed: [],
    fixed: [],
    security: [],
    deprecated: [],
    removed: [],
  };

  const versionRegex = new RegExp(`## \\[${version}\\].*?(?=## \\[|$)`, 's');
  const match = content.match(versionRegex);

  if (!match) {
    return null;
  }

  const versionContent = match[0];

  const sectionRegex = /### (\w+)\n([\s\S]*?)(?=### |$)/g;
  let sectionMatch;

  while ((sectionMatch = sectionRegex.exec(versionContent)) !== null) {
    const sectionName = sectionMatch[1].toLowerCase();
    const sectionContent = sectionMatch[2].trim();

    const items = sectionContent
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line.startsWith('-') || line.startsWith('*'))
      .map((line) => line.substring(1).trim());

    if (sections[sectionName] !== undefined) {
      sections[sectionName] = items;
    }
  }

  return sections;
}

function getCommitsSinceLastTag() {
  try {
    const lastTag = execSync('git describe --tags --abbrev=0', {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    }).trim();

    console.log(`Last tag: ${lastTag}`);

    const commits = execSync(
      `git log ${lastTag}..HEAD --pretty=format:"%s|%h|%an"`,
      { encoding: 'utf8' }
    ).split('\n');

    const categorized = {
      feat: [],
      fix: [],
      docs: [],
      perf: [],
      refactor: [],
      security: [],
      ci: [],
      build: [],
      chore: [],
      other: [],
    };

    for (const commit of commits) {
      if (!commit.trim()) continue;

      const [message, hash, author] = commit.split('|');
      const type = message.split(':')[0].toLowerCase().trim();

      if (categorized[type]) {
        categorized[type].push({ message, hash, author });
      } else {
        categorized.other.push({ message, hash, author });
      }
    }

    return categorized;
  } catch (err) {
    console.log(`Error getting commits: ${err.message}`);
    return null;
  }
}

function generateFromCommits(commits, version) {
  const lines = [];

  lines.push(`## FileTools v${version}`);
  lines.push('');
  lines.push('### 重要提示');
  lines.push('⚠️ **升级前请备份数据目录**（默认位于：');
  lines.push('- Windows: `%APPDATA%/com.filetools.app`');
  lines.push('- macOS: `~/Library/Application Support/com.filetools.app`');
  lines.push('- Linux: `~/.local/share/com.filetools.app`');
  lines.push('');

  const emojiMap = {
    feat: '✨',
    fix: '🐞',
    docs: '📚',
    perf: '⚡',
    refactor: '🎨',
    security: '🔒',
    ci: '🛠️',
    build: '🏗️',
    chore: '🔧',
    other: '📌',
  };

  const labelMap = {
    feat: '新功能',
    fix: '问题修复',
    docs: '文档更新',
    perf: '性能优化',
    refactor: '代码重构',
    security: '安全更新',
    ci: 'CI 构建',
    build: '构建系统',
    chore: '其他变更',
    other: '其他变更',
  };

  let hasChanges = false;
  for (const [type, items] of Object.entries(commits)) {
    if (items.length > 0) {
      hasChanges = true;
      lines.push(`### ${emojiMap[type]} ${labelMap[type]}`);
      for (const item of items) {
        lines.push(`- ${emojiMap[type]} ${item.message} (${item.hash})`);
      }
      lines.push('');
    }
  }

  if (!hasChanges) {
    lines.push('此版本为常规更新。');
    lines.push('');
  }

  return lines.join('\n');
}

function formatReleaseBody(sections, version) {
  const lines = [];

  lines.push(`## FileTools v${version}`);
  lines.push('');

  lines.push('### 重要提示');
  lines.push('⚠️ **升级前请备份数据目录**（默认位于：');
  lines.push('- Windows: `%APPDATA%/com.filetools.app`');
  lines.push('- macOS: `~/Library/Application Support/com.filetools.app`');
  lines.push('- Linux: `~/.local/share/com.filetools.app`');
  lines.push('');

  const hasChanges = Object.values(sections).some((arr) => arr.length > 0);
  if (hasChanges) {
    lines.push('此版本包含重要修复和优化，建议所有用户升级。');
    lines.push('');
  }

  if (sections.fixed.length > 0) {
    lines.push('### 🐞 修复问题');
    for (const item of sections.fixed) {
      lines.push(`- 🐞 ${item}`);
    }
    lines.push('');
  }

  if (sections.added.length > 0) {
    lines.push('### ✨ 新增功能');
    for (const item of sections.added) {
      lines.push(`- ✨ ${item}`);
    }
    lines.push('');
  }

  if (sections.changed.length > 0) {
    lines.push('### 🚀 优化改进');
    for (const item of sections.changed) {
      lines.push(`- 🚀 ${item}`);
    }
    lines.push('');
  }

  if (sections.security.length > 0) {
    lines.push('### 🔒 安全更新');
    for (const item of sections.security) {
      lines.push(`- 🔒 ${item}`);
    }
    lines.push('');
  }

  return lines.join('\n');
}

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

### Windows
- [64位安装包](${REPO_URL}/releases/download/v${version}/FileTools_${version}_x64-setup.exe)
- [64位便携版](${REPO_URL}/releases/download/v${version}/FileTools_${version}_x64-portable.zip)
- [64位MSI](${REPO_URL}/releases/download/v${version}/FileTools_${version}_x64.msi)

### macOS
- [Apple M 芯片](${REPO_URL}/releases/download/v${version}/FileTools_${version}_aarch64.dmg)

### Linux
- [DEB 包](${REPO_URL}/releases/download/v${version}/FileTools_${version}_amd64.deb)
- [AppImage](${REPO_URL}/releases/download/v${version}/FileTools_${version}_amd64.AppImage)

## 系统要求
- **Windows**: Windows 10/11 64位
- **Linux**: Ubuntu 20.04+ / Debian 11+ (64位)
- **macOS**: macOS 10.15+ (Apple Silicon)

---

**完整变更日志**: [CHANGELOG.md](${REPO_URL}/blob/main/CHANGELOG.md)
`;
}

function appendDownloadLinks(body, version) {
  const lines = body.split('\n');

  // 找到合适的位置插入下载链接（在 FAQ 之前或文件末尾）
  const faqIndex = lines.findIndex((l) => l.startsWith('## FAQ'));
  const insertIndex = faqIndex > 0 ? faqIndex : lines.length;

  const downloadSection = `
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

### Linux
**DEB 包（Debian/Ubuntu 系）**
- [64位](${REPO_URL}/releases/download/v${version}/FileTools_${version}_amd64.deb)

**AppImage（通用）**
- [64位](${REPO_URL}/releases/download/v${version}/FileTools_${version}_amd64.AppImage)

---

**问题反馈**: [GitHub Issues](${REPO_URL}/issues)
`;

  lines.splice(insertIndex, 0, downloadSection);

  return lines.join('\n');
}

async function main() {
  console.log(`Generating release notes for v${VERSION}...\n`);

  // 1. 尝试从 GitHub API 获取 release-drafter 草稿
  const draftBody = await getDraftReleaseBody();
  if (draftBody) {
    const withLinks = appendDownloadLinks(draftBody, VERSION);
    fs.writeFileSync(OUTPUT_PATH, withLinks);
    console.log(`✓ Release notes from draft: ${OUTPUT_PATH}`);
    return;
  }

  // 2. 尝试从 CHANGELOG.md 提取
  try {
    const changelog = fs.readFileSync(CHANGELOG_PATH, 'utf8');
    const sections = parseChangelog(changelog, VERSION);

    if (sections && Object.values(sections).some((arr) => arr.length > 0)) {
      let releaseBody = formatReleaseBody(sections, VERSION);
      releaseBody = appendDownloadLinks(releaseBody, VERSION);
      fs.writeFileSync(OUTPUT_PATH, releaseBody);
      console.log('✓ Release notes from CHANGELOG.md');
      console.log('Parsed sections:');
      for (const [key, items] of Object.entries(sections)) {
        if (items.length > 0) {
          console.log(`  - ${key}: ${items.length} items`);
        }
      }
      return;
    }
  } catch (err) {
    console.log(`CHANGELOG.md not found or parse error: ${err.message}`);
  }

  // 3. Fallback: 从 git commits 自动生成
  console.log('Falling back to git commits...');
  const commits = getCommitsSinceLastTag();
  if (commits) {
    let releaseBody = generateFromCommits(commits, VERSION);
    releaseBody = appendDownloadLinks(releaseBody, VERSION);
    fs.writeFileSync(OUTPUT_PATH, releaseBody);
    console.log('✓ Release notes from git commits');
    return;
  }

  // 4. 最终 fallback: 基本模板
  console.log('Using basic template...');
  const basic = generateBasicTemplate(VERSION);
  fs.writeFileSync(OUTPUT_PATH, basic);
  console.log(`✓ Release notes (basic template): ${OUTPUT_PATH}`);
}

main().catch((err) => {
  console.error('Error:', err);
  const basic = generateBasicTemplate(process.env.VERSION || 'unknown');
  fs.writeFileSync(OUTPUT_PATH, basic);
  console.log(`✓ Release notes (error fallback): ${OUTPUT_PATH}`);
});
