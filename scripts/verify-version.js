#!/usr/bin/env node
/**
 * 版本号验证脚本
 * 验证所有配置文件的版本号一致
 */

const fs = require('fs');
const path = require('path');

const EXPECTED_VERSION = process.env.FILETOOLS_VERSION || process.argv[2];

if (!EXPECTED_VERSION) {
  console.error('Error: VERSION not provided');
  process.exit(1);
}

function getVersion(filePath, extractor) {
  const content = fs.readFileSync(filePath, 'utf8');
  return extractor(content);
}

const versions = {
  'tauri.conf.json': getVersion(
    path.join(__dirname, '../src-tauri/tauri.conf.json'),
    (c) => JSON.parse(c).version
  ),
  'Cargo.toml': getVersion(
    path.join(__dirname, '../src-tauri/Cargo.toml'),
    (c) => c.match(/^version = "([^"]+)"/m)?.[1]
  ),
  'package.json': getVersion(
    path.join(__dirname, '../package.json'),
    (c) => JSON.parse(c).version
  ),
  'pyproject.toml': getVersion(
    path.join(__dirname, '../pyproject.toml'),
    (c) => c.match(/^\s*version = "([^"]+)"/m)?.[1]
  ),
  'VERSION': getVersion(
    path.join(__dirname, '../VERSION'),
    (c) => c.trim()
  ),
};

console.log('Version check:');
console.log(`Expected: ${EXPECTED_VERSION}`);
console.log('');

let allMatch = true;
for (const [file, version] of Object.entries(versions)) {
  const match = version === EXPECTED_VERSION;
  const status = match ? '✓' : '✗';
  console.log(`  ${status} ${file}: ${version}`);
  if (!match) allMatch = false;
}

if (!allMatch) {
  console.error(`\nError: Version mismatch! All files must be ${EXPECTED_VERSION}`);
  process.exit(1);
}

console.log('\n✓ All versions match!');
