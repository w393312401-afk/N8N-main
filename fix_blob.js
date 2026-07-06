/**
 * 修复 n8n Code 节点中 Blob is not defined 错误
 * 将 new Blob([bytes], {...}) 替换为直接 Buffer 方式
 * 
 * n8n 沙箱中 FormData 支持 Buffer，不支持 Blob
 */
const fs = require('fs');
const path = require('path');

const API_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkODA1MWRiZC1lOWUxLTRhZjktOWExMy01ZGU4MWNhMzY3MWYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiMDczODI0OTUtN2Y0NS00MmE4LTg3ZWItZTU0YzU0ZmQ3NzA1IiwiaWF0IjoxNzc5MTY4NTMxfQ.STcFcbOEConsW4spsUrEkfqphKfwqMUib6pzQ8lwZcw';
const BASE = 'http://127.0.0.1:5678/api/v1';

// 修复后的 appendReference 函数 — 用 Buffer 替代 Blob
const FIXED_APPEND_FN = `async function appendReference(form, source, fileName) {
  const bytes = await readBytes(source);
  const name = pick(fileName, path.basename(pick(source)) || 'reference.png');
  const mime = mimeFromPath(name || source);
  // n8n Code 节点沙箱没有 Blob，使用 Buffer + File polyfill
  if (typeof File !== 'undefined') {
    form.append('input_reference', new File([bytes], name, { type: mime }), name);
  } else {
    // 降级: 直接用 Buffer，手动设置 content-disposition
    const buf = Buffer.isBuffer(bytes) ? bytes : Buffer.from(bytes);
    buf.name = name;
    buf.type = mime;
    form.append('input_reference', buf, { filename: name, contentType: mime });
  }
}`;

async function fixWorkflow(workflowId) {
  // 1. 获取当前工作流
  const getRes = await fetch(`${BASE}/workflows/${workflowId}`, {
    headers: { 'X-N8N-API-KEY': API_KEY }
  });
  if (!getRes.ok) throw new Error('GET failed: ' + getRes.status + ' ' + await getRes.text());
  const workflow = await getRes.json();
  
  let fixCount = 0;
  
  // 2. 修复两个视频创建节点
  for (const node of workflow.nodes) {
    if (node.name === '创建视频任务：首尾帧' || node.name === '创建视频任务：首帧') {
      const code = node.parameters.jsCode;
      if (!code) continue;
      
      // 替换整个 appendReference 函数
      const pattern = /async function appendReference\(form, source, fileName\)\s*\{[^}]*new Blob[^}]*\}/s;
      if (pattern.test(code)) {
        node.parameters.jsCode = code.replace(pattern, FIXED_APPEND_FN);
        fixCount++;
        console.log(`✅ 已修复: ${node.name}`);
      } else {
        console.log(`⚠️ 未匹配到 Blob 模式: ${node.name}`);
        // 尝试简单替换
        if (code.includes('new Blob(')) {
          node.parameters.jsCode = code.replace(
            /new Blob\(\[bytes\],\s*\{[^}]+\}\)/g,
            'Buffer.isBuffer(bytes) ? bytes : Buffer.from(bytes)'
          );
          fixCount++;
          console.log(`✅ 已通过简单替换修复: ${node.name}`);
        }
      }
    }
  }
  
  if (fixCount === 0) {
    console.log('❌ 没有找到需要修复的节点');
    return;
  }
  
  // 3. 推送修复
  const updateBody = JSON.stringify({
    name: workflow.name,
    nodes: workflow.nodes,
    connections: workflow.connections,
    settings: { executionOrder: 'v1' },
  });
  
  const putRes = await fetch(`${BASE}/workflows/${workflowId}`, {
    method: 'PUT',
    headers: {
      'X-N8N-API-KEY': API_KEY,
      'Content-Type': 'application/json',
    },
    body: updateBody,
  });
  
  if (!putRes.ok) {
    const errText = await putRes.text();
    throw new Error('PUT failed: ' + putRes.status + ' ' + errText);
  }
  
  const result = await putRes.json();
  console.log(`\n🎉 工作流 ${workflowId} 已更新 (version: ${result.versionId})`);
  console.log(`   修复了 ${fixCount} 个节点的 Blob 问题`);
}

// 修复简化版工作流
fixWorkflow('3BS5NW3ZAiC7VeJH')
  .then(() => {
    // 同时修复原工作流
    console.log('\n--- 同时修复原工作流 ---');
    return fixWorkflow('mQWN2HbXuuXXYbxU');
  })
  .catch(err => console.error('❌ Error:', err.message));
