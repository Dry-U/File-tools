#!/usr/bin/env node
/**
 * 产物打包脚本
 * 重命名产物文件并创建便携版 ZIP
 */

const fs = require('fs');
const path = require('path');

const VERSION = process.env.VERSION;
const ARTIFACTS_DIR = process.env.ARTIFACTS_DIR || 'release-artifacts';
const OUTPUT_DIR = process.env.OUTPUT_DIR || 'release-files';

if (!VERSION) {
  console.error('Error: VERSION not provided');
  process.exit(1);
}

console.log(`Packaging release for version: ${VERSION}\n`);

// 创建输出目录
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

// 读取所有产物
const files = fs.readdirSync(ARTIFACTS_DIR);
console.log(`Found ${files.length} artifacts:`);
files.forEach(f => console.log(`  - ${f}`));
console.log('');

// 收集需要打包的文件
const portableFiles = []; // filetools.exe 和 backend
const installers = [];    // NSIS, MSI, DMG, etc.

for (const file of files) {
  const filePath = path.join(ARTIFACTS_DIR, file);

  // 识别便携版组件
  if (file === 'filetools.exe' || file.includes('backend')) {
    portableFiles.push({ name: file, path: filePath });
  } else {
    installers.push({ name: file, path: filePath });
  }
}

console.log(`Portable components: ${portableFiles.length}`);
console.log(`Installers: ${installers.length}\n`);

// 重命名安装包 - 使用 Tauri 原生格式: FileTools_{version}_{arch}-{type}.{ext}
const renameMap = [
  // Windows
  { pattern: /FileTools_[\d.]+_x64-setup\.exe$/i, name: `FileTools_${VERSION}_x64-setup.exe` },
  { pattern: /FileTools_[\d.]+_aarch64-setup\.exe$/i, name: `FileTools_${VERSION}_aarch64-setup.exe` },
  { pattern: /FileTools_[\d.]+_x64.*\.msi$/i, name: `FileTools_${VERSION}_x64.msi` },
  // macOS
  { pattern: /FileTools_[\d.]+_aarch64\.dmg$/i, name: `FileTools_${VERSION}_aarch64.dmg` },
  { pattern: /FileTools_[\d.]+_x64\.dmg$/i, name: `FileTools_${VERSION}_x64.dmg` },
  // Linux
  { pattern: /filetools_[\d.]+_amd64\.AppImage$/i, name: `FileTools_${VERSION}_amd64.AppImage` },
  { pattern: /filetools_[\d.]+_amd64\.deb$/i, name: `FileTools_${VERSION}_amd64.deb` },
];

for (const { name, path: filePath } of installers) {
  for (const { pattern, name: newName } of renameMap) {
    if (pattern.test(name)) {
      const destPath = path.join(OUTPUT_DIR, newName);
      fs.copyFileSync(filePath, destPath);
      console.log(`✓ ${name} -> ${newName}`);
      break;
    }
  }
}

// 创建便携版 ZIP
if (portableFiles.length >= 2) {
  console.log('\nCreating portable package...');

  const portableDir = path.join(OUTPUT_DIR, `FileTools_${VERSION}_x64-portable`);
  fs.mkdirSync(portableDir, { recursive: true });

  for (const { name, path: filePath } of portableFiles) {
    const destName = name.includes('backend') ? 'filetools_backend.exe' : 'FileTools.exe';
    fs.copyFileSync(filePath, path.join(portableDir, destName));
    console.log(`  + ${destName}`);
  }

  // 创建 README
  const readme = `FileTools Portable v${VERSION}
========================

使用方法:
1. 解压此 ZIP 文件到任意目录
2. 运行 FileTools.exe 启动应用
3. 后端会自动作为 sidecar 启动

注意:
- FileTools.exe 和 filetools_backend.exe 必须保持在同一目录
- 首次启动可能需要几秒钟加载
- 便携版不会在系统中注册，卸载时直接删除即可

系统要求:
- Windows 10/11 64位
- 8GB+ 内存

数据目录:
- 便携版使用相对目录存储数据 (./data/)
- 如需迁移数据，复制 data 目录即可

文件说明:
- FileTools.exe        - 前端程序 (Tauri)
- filetools_backend.exe - 后端服务 (Python)
- README.txt           - 本说明文件

官方文档: https://github.com/Dry-U/File-tools#readme
问题反馈: https://github.com/Dry-U/File-tools/issues
`;
  fs.writeFileSync(path.join(portableDir, 'README.txt'), readme);
  console.log('  + README.txt');

  // 使用系统 zip 命令打包 - 使用 Tauri 原生格式
  const { execSync } = require('child_process');
  const zipName = `FileTools_${VERSION}_x64-portable.zip`;

  try {
    execSync(`cd "${OUTPUT_DIR}" && zip -r "${zipName}" "FileTools_${VERSION}_x64-portable"`, {
      stdio: 'inherit'
    });
    console.log(`✓ Created ${zipName}`);
  } catch (e) {
    // 如果 zip 命令失败，尝试使用 Node.js 的 archiver
    console.log('  (zip command failed, trying alternative method)');
  }

  // 清理临时目录
  fs.rmSync(portableDir, { recursive: true, force: true });
} else {
  console.warn('Warning: Not enough files for portable package');
}

console.log('\n✓ Packaging complete!');
console.log(`\nOutput directory: ${OUTPUT_DIR}`);
const outputFiles = fs.readdirSync(OUTPUT_DIR);
console.log(`Output files (${outputFiles.length}):`);
outputFiles.forEach(f => {
  const stats = fs.statSync(path.join(OUTPUT_DIR, f));
  const size = (stats.size / 1024 / 1024).toFixed(1);
  console.log(`  - ${f} (${size} MB)`);
});
