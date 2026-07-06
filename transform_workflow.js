/**
 * 工作流简化转换脚本
 * 读取现有 workflow_dump.json，删除图片生成循环节点，
 * 重写解析节点为直接从本地目录读取首尾帧，输出简化版 JSON。
 */
const fs = require('fs');
const path = require('path');

const srcPath = path.join(__dirname, 'workflow_dump.json');
const outPath = path.join(__dirname, 'workflow_simplified.json');
const raw = fs.readFileSync(srcPath, 'utf8').replace(/^\uFEFF/, '');
const workflow = JSON.parse(raw);

// ── 1. 要删除的节点名称 ──
const REMOVE = new Set([
  '图片循环', '准备图片参考', '创建图片任务',
  '合并图片创建上下文', '图片状态路由', '保存图片结果',
  '准备图片重试', '等待图片重试', '停止：图片失败',
  '汇总图片结果', '拆分视频任务',
  '生成视频参考帧尺寸', '合并尺寸处理上下文',
  '输入与解析说明', 'HTTP 接口说明', '最终输出说明',
]);

// ── 2. 新的「解析视频任务」节点代码 ──
const NEW_PARSE_CODE = `
const os = require('os');
const path = require('path');
const fs = require('fs');
const row = $input.first().json;

function text(value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value.trim();
  if (Array.isArray(value)) return value.map(text).filter(Boolean).join('\\n').trim();
  if (typeof value === 'object') {
    if (typeof value.plain_text === 'string') return value.plain_text.trim();
    if (typeof value.content === 'string') return value.content.trim();
    if (typeof value.name === 'string') return value.name.trim();
    if (Array.isArray(value.rich_text)) return value.rich_text.map(text).filter(Boolean).join('\\n').trim();
    if (Array.isArray(value.title)) return value.title.map(text).filter(Boolean).join(' ').trim();
    if (value.status) return text(value.status);
    if (value.text) return text(value.text);
  }
  return '';
}

function sectionsFromText(sourceText, kind) {
  const lines = String(sourceText || '').split(/\\r?\\n/);
  const out = [];
  let current = null;
  const flush = () => {
    if (current && current.body.length) out.push({ ...current, prompt: current.body.join('\\n').trim() });
  };
  for (const raw of lines) {
    const t = raw.trim().replace(/^[#>*\\-\\s]+/, '');
    const headerText = t.replace(/^(图片提示词|视频提示词|image prompts?|video prompts?)\\s*/i, '').trim();
    if (!headerText) continue;
    const m = headerText.match(/^(IMAGE|VIDEO|图片|视频)\\s*(\\d+)\\s*[:：]?\\s*(.*)$/i);
    if (m) {
      flush();
      current = null;
      const sectionKind = (/^图片$/i.test(m[1]) || /^IMAGE$/i.test(m[1])) ? 'IMAGE' : 'VIDEO';
      if (sectionKind === kind) {
        current = { slot: kind + ' ' + Number(m[2]), index: Number(m[2]), body: [] };
        if (m[3]) current.body.push(m[3]);
      }
      continue;
    }
    if (current) current.body.push(raw);
  }
  flush();
  return out.filter((x) => x.prompt);
}

function safePart(value) {
  return String(value || 'yunwu').replace(/[^\\p{L}\\p{N}_-]+/gu, '_').replace(/^_+|_+$/g, '').slice(0, 80) || 'yunwu';
}

function resolveLocalPath(value) {
  const raw = String(value || '').trim();
  const home = os.homedir();
  if (!raw) return path.join(home, '.n8n-files', 'image-output');
  const expanded = raw.replace(/^~(?=$|[\\\\/])/, home).replace(/\\$\\{HOME\\}|\\$HOME|%USERPROFILE%|%HOME%/gi, home);
  return path.resolve(expanded);
}

function findExistingImage(saveRoot, stem, imageIndex) {
  if (!fs.existsSync(saveRoot)) return '';
  const prefix = stem + '_image' + imageIndex + '_';
  const files = fs.readdirSync(saveRoot)
    .filter(name => name.startsWith(prefix) && /\\.(png|jpg|jpeg|webp|gif)$/i.test(name))
    .map(name => ({ fullPath: path.join(saveRoot, name), mtimeMs: fs.statSync(path.join(saveRoot, name)).mtimeMs }))
    .sort((a, b) => b.mtimeMs - a.mtimeMs);
  return files.length ? files[0].fullPath : '';
}

const props = row.properties || {};
const name = text(row.Name) || text(row.name) || text(props.Name) || 'Notion prompt task';
const status = text(row["状态"]) || text(row.status) || text(props["状态"]);
const prompt = text(row.Prompt) || text(row.prompt) || text(props.Prompt);
const creative = text(row["创意"]) || text(row.creative) || text(props["创意"]);
const rawPrompt = prompt || creative;
if (!rawPrompt) throw new Error('Notion task is missing Prompt content.');

const trimmed = rawPrompt.trim();
let sourcePack;
try {
  sourcePack = (trimmed.startsWith('{') || trimmed.startsWith('[')) ? JSON.parse(trimmed) : { promptPack: trimmed };
} catch (error) {
  sourcePack = { promptPack: trimmed };
}
const pack = {
  ...sourcePack,
  title: sourcePack.title || name,
  taskKey: row.id || row.pageId || row.url || sourcePack.taskKey || name,
  notionTask: { id: row.id || row.pageId || '', url: row.url || '', name, status, creative },
};

const config = row.config || {};
const saveRoot = resolveLocalPath(config.imageSaveRoot);
const stem = safePart(pack.taskKey || pack.title);

// 解析 IMAGE 段（仅用于确定 firstImage/lastImage 索引上限）
const images = Array.isArray(pack.images) ? pack.images : sectionsFromText(pack.promptPack || pack.promptPacked || pack.prompts || '', 'IMAGE');
const maxImageIndex = images.reduce((max, img, i) => Math.max(max, Number(img.index || i + 1)), 0);

// 解析 VIDEO 段
const videos = Array.isArray(pack.videos) ? pack.videos : sectionsFromText(pack.promptPack || pack.promptPacked || pack.prompts || '', 'VIDEO').map((v) => ({ ...v, firstImage: v.index }));
if (!videos.length) throw new Error('Prompt Pack must include videos[] or VIDEO sections.');

// 支持 Notion 属性或 JSON pack 中直接指定帧 URL
const notionFirst = text(props['首帧']) || text(props['firstFrame']) || text(row.firstFrame) || '';
const notionLast = text(props['尾帧']) || text(props['lastFrame']) || text(row.lastFrame) || '';
const packFirst = pack.firstFrameUrl || pack.firstFrame || '';
const packLast = pack.lastFrameUrl || pack.lastFrame || '';

const tasks = videos.map((item, i) => {
  const index = Number(item.index || String(item.slot || '').match(/\\d+/)?.[0] || i + 1);
  const videoPrompt = String(item.prompt || item.text || '').trim();
  const firstIdx = item.firstImage === null ? null : Number(item.firstImage || item.firstImageIndex || i + 1);
  const lastIdx = item.lastImage === undefined
    ? (firstIdx !== null && firstIdx + 1 <= maxImageIndex ? firstIdx + 1 : null)
    : (item.lastImage === null ? null : Number(item.lastImage));

  // 优先级：pack 指定 > Notion 属性 > 本地目录查找
  let firstFileUrl = packFirst || notionFirst || (firstIdx ? findExistingImage(saveRoot, stem, firstIdx) : '');
  let lastFileUrl = packLast || notionLast || (lastIdx ? findExistingImage(saveRoot, stem, lastIdx) : '');

  const isLocalFirst = firstFileUrl && !/^https?:\\/\\//i.test(firstFileUrl);
  const isLocalLast = lastFileUrl && !/^https?:\\/\\//i.test(lastFileUrl);

  return {
    json: {
      title: pack.title,
      taskKey: pack.taskKey,
      notionTask: pack.notionTask,
      config,
      slot: item.slot || 'VIDEO ' + index,
      index,
      prompt: videoPrompt,
      firstImage: firstIdx,
      lastImage: lastIdx,
      firstFileUrl: firstFileUrl,
      lastFileUrl: lastFileUrl,
      firstLocalPath: isLocalFirst ? firstFileUrl : '',
      lastLocalPath: isLocalLast ? lastFileUrl : '',
      firstFileName: firstFileUrl ? path.basename(firstFileUrl) || 'first.png' : 'first.png',
      lastFileName: lastFileUrl ? path.basename(lastFileUrl) || 'last.png' : 'last.png',
      noVideos: false,
    }
  };
}).filter(t => t.json.prompt);

if (!tasks.length) throw new Error('No video tasks found in prompt.');
return tasks;
`.trim();

