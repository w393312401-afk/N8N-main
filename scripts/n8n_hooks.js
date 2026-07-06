const http = require('http');

const FLOW2API_WORKFLOW_LIFECYCLE_DISABLED = true;

function logIgnoredLifecycle(phase, workflowData) {
  if (!FLOW2API_WORKFLOW_LIFECYCLE_DISABLED || !workflowData) return;
  console.log(
    `[n8n Hooks] ${phase} ignored flow2api lifecycle: ${workflowData.name || ''} (${workflowData.id || ''})`,
  );
}

function sendCancelTask() {
  console.log(`[n8n Hooks] Sending POST request to http://127.0.0.1:8000/cancel_task...`);
  const req = http.request({
    hostname: '127.0.0.1',
    port: 8000,
    path: '/cancel_task',
    method: 'POST',
    headers: {
      'Content-Length': 0
    }
  }, (res) => {
    let data = '';
    res.on('data', chunk => data += chunk);
    res.on('end', () => {
      console.log(`[n8n Hooks] /cancel_task API response: ${res.statusCode} - ${data}`);
    });
  });

  req.on('error', (err) => {
    console.error(`[n8n Hooks] Failed to call /cancel_task API: ${err.message}`);
  });

  req.end();
}

module.exports = {
  workflow: {
    preExecute: [
      async function (workflowData) {
        logIgnoredLifecycle('preExecute', workflowData);
      },
    ],
    postExecute: [
      async function (run, workflowData) {
        logIgnoredLifecycle('postExecute', workflowData);
        if (workflowData) {
          const wId = workflowData.id;
          const wName = workflowData.name;
          const runStatus = run ? run.status : 'unknown';
          console.log(`[n8n Hooks] postExecute hook triggered: workflowName="${wName}", workflowId="${wId}", status="${runStatus}"`);
          
          const isTargetWorkflow = wId === '1eKIJgTQuvKLm4jVpxo4O' || wName === 'ADS指纹浏览器-flow- UI自动化';
          if (isTargetWorkflow && runStatus !== 'success') {
            console.log(`[n8n Hooks] Target workflow stopped/failed/canceled (status: ${runStatus}). Triggering backend browser cancellation.`);
            sendCancelTask();
          }
        }
      },
    ],
  },
};
