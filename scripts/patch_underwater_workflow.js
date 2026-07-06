const fs = require('fs');
const path = require('path');
const sqlite3 = require('C:/Users/FLY/Desktop/node-v22.16.0-win-x64/node_modules/n8n/node_modules/sqlite3');

const workflowId = '13CnpyRAeEwAyv5D';
const dbPath = 'C:/Users/FLY/.n8n/database.sqlite';
const backupDir = 'C:/Users/FLY/Desktop/N8N-main/workflows';

const nodeNames = {
  imageSummary: '\u6c47\u603b\u56fe\u7247\u7ed3\u679c',
  buildVideoTask: '\u6784\u5efa\u89c6\u9891\u4efb\u52a1',
};

const imageSummaryCode = String.raw`const fs = require('fs');
const parsed = $('\u89e3\u6790\u4efb\u52a1').first().json;
const jobs = $items('\u6784\u5efa\u751f\u56fe\u4efb\u52a1')
  .map((item) => item.json || {})
  .sort((a, b) => (a.stepIndex || 0) - (b.stepIndex || 0));

if (!jobs.length) throw new Error('\u56fe\u7247\u9636\u6bb5\u6ca1\u6709\u4efb\u4f55\u751f\u56fe\u4efb\u52a1');

const extractedByStep = new Map(
  $items('\u63d0\u53d6\u56fe\u7247\u6587\u4ef6')
    .map((item) => item.json || {})
    .filter((item) => item.stepIndex !== undefined)
    .map((item) => [Number(item.stepIndex), item]),
);

const results = jobs.map((job) => {
  const stepIndex = Number(job.stepIndex || 0);
  const outputPath = job.outputPath || '';
  const exists = Boolean(outputPath && fs.existsSync(outputPath));
  const extracted = extractedByStep.get(stepIndex) || {};
  return {
    stepIndex,
    stepLabel: job.stepLabel || '',
    outputPath,
    imageOk: exists,
    imageError: exists ? '' : (extracted.imageError || '\u56fe\u7247\u6587\u4ef6\u672a\u751f\u6210'),
  };
});

const success = results.filter((item) => item.imageOk);
const failed = results.filter((item) => !item.imageOk);

return [{
  json: {
    ...parsed,
    imageResults: success,
    imageFailures: failed,
    imageAttemptCount: results.length,
    imageSuccessCount: success.length,
    image1Path: success.find((item) => item.stepIndex === 1)?.outputPath || '',
    image2Path: success.find((item) => item.stepIndex === 2)?.outputPath || '',
  },
}];`;

const buildVideoTaskCode = String.raw`const base = $('\u6c47\u603b\u56fe\u7247\u7ed3\u679c').first().json;
const cfg = base.config;
const lines = String(base.promptPacked || '').split('\n');
const sections = [];
let current = null;

const flush = () => {
  if (current && current.body.length) {
    sections.push({ ...current, block: current.body.join('\n').trim() });
  }
};

for (const rawLine of lines) {
  const trimmed = rawLine.trim();
  const normalizedHeading = trimmed.replace(/^[^A-Za-z0-9]+/, '');
  const imageMatch = normalizedHeading.match(/^(Image\s+\d+)/i);
  const videoMatch = normalizedHeading.match(/^(Video\s+\d+)/i);
  if (imageMatch || videoMatch) {
    flush();
    current = null;
    if (videoMatch) {
      const normalized = videoMatch[1].replace(/\s+/g, ' ').trim();
      const indexMatch = normalized.match(/(\d+)/);
      current = {
        label: normalized.toUpperCase(),
        stepIndex: indexMatch ? Number(indexMatch[1]) : (sections.length + 1),
        body: [],
      };
    }
    continue;
  }
  if (current) current.body.push(rawLine);
}

flush();

const videos = sections
  .filter((section) => section.block)
  .sort((a, b) => (a.stepIndex || 0) - (b.stepIndex || 0));

const referenceImage = cfg.videoImageSource === 'image2' ? base.image2Path : base.image1Path;
const shouldGenerateVideo = Boolean(cfg.videoEnabled && videos.length && referenceImage);

if (!shouldGenerateVideo) {
  return [{
    json: {
      ...base,
      videoEnabled: Boolean(cfg.videoEnabled),
      shouldGenerateVideo: false,
      videoPromptCount: videos.length,
      videoTasks: [],
      videoReason: !cfg.videoEnabled
        ? '\u89c6\u9891\u80fd\u529b\u5df2\u5173\u95ed'
        : (!videos.length ? '\u672a\u89e3\u6790\u5230 Video \u5206\u955c' : '\u7f3a\u5c11\u89c6\u9891\u53c2\u8003\u56fe'),
    },
  }];
}

return videos.map((section) => ({
  json: {
    ...base,
    videoEnabled: true,
    shouldGenerateVideo: true,
    videoPromptCount: videos.length,
    videoIndex: section.stepIndex,
    videoLabel: section.label,
    videoPrompt: section.block,
    videoReferenceImage: referenceImage,
    videoReason: 'ready',
  },
}));`;

function updateWorkflow() {
  const db = new sqlite3.Database(dbPath);
  db.get('SELECT nodes, connections FROM workflow_entity WHERE id = ?', [workflowId], (err, row) => {
    if (err) throw err;
    if (!row) throw new Error(`Workflow not found: ${workflowId}`);

    const nodes = JSON.parse(row.nodes);
    const workflowBackupPath = path.join(backupDir, `${workflowId}.debug-backup.json`);
    fs.writeFileSync(
      workflowBackupPath,
      JSON.stringify({ id: workflowId, nodes, connections: JSON.parse(row.connections) }, null, 2),
      'utf8',
    );

    const imageSummaryNode = nodes.find((node) => node.name === nodeNames.imageSummary);
    const buildVideoTaskNode = nodes.find((node) => node.name === nodeNames.buildVideoTask);

    if (!imageSummaryNode || !buildVideoTaskNode) {
      throw new Error('Required workflow nodes not found');
    }

    imageSummaryNode.parameters.jsCode = imageSummaryCode;
    buildVideoTaskNode.parameters.jsCode = buildVideoTaskCode;

    db.run(
      'UPDATE workflow_entity SET nodes = ?, updatedAt = CURRENT_TIMESTAMP WHERE id = ?',
      [JSON.stringify(nodes), workflowId],
      (updateErr) => {
        if (updateErr) throw updateErr;
        console.log(JSON.stringify({
          workflowId,
          backup: workflowBackupPath,
          updated: [nodeNames.imageSummary, nodeNames.buildVideoTask],
        }, null, 2));
        db.close();
      },
    );
  });
}

updateWorkflow();
