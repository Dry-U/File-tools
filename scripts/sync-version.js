#!/usr/bin/env node
/**
 * 版本号同步脚本
 * 从 Git tag 或环境变量读取版本，同步到所有配置文件
 */

const fs = require('fs');
const path = require('path');

const rawVersion = process.env.FILETOOLS_VERSION || process.argv[2];
const VERSION = rawVersion ? rawVersion.replace(/^v/, '') : null;

if (!VERSION) {
  console.error('Error: VERSION not provided');
  process.exit(1);
}

console.log(`Syncing version: ${VERSION}`);

// 1. 更新 tauri.conf.json
const tauriConfPath = path.join(__dirname, '../src-tauri/tauri.conf.json');
const tauriConf = JSON.parse(fs.readFileSync(tauriConfPath, 'utf8'));
tauriConf.version = VERSION;
fs.writeFileSync(tauriConfPath, JSON.stringify(tauriConf, null, 2) + '\n');
console.log('✓ Updated tauri.conf.json');

// 2. 更新 Cargo.toml
const cargoPath = path.join(__dirname, '../src-tauri/Cargo.toml');
let cargoContent = fs.readFileSync(cargoPath, 'utf8');
cargoContent = cargoContent.replace(
  /^version = "[^"]+"/m,
  `version = "${VERSION}"`
);
fs.writeFileSync(cargoPath, cargoContent);
console.log('✓ Updated Cargo.toml');

// 3. 更新 package.json
const packagePath = path.join(__dirname, '../package.json');
const packageJson = JSON.parse(fs.readFileSync(packagePath, 'utf8'));
packageJson.version = VERSION;
fs.writeFileSync(packagePath, JSON.stringify(packageJson, null, 2) + '\n');
console.log('✓ Updated package.json');

// 4. 更新 pyproject.toml
const pyprojectPath = path.join(__dirname, '../pyproject.toml');
let pyprojectContent = fs.readFileSync(pyprojectPath, 'utf8');
pyprojectContent = pyprojectContent.replace(
  /^\s*version = "[^"]+"/m,
  `version = "${VERSION}"`
);
fs.writeFileSync(pyprojectPath, pyprojectContent);
console.log('✓ Updated pyproject.toml');

// 5. 更新 VERSION 文件
const versionPath = path.join(__dirname, '../VERSION');
fs.writeFileSync(versionPath, VERSION + '\n');
console.log('✓ Updated VERSION file');

console.log('\nVersion sync complete!');
