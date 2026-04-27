#!/usr/bin/env node
/**
 * 使用 changelogen 生成 changelog 并同步到 GitHub Release
 *
 * 用法:
 *   node scripts/generate-changelog.js              # 生成到 CHANGELOG.md
 *   node scripts/generate-changelog.js --release   # 生成并创建 GitHub Release
 *   node scripts/generate-changelog.js --dry        # 仅预览，不写入文件
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const VERSION = process.env.VERSION;
const GITHUB_TOKEN = process.env.GITHUB_TOKEN;
const IS_DRY_RUN = process.argv.includes('--dry');
const IS_RELEASE = process.argv.includes('--release');
const REPO = process.env.GITHUB_REPOSITORY || 'Dariandai/File-tools';
const REPO_URL = 'https://github.com/' + REPO;

function log(msg) {
  console.log(`[changelog] ${msg}`);
}

function run(cmd, options = {}) {
  log(`Running: ${cmd}`);
  try {
    return execSync(cmd, {
      encoding: 'utf8',
      stdio: 'pipe',
      ...options,
    }).trim();
  } catch (err) {
    if (options.ignoreError) return '';
    console.error(`Command failed: ${cmd}`);
    console.error(err.message);
    process.exit(1);
  }
}

async function main() {
  log('Starting changelog generation...');

  // 1. 检查 changelogen 是否可用
  try {
    run('npx changelogen --version --no-install');
  } catch (err) {
    log('Installing changelogen...');
    run('npm install -D changelogen');
  }

  // 2. 生成 changelog
  if (IS_DRY_RUN) {
    log('DRY RUN mode - only preview');
    const output = run('npx changelogen --no-output --dir .');
    console.log(output);
    return;
  }

  // 3. 更新 CHANGELOG.md
  log('Generating CHANGELOG.md...');
  run('npx changelogen --output CHANGELOG.md --dir .');
  log('CHANGELOG.md updated');

  // 4. 如果指定 --release，同步到 GitHub
  if (IS_RELEASE) {
    if (!GITHUB_TOKEN) {
      log('GITHUB_TOKEN not available, skipping GitHub release');
      return;
    }

    log('Syncing to GitHub Release...');
    run(`npx changelogen gh release --token ${GITHUB_TOKEN} --dir .`);
    log('GitHub Release created/updated');
  }

  log('Done!');
}

main().catch((err) => {
  console.error('Error:', err);
  process.exit(1);
});