// ── 3. 过滤节点 ──
workflow.nodes = workflow.nodes.filter(n => !REMOVE.has(n.name));

// ── 4. 重写解析节点 ──
const parseNode = workflow.nodes.find(n => n.name === '解析并拆分图片任务');
if (parseNode) {
  parseNode.name = '解析视频任务';
  parseNode.parameters.jsCode = NEW_PARSE_CODE;
}

// ── 5. 重建连接 ──
const conn = {};

// 手动触发 → 读取 Notion
conn["When clicking 'Execute workflow'"] = { main: [[{ node: '读取 Notion 任务', type: 'main', index: 0 }]] };
// Notion → 统一配置
conn['读取 Notion 任务'] = { main: [[{ node: '统一配置', type: 'main', index: 0 }]] };
// 统一配置 → 解析视频任务
conn['统一配置'] = { main: [[{ node: '解析视频任务', type: 'main', index: 0 }]] };
// 解析视频任务 → 视频创建与状态路由
conn['解析视频任务'] = { main: [[{ node: '视频创建与状态路由', type: 'main', index: 0 }]] };

// 视频创建与状态路由 (4 outputs: completed/failed/retry/needsFramePrep)
conn['视频创建与状态路由'] = { main: [
  [{ node: '保存视频结果', type: 'main', index: 0 }],
  [{ node: '停止：视频失败', type: 'main', index: 0 }],
  [{ node: '等待视频重试', type: 'main', index: 0 }],
  [{ node: '准备视频参考帧尺寸', type: 'main', index: 0 }],
] };

