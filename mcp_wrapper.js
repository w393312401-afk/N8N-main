const { spawn, execSync } = require('child_process');
const net = require('net');
const path = require('path');

const PORT = 5678;
const HOST = '127.0.0.1';

// Function to check if port 5678 is listening
function checkPort() {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    socket.setTimeout(500);
    socket.on('connect', () => {
      socket.destroy();
      resolve(true);
    });
    socket.on('timeout', () => {
      socket.destroy();
      resolve(false);
    });
    socket.on('error', () => {
      resolve(false);
    });
    socket.connect(PORT, HOST);
  });
}

// Function to start N8N in the background detached
function startN8N() {
  const batPath = path.join(__dirname, '后台24小时运行N8N.bat');
  const command = `Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = 'cmd.exe /c "${batPath}" hidden' }`;
  const psPath = path.join(process.env.SystemRoot || 'C:\\Windows', 'System32\\WindowsPowerShell\\v1.0\\powershell.exe');
  
  const child = spawn(psPath, ['-NoProfile', '-Command', command], {
    stdio: 'ignore',
    windowsHide: true
  });
  child.on('error', (err) => {
    console.error('[MCP Wrapper] Failed to spawn powershell:', err);
  });
}

function isN8NProcessRunning() {
  try {
    const cmd = `powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \\"Name = 'node.exe' AND CommandLine LIKE '%n8n%'\\" | Select-Object -ExpandProperty ProcessId"`;
    const stdout = execSync(cmd, { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'] });
    const pids = stdout.trim().split(/\r?\n/).filter(Boolean);
    return pids.length > 0 ? pids : null;
  } catch (e) {
    return null;
  }
}

async function ensureN8N() {
  let isRunning = await checkPort();
  if (!isRunning) {
    const activePids = isN8NProcessRunning();
    if (activePids) {
      console.error(`[MCP Wrapper] N8N is not listening on port ${PORT}, but an N8N process is already running/booting (PID: ${activePids.join(', ')}).`);
    } else {
      console.error(`[MCP Wrapper] N8N is not running on port ${PORT}. Starting N8N in the background...`);
      startN8N();
    }
    
    console.error(`[MCP Wrapper] Waiting up to 3 seconds for N8N to become ready...`);
    const startTime = Date.now();
    while (Date.now() - startTime < 3000) {
      await new Promise((resolve) => setTimeout(resolve, 500));
      isRunning = await checkPort();
      if (isRunning) {
        console.error(`[MCP Wrapper] N8N is now ready.`);
        break;
      }
    }
    
    if (!isRunning) {
      console.error(`[MCP Wrapper] N8N is still booting. Proceeding to start supergateway...`);
    }
  }
  return true;
}

async function main() {
  const supergatewayPath = 'C:\\Users\\video\\Desktop\\node-v22.16.0-win-x64\\supergateway.cmd';
  
  // Forward all arguments to supergateway, quoting arguments with spaces for Windows cmd compatibility
  const args = process.argv.slice(2).map(arg => {
    if (arg.includes(' ') && !arg.startsWith('"') && !arg.endsWith('"')) {
      return `"${arg.replace(/"/g, '\\"')}"`;
    }
    return arg;
  });

  // Track if we should shut down (e.g. if parent closed stdin)
  let shouldExit = false;

  // Listen to stdin close to know when the IDE terminates us
  process.stdin.on('close', () => {
    console.error('[MCP Wrapper] Stdin closed. Shutting down wrapper...');
    shouldExit = true;
    process.exit(0);
  });

  while (!shouldExit) {
    const ready = await ensureN8N();
    if (!ready) {
      // If N8N fails to start, wait 10s and retry
      console.error('[MCP Wrapper] N8N start failed. Retrying in 10 seconds...');
      await new Promise((resolve) => setTimeout(resolve, 10000));
      continue;
    }

    console.error('[MCP Wrapper] Starting supergateway...');
    
    const gateway = spawn(supergatewayPath, args, {
      stdio: 'inherit',
      windowsHide: true,
      shell: true
    });

    // Wait for gateway process to exit
    await new Promise((resolve) => {
      gateway.on('exit', (code) => {
        console.error(`[MCP Wrapper] Supergateway process exited with code ${code}.`);
        resolve();
      });
      gateway.on('error', (err) => {
        console.error('[MCP Wrapper] Supergateway process error:', err);
        resolve();
      });
    });

    if (shouldExit) {
      break;
    }

    console.error('[MCP Wrapper] Supergateway exited unexpectedly. Reconnecting in 5 seconds...');
    await new Promise((resolve) => setTimeout(resolve, 5000));
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
