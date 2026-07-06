/**
 * N8N SQLite 数据库一键深度优化工具
 * 运行方式: node optimize_db.js
 */
const fs = require('fs');
const path = require('path');
const os = require('os');

const userHome = process.env.USERPROFILE || os.homedir() || 'C:\\Users\\video';
const DB_PATH = process.env.DB_PATH || path.join(userHome, '.n8n', 'database.sqlite');

if (!fs.existsSync(DB_PATH)) {
  console.error('[ERROR] 找不到数据库文件:', DB_PATH);
  process.exit(1);
}

const stat = fs.statSync(DB_PATH);
console.log('[INFO] 数据库路径: ' + DB_PATH);
console.log('[INFO] 数据库大小: ' + (stat.size / 1024 / 1024).toFixed(2) + ' MB');

// 搜索 sqlite3 或 better-sqlite3 模块（N8N 使用 sqlite3 异步驱动）
const desktopPath = path.join(userHome, 'Desktop');
const NODE_DIR = path.join(desktopPath, 'node-v22.16.0-win-x64');
const N8N_MODULES = path.join(NODE_DIR, 'node_modules', 'n8n', 'node_modules');
const possibleSqlite3 = [
  path.join(N8N_MODULES, 'sqlite3'),
  path.join(NODE_DIR, 'node_modules', 'sqlite3'),
];
const possibleBetter = [
  path.join(N8N_MODULES, 'better-sqlite3'),
  path.join(NODE_DIR, 'node_modules', 'better-sqlite3'),
];

// 优先尝试 better-sqlite3（同步，更容易操控）
let Database = null;
let useAsync = false;

for (const p of possibleBetter) {
  try {
    Database = require(p);
    console.log('[INFO] 使用 better-sqlite3: ' + p);
    break;
  } catch (e) { /* 继续 */ }
}

// 降级到 sqlite3（异步）
let sqlite3 = null;
if (!Database) {
  for (const p of possibleSqlite3) {
    try {
      sqlite3 = require(p);
      console.log('[INFO] 使用 sqlite3（异步模式）: ' + p);
      useAsync = true;
      break;
    } catch (e) { /* 继续 */ }
  }
}

if (!Database && !sqlite3) {
  // 最后手段：系统级 sqlite3 CLI（如果存在）
  console.log('[WARN] 未找到 Node.js SQLite 模块，尝试通过 SQLite CLI 优化...');
  runWithCLI();
  process.exit(0);
}

// ===================== better-sqlite3 同步模式 =====================
if (!useAsync && Database) {
  try {
    const db = new Database(DB_PATH);
    runOptimizationsSync(db);
    db.close();
    printResult();
  } catch (e) {
    console.error('[ERROR]', e.message);
    process.exit(1);
  }
}

// ===================== sqlite3 异步模式 =====================
if (useAsync && sqlite3) {
  const db = new sqlite3.Database(DB_PATH, (err) => {
    if (err) {
      console.error('[ERROR] 无法打开数据库:', err.message);
      process.exit(1);
    }
    runOptimizationsAsync(db);
  });
}

// ===================== 同步优化函数 =====================
function runOptimizationsSync(db) {
  const steps = [
    { pragma: 'PRAGMA journal_mode = WAL', label: 'WAL 模式（读写并发）' },
    { pragma: 'PRAGMA synchronous = NORMAL', label: '同步模式 NORMAL（高效安全）' },
    { pragma: 'PRAGMA busy_timeout = 5000', label: '锁等待 5 秒（防 Database connection timed out）' },
    { pragma: 'PRAGMA cache_size = -65536', label: '页面缓存 64MB（64GB 内存充裕）' },
    { pragma: 'PRAGMA temp_store = MEMORY', label: '临时表存内存' },
    { pragma: 'PRAGMA mmap_size = 536870912', label: '内存映射 512MB' },
    { pragma: 'PRAGMA page_size = 8192', label: '页面大小 8KB（大数据优化）' },
  ];

  for (const s of steps) {
    db.prepare(s.pragma).run();
    console.log('[OK]  ' + s.label);
  }

  console.log('[RUN] 正在执行 VACUUM（碎片整理）...');
  db.prepare('VACUUM').run();
  console.log('[OK]  VACUUM 完成');

  console.log('[RUN] 正在执行 ANALYZE...');
  db.prepare('ANALYZE').run();
  console.log('[OK]  ANALYZE 完成');
}

// ===================== 异步优化函数 =====================
function runOptimizationsAsync(db) {
  const pragmas = [
    'PRAGMA journal_mode = WAL',
    'PRAGMA synchronous = NORMAL',
    'PRAGMA busy_timeout = 5000',
    'PRAGMA cache_size = -65536',
    'PRAGMA temp_store = MEMORY',
    'PRAGMA mmap_size = 536870912',
  ];

  const labels = [
    'WAL 模式（读写并发）',
    '同步模式 NORMAL（高效安全）',
    '锁等待 5 秒（防 Database connection timed out）',
    '页面缓存 64MB（64GB 内存充裕）',
    '临时表存内存',
    '内存映射 512MB',
  ];

  let i = 0;
  function nextPragma() {
    if (i >= pragmas.length) {
      console.log('[RUN] 正在执行 VACUUM（碎片整理）...');
      db.run('VACUUM', (err) => {
        if (err) console.error('[WARN] VACUUM:', err.message);
        else console.log('[OK]  VACUUM 完成');
        console.log('[RUN] 正在执行 ANALYZE...');
        db.run('ANALYZE', (err2) => {
          if (err2) console.error('[WARN] ANALYZE:', err2.message);
          else console.log('[OK]  ANALYZE 完成');
          db.close(() => printResult());
        });
      });
      return;
    }
    db.run(pragmas[i], (err) => {
      if (err) console.error('[WARN] ' + labels[i] + ':', err.message);
      else console.log('[OK]  ' + labels[i]);
      i++;
      nextPragma();
    });
  }

  nextPragma();
}

// ===================== CLI 回退方案 =====================
function runWithCLI() {
  const { execSync } = require('child_process');
  const cmds = [
    'PRAGMA journal_mode=WAL;',
    'PRAGMA synchronous=NORMAL;',
    'PRAGMA cache_size=-32000;',
    'VACUUM;',
    'ANALYZE;',
  ];
  try {
    for (const cmd of cmds) {
      execSync('sqlite3 "' + DB_PATH + '" "' + cmd + '"', { stdio: 'inherit' });
    }
    console.log('[OK] CLI 优化完成');
  } catch (e) {
    console.log('[WARN] sqlite3 CLI 未安装，跳过优化。N8N 启动后会自动优化。');
  }
}

function printResult() {
  const newStat = fs.statSync(DB_PATH);
  const savedMB = ((stat.size - newStat.size) / 1024 / 1024).toFixed(2);
  console.log('');
  console.log('======================================');
  console.log(' 数据库深度优化完成！');
  console.log(' 优化前: ' + (stat.size / 1024 / 1024).toFixed(2) + ' MB');
  console.log(' 优化后: ' + (newStat.size / 1024 / 1024).toFixed(2) + ' MB');
  if (parseFloat(savedMB) > 0) console.log(' 节省空间: ' + savedMB + ' MB');
  console.log('======================================');
}