// 准备视频参考帧尺寸 → 直接连 下载首帧 + 合并首帧上下文(input1)
// (跳过已删除的 生成视频参考帧尺寸 和 合并尺寸处理上下文)
conn['准备视频参考帧尺寸'] = { main: [[
  { node: '下载首帧', type: 'main', index: 0 },
  { node: '合并首帧上下文', type: 'main', index: 0 },
]] };
// 下载首帧 → 合并首帧上下文(input2)
conn['下载首帧'] = { main: [[{ node: '合并首帧上下文', type: 'main', index: 1 }]] };
// 合并首帧上下文 → 是否存在尾帧
conn['合并首帧上下文'] = { main: [[{ node: '是否存在尾帧', type: 'main', index: 0 }]] };

// 是否存在尾帧 (2 outputs: has tail / no tail)
conn['是否存在尾帧'] = { main: [
  [{ node: '下载尾帧', type: 'main', index: 0 }, { node: '合并尾帧上下文', type: 'main', index: 0 }],
  [{ node: '合并视频创建上下文', type: 'main', index: 0 }, { node: '创建视频任务：首帧', type: 'main', index: 0 }],
] };
conn['下载尾帧'] = { main: [[{ node: '合并尾帧上下文', type: 'main', index: 1 }]] };
conn['合并尾帧上下文'] = { main: [[
  { node: '合并视频创建上下文', type: 'main', index: 0 },
  { node: '创建视频任务：首尾帧', type: 'main', index: 0 },
]] };

// 创建视频任务 → 合并视频创建上下文(input2)
conn['创建视频任务：首帧'] = { main: [[{ node: '合并视频创建上下文', type: 'main', index: 1 }]] };
conn['创建视频任务：首尾帧'] = { main: [[{ node: '合并视频创建上下文', type: 'main', index: 1 }]] };
conn['合并视频创建上下文'] = { main: [[{ node: '轮询视频任务', type: 'main', index: 0 }]] };

// 轮询管线
conn['轮询视频任务'] = { main: [[{ node: '视频是否需要轮询', type: 'main', index: 0 }]] };
conn['视频是否需要轮询'] = { main: [
  [{ node: '视频创建与状态路由', type: 'main', index: 0 }],
  [{ node: '等待视频轮询', type: 'main', index: 0 }],
] };
conn['等待视频轮询'] = { main: [[{ node: '查询视频状态', type: 'main', index: 0 }]] };
conn['查询视频状态'] = { main: [[{ node: '解析视频轮询响应', type: 'main', index: 0 }]] };
conn['解析视频轮询响应'] = { main: [[{ node: '视频轮询是否继续', type: 'main', index: 0 }]] };
conn['视频轮询是否继续'] = { main: [
  [{ node: '等待视频轮询', type: 'main', index: 0 }],
  [{ node: '视频创建与状态路由', type: 'main', index: 0 }],
] };

// 重试/输出
conn['等待视频重试'] = { main: [[{ node: '准备视频参考帧尺寸', type: 'main', index: 0 }]] };
conn['保存视频结果'] = { main: [[{ node: '仅输出最终视频', type: 'main', index: 0 }]] };

// ── 6. 构建输出 ──
const simplified = {
  name: '简化版：仅首尾帧视频生成流程',
  nodes: workflow.nodes.map(n => {
    // 去掉 id 让 n8n 自动生成
    const { id, ...rest } = n;
    return { ...rest, id: require('crypto').randomUUID() };
  }),
  connections: conn,
  settings: workflow.settings || { executionOrder: 'v1' },
};

fs.writeFileSync(outPath, JSON.stringify(simplified, null, 2), 'utf8');
console.log('✅ 简化版工作流已写入:', outPath);
console.log('   节点数:', simplified.nodes.length, '(原始:', 30, ')');
