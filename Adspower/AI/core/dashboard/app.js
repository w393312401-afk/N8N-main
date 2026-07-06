/* ==============================================================================
   ⚙️ Google FX Studio - Dashboard Application Logic (ES Modules)
   ============================================================================== */

const API_BASE = window.location.origin;

// 1. 全局状态存储
const state = {
    activeTab: 'tab-pane-video',
    adspowerOnline: false,
    profiles: [],
    selectedProfile: '',
    isGenerating: false,
    uploadedStartFrame: '',
    uploadedEndFrame: '',
    uploadedRefImages: [], // 批量图片生成的参考图列表 (路径数组)
    mergeQueue: [], // { id, name, path, url }
    lastLogCount: 0,
    logPollingInterval: null,
};

// 2. DOM 元素选择器
const dom = {
    // 侧边栏与环境
    adspowerStatusDot: document.getElementById('adspower-status-dot'),
    adspowerStatusText: document.getElementById('adspower-status-text'),
    envProfileSelect: document.getElementById('env-profile-select'),
    btnForceRotateProxy: document.getElementById('btn-force-rotate-proxy'),
    navItems: document.querySelectorAll('.nav-item'),
    tabPanes: document.querySelectorAll('.tab-pane'),
    currentPaneTitle: document.getElementById('current-pane-title'),
    activeTaskBadge: document.getElementById('active-task-badge'),
    activeTaskText: document.getElementById('active-task-text'),
    btnCancelTask: document.getElementById('btn-cancel-task'),

    // 视频生成表单
    videoForm: document.getElementById('video-generator-form'),
    videoPromptInput: document.getElementById('video-prompt-input'),
    videoOutputPath: document.getElementById('video-output-path'),
    slotStartFrame: document.getElementById('slot-start-frame'),
    inputStartFrame: document.getElementById('input-start-frame'),
    previewStartFrame: document.getElementById('preview-start-frame'),
    filenameStartFrame: document.getElementById('filename-start-frame'),
    btnRemoveStartFrame: document.getElementById('btn-remove-start-frame'),
    slotEndFrame: document.getElementById('slot-end-frame'),
    inputEndFrame: document.getElementById('input-end-frame'),
    previewEndFrame: document.getElementById('preview-end-frame'),
    filenameEndFrame: document.getElementById('filename-end-frame'),
    btnRemoveEndFrame: document.getElementById('btn-remove-end-frame'),
    videoModelGroup: document.getElementById('video-model-group'),
    videoRatioGroup: document.getElementById('video-ratio-group'),
    videoDurationGroup: document.getElementById('video-duration-group'),
    btnSubmitVideo: document.getElementById('btn-submit-video'),

    // 图片生成表单
    imageForm: document.getElementById('image-generator-form'),
    imagePromptsInput: document.getElementById('image-prompts-input'),
    imageOutputPath: document.getElementById('image-output-path'),
    slotRefImages: document.getElementById('slot-ref-images'),
    inputRefImages: document.getElementById('input-ref-images'),
    imageMultiPreviews: document.getElementById('image-multi-previews'),
    imageModelGroup: document.getElementById('image-model-group'),
    imageRatioGroup: document.getElementById('image-ratio-group'),
    btnSubmitImage: document.getElementById('btn-submit-image'),

    // 媒体库与 FFmpeg
    ffmpegWorkspace: document.getElementById('ffmpeg-merge-workspace'),
    mergeCountBadge: document.getElementById('merge-count-badge'),
    mergeEmptyTip: document.getElementById('merge-empty-tip'),
    mergeSlotsList: document.getElementById('merge-slots-list'),
    mergeControlsPanel: document.getElementById('merge-controls-panel'),
    mergeSpeedSlider: document.getElementById('merge-speed-slider'),
    labelSpeedVal: document.getElementById('label-speed-val'),
    mergeOutputName: document.getElementById('merge-output-name'),
    btnExecuteMerge: document.getElementById('btn-execute-merge'),
    galleryDirInput: document.getElementById('gallery-dir-input'),
    btnRefreshGallery: document.getElementById('btn-refresh-gallery'),
    galleryGrid: document.getElementById('gallery-grid'),

    // 终端日志
    progressTaskName: document.getElementById('progress-task-name'),
    progressTaskPercent: document.getElementById('progress-task-percent'),
    progressBarFill: document.getElementById('progress-bar-fill'),
    terminalLogOutput: document.getElementById('terminal-log-output'),
    btnClearTerminal: document.getElementById('btn-clear-terminal'),

    // 模态播放器
    videoLightbox: document.getElementById('video-lightbox'),
    lightboxVideoPlayer: document.getElementById('lightbox-video-player'),
    lightboxVideoTitle: document.getElementById('lightbox-video-title'),
    lightboxVideoPath: document.getElementById('lightbox-video-path'),
    btnLightboxDownload: document.getElementById('btn-lightbox-download'),
    btnCloseLightbox: document.getElementById('btn-close-lightbox'),

    // 📖 故事脚本流
    scriptForm: document.getElementById('script-flow-form'),
    scriptFlowInput: document.getElementById('script-flow-input'),
    scriptProjectName: document.getElementById('script-project-name'),
    scriptOutputPath: document.getElementById('script-output-path'),
    scriptMergeSpeed: document.getElementById('script-merge-speed'),
    scriptImageModel: document.getElementById('script-image-model'),
    scriptVideoModel: document.getElementById('script-video-model'),
    scriptVideoRatio: document.getElementById('script-video-ratio'),
    scriptVideoDuration: document.getElementById('script-video-duration'),
    btnLoadScriptDemo: document.getElementById('btn-load-script-demo'),
    btnSubmitScriptFlow: document.getElementById('btn-submit-script-flow'),
    pipelineStatusPanel: document.getElementById('pipeline-status-panel'),
    pipelineStepText: document.getElementById('pipeline-step-text'),
    pipelinePercentText: document.getElementById('pipeline-percent-text'),
    pipelineProgressBar: document.getElementById('pipeline-progress-bar'),
    pipelineImagesList: document.getElementById('pipeline-images-list'),
    pipelineVideosList: document.getElementById('pipeline-videos-list'),
    pipelineResultBox: document.getElementById('pipeline-result-box'),
    pipelineResultFilename: document.getElementById('pipeline-result-filename'),
    btnPlayPipelineResult: document.getElementById('btn-play-pipeline-result'),
    btnDownloadPipelineResult: document.getElementById('btn-download-pipeline-result'),
};

// ==============================================================================
// 3. 初始化加载
// ==============================================================================
document.addEventListener('DOMContentLoaded', () => {
    initTabNavigation();
    checkEnvironments();
    initVideoFormHandlers();
    initImageFormHandlers();
    initScriptFlowHandlers();
    initGalleryHandlers();
    initTerminalHandlers();
    initLightboxHandlers();
    
    // 自动刷新媒体库和日志轮询
    refreshGallery();
    startLogPolling();
});

// ==============================================================================
// 4. 侧边栏及导航切换
// ==============================================================================
function initTabNavigation() {
    dom.navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            const targetPaneId = e.currentTarget.getAttribute('data-target');
            
            // 切换按钮高亮
            dom.navItems.forEach(nav => nav.classList.remove('active'));
            e.currentTarget.classList.add('active');
            
            // 切换显示标签页
            dom.tabPanes.forEach(pane => pane.classList.remove('active'));
            const activePane = document.getElementById(targetPaneId);
            activePane.classList.add('active');
            
            // 更新标题
            const tabTitleMap = {
                'tab-pane-video': 'Veo 视频生成控制台',
                'tab-pane-image': 'Imagen / Nano Banana 图片批量生成',
                'tab-pane-script-flow': '故事脚本流自动生成',
                'tab-pane-gallery': '灵感媒体库与合并工坊',
                'tab-pane-logs': '实时系统监控日志终端',
            };
            dom.currentPaneTitle.textContent = tabTitleMap[targetPaneId] || 'Google FX Studio';
            state.activeTab = targetPaneId;
        });
    });

    // 终止按钮绑定
    dom.btnCancelTask.addEventListener('click', async () => {
        if (!confirm('确定要强行终止正在运行的任务并关闭浏览器环境吗？')) return;
        appendSystemLog('🚨 正在发送终止任务信号...');
        try {
            const res = await fetch(`${API_BASE}/cancel_task`, { method: 'POST' });
            const data = await res.json();
            appendSystemLog(`🛑 任务终止结果: ${data.message || JSON.stringify(data)}`, 'system');
            setGeneratingState(false);
        } catch (e) {
            appendSystemLog(`❌ 终止命令发送异常: ${e.message}`, 'error');
        }
    });
}

// 获取浏览器环境列表与运行状态
async function checkEnvironments() {
    try {
        const res = await fetch(`${API_BASE}/environments`);
        if (!res.ok) throw new Error('API Error');
        const data = await res.json();
        
        state.adspowerOnline = true;
        dom.adspowerStatusDot.className = 'status-dot online';
        dom.adspowerStatusText.textContent = `AdsPower 在线 (可用环境: ${data.total})`;
        
        // 渲染下拉列表
        state.profiles = data.environments || [];
        dom.envProfileSelect.innerHTML = '<option value="">-- 使用配置默认环境 --</option>';
        state.profiles.forEach(p => {
            const option = document.createElement('option');
            option.value = p.user_id;
            option.textContent = `${p.serial_number} | ${p.name || '未命名'} (${p.user_id})`;
            dom.envProfileSelect.appendChild(option);
        });
    } catch (e) {
        state.adspowerOnline = false;
        dom.adspowerStatusDot.className = 'status-dot';
        dom.adspowerStatusText.textContent = 'AdsPower API 未连接 (请启动 AdsPower 本地客户端)';
    }

    // 强制换 IP 按钮绑定
    dom.btnForceRotateProxy.addEventListener('click', async () => {
        dom.btnForceRotateProxy.disabled = true;
        appendSystemLog('🔄 正在强制轮换住宅代理 IP，请稍候...', 'system');
        try {
            const res = await fetch(`${API_BASE}/rotate_proxy`, { method: 'POST' });
            const data = await res.json();
            if (data.status === 'success') {
                appendSystemLog('✅ 代理 IP 轮换完成', 'success');
                alert('代理 IP 轮换成功！');
            } else {
                appendSystemLog(`⚠️ 轮换跳过或失败: ${data.message}`, 'error');
                alert(`代理轮换未成功: ${data.message}`);
            }
        } catch (e) {
            appendSystemLog(`❌ 轮换代理接口请求失败: ${e.message}`, 'error');
        } finally {
            dom.btnForceRotateProxy.disabled = false;
        }
    });
}

// 设置生成任务的活动状态 UI 绑定
function setGeneratingState(isGenerating, taskText = '正在运行生成任务...') {
    state.isGenerating = isGenerating;
    if (isGenerating) {
        dom.activeTaskBadge.style.display = 'flex';
        dom.activeTaskText.textContent = taskText;
        dom.btnSubmitVideo.disabled = true;
        dom.btnSubmitImage.disabled = true;
        if (dom.btnSubmitScriptFlow) dom.btnSubmitScriptFlow.disabled = true;
    } else {
        dom.activeTaskBadge.style.display = 'none';
        dom.btnSubmitVideo.disabled = false;
        dom.btnSubmitImage.disabled = false;
        if (dom.btnSubmitScriptFlow) dom.btnSubmitScriptFlow.disabled = false;
    }
}

// ==============================================================================
// 5. 视频生成逻辑 (首尾帧拖拽上传)
// ==============================================================================
function initVideoFormHandlers() {
    // 绑定参数卡片单选点击
    bindRadioCards('video-model-group');
    bindRatioButtons('video-ratio-group');
    bindDurationButtons('video-duration-group');

    // 双参考图槽位事件绑定 (点击触发 file select, 支持拖放)
    setupDragDropSlot(dom.slotStartFrame, dom.inputStartFrame, (filePath) => {
        state.uploadedStartFrame = filePath;
        showPreview(dom.slotStartFrame, dom.previewStartFrame, dom.filenameStartFrame, filePath);
    });
    
    setupDragDropSlot(dom.slotEndFrame, dom.inputEndFrame, (filePath) => {
        state.uploadedEndFrame = filePath;
        showPreview(dom.slotEndFrame, dom.previewEndFrame, dom.filenameEndFrame, filePath);
    });

    // 移除图片绑定
    dom.btnRemoveStartFrame.addEventListener('click', (e) => {
        e.stopPropagation();
        state.uploadedStartFrame = '';
        hidePreview(dom.slotStartFrame, dom.inputStartFrame);
    });

    dom.btnRemoveEndFrame.addEventListener('click', (e) => {
        e.stopPropagation();
        state.uploadedEndFrame = '';
        hidePreview(dom.slotEndFrame, dom.inputEndFrame);
    });

    // 提交视频生成任务
    dom.videoForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (state.isGenerating) return;

        const prompt = dom.videoPromptInput.value.trim();
        const model = getSelectedRadioValue('video-model-group');
        const ratio = getSelectedRadioValue('video-ratio-group');
        const duration = getSelectedRadioValue('video-duration-group');
        const outputPath = dom.videoOutputPath.value.trim();

        // 验证首尾帧规则
        if (state.uploadedEndFrame && !state.uploadedStartFrame) {
            alert('要配置尾帧，您必须同时配置首帧！');
            return;
        }

        const payload = {
            prompt,
            model,
            ratio,
            duration,
            image: state.uploadedStartFrame,
            end_image: state.uploadedEndFrame,
            output_path: outputPath
        };

        // 切换到日志终端
        document.getElementById('nav-tab-logs').click();
        setGeneratingState(true, 'Veo 视频生成中...');
        appendSystemLog(`🚀 视频生成任务已提交: Model="${model}", Ratio="${ratio}", Duration="${duration}"`, 'system');
        appendSystemLog(`💬 提示词: ${prompt}`);

        try {
            const res = await fetch(`${API_BASE}/generate_video`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (res.ok && data.status !== 'failed') {
                appendSystemLog(`🎉 视频生成成功！资源地址: ${data.video_url || '请查看 manifest'}`, 'success');
                // 自动刷新媒体库
                refreshGallery();
                alert('视频生成成功！');
            } else {
                appendSystemLog(`❌ 生成失败: ${data.detail || data.message || '未知错误'}`, 'error');
                alert(`视频生成失败: ${data.detail || data.message || '查看控制台日志'}`);
            }
        } catch (err) {
            appendSystemLog(`❌ 后端通信异常: ${err.message}`, 'error');
        } finally {
            setGeneratingState(false);
        }
    });
}

// 辅助方法：多槽位单选/属性获取
function bindRadioCards(groupId) {
    const group = document.getElementById(groupId);
    const cards = group.querySelectorAll('.radio-card');
    cards.forEach(card => {
        card.addEventListener('click', () => {
            cards.forEach(c => c.classList.remove('active'));
            card.classList.add('active');
        });
    });
}

function bindRatioButtons(groupId) {
    const group = document.getElementById(groupId);
    const btns = group.querySelectorAll('.btn-ratio');
    btns.forEach(btn => {
        btn.addEventListener('click', () => {
            btns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });
}

function bindDurationButtons(groupId) {
    const group = document.getElementById(groupId);
    const btns = group.querySelectorAll('.btn-duration');
    btns.forEach(btn => {
        btn.addEventListener('click', () => {
            btns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });
}

function getSelectedRadioValue(groupId) {
    const group = document.getElementById(groupId);
    const active = group.querySelector('.radio-card.active, .btn-ratio.active, .btn-duration.active');
    return active ? active.getAttribute('data-value') : null;
}

// 辅助方法：设置拖拽与点击上传
function setupDragDropSlot(slotEl, inputEl, callback) {
    slotEl.addEventListener('click', () => inputEl.click());
    
    slotEl.addEventListener('dragover', (e) => {
        e.preventDefault();
        slotEl.style.borderColor = 'var(--color-primary)';
        slotEl.style.background = 'rgba(139, 92, 246, 0.08)';
    });

    slotEl.addEventListener('dragleave', () => {
        slotEl.style.borderColor = '';
        slotEl.style.background = '';
    });

    slotEl.addEventListener('drop', async (e) => {
        e.preventDefault();
        slotEl.style.borderColor = '';
        slotEl.style.background = '';
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            await handleFileUpload(files[0], slotEl, callback);
        }
    });

    inputEl.addEventListener('change', async (e) => {
        const files = e.target.files;
        if (files.length > 0) {
            await handleFileUpload(files[0], slotEl, callback);
        }
    });
}

// 执行接口文件上传
async function handleFileUpload(file, slotEl, callback) {
    const formData = new FormData();
    formData.append('file', file);
    
    // 显示上传中状态
    const placeholder = slotEl.querySelector('.slot-placeholder');
    const originalContent = placeholder.innerHTML;
    placeholder.innerHTML = `<span class="spinner" style="width:24px; height:24px; margin-bottom: 8px;"></span><h4>正在上传到服务器...</h4>`;

    try {
        const res = await fetch(`${API_BASE}/upload`, {
            method: 'POST',
            body: formData
        });
        if (!res.ok) throw new Error('Upload server error');
        const data = await res.json();
        
        appendSystemLog(`📸 成功上传参考图: ${file.name} -> 保存至: ${data.file_path}`, 'system');
        callback(data.file_path);
    } catch (e) {
        appendSystemLog(`❌ 图片上传失败: ${e.message}`, 'error');
        alert('文件上传失败，请检查后端服务连接');
        placeholder.innerHTML = originalContent;
    }
}

function showPreview(slotEl, imgEl, nameEl, filePath) {
    slotEl.querySelector('.slot-placeholder').style.display = 'none';
    const preview = slotEl.querySelector('.slot-preview');
    preview.style.display = 'block';
    
    // 由于后端把图片保存在了 media/temp_uploads 里，我们拼成前端访问路径
    // 如果是绝对路径，解析出文件名以渲染预览图
    const filename = filePath.split(/[/\\]/).pop();
    imgEl.src = `/media/temp_uploads/${filename}`;
    nameEl.textContent = filename;
}

function hidePreview(slotEl, inputEl) {
    slotEl.querySelector('.slot-placeholder').style.display = 'block';
    slotEl.querySelector('.slot-preview').style.display = 'none';
    inputEl.value = '';
}

// ==============================================================================
// 6. 图片批量生成逻辑
// ==============================================================================
function initImageFormHandlers() {
    bindRadioCards('image-model-group');
    bindRatioButtons('image-ratio-group');

    // 图片批量生成的参考图上传 (多图)
    dom.slotRefImages.addEventListener('click', (e) => {
        if (e.target.closest('.thumb-remove')) return; // 防止删除按钮冒泡
        dom.inputRefImages.click();
    });

    dom.slotRefImages.addEventListener('dragover', (e) => {
        e.preventDefault();
        dom.slotRefImages.style.borderColor = 'var(--color-primary)';
    });

    dom.slotRefImages.addEventListener('dragleave', () => {
        dom.slotRefImages.style.borderColor = '';
    });

    dom.slotRefImages.addEventListener('drop', async (e) => {
        e.preventDefault();
        dom.slotRefImages.style.borderColor = '';
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            for (let file of files) {
                await handleImageBatchUpload(file);
            }
        }
    });

    dom.inputRefImages.addEventListener('change', async (e) => {
        const files = e.target.files;
        if (files.length > 0) {
            for (let file of files) {
                await handleImageBatchUpload(file);
            }
        }
    });

    async function handleImageBatchUpload(file) {
        const formData = new FormData();
        formData.append('file', file);
        try {
            const res = await fetch(`${API_BASE}/upload`, { method: 'POST', body: formData });
            const data = await res.json();
            
            state.uploadedRefImages.push(data.file_path);
            renderMultiPreviews();
        } catch (err) {
            appendSystemLog(`❌ 图片批量上传失败: ${err.message}`, 'error');
        }
    }

    function renderMultiPreviews() {
        if (state.uploadedRefImages.length === 0) {
            dom.slotRefImages.querySelector('.slot-placeholder').style.display = 'block';
            dom.imageMultiPreviews.style.display = 'none';
            return;
        }

        dom.slotRefImages.querySelector('.slot-placeholder').style.display = 'none';
        dom.imageMultiPreviews.style.display = 'grid';
        dom.imageMultiPreviews.innerHTML = '';

        state.uploadedRefImages.forEach((path, idx) => {
            const filename = path.split(/[/\\]/).pop();
            const thumb = document.createElement('div');
            thumb.className = 'preview-thumb';
            thumb.innerHTML = `
                <img src="/media/temp_uploads/${filename}">
                <button type="button" class="thumb-remove" data-index="${idx}">
                    <span class="material-symbols-outlined">close</span>
                </button>
            `;
            dom.imageMultiPreviews.appendChild(thumb);
        });

        // 绑定删除按钮
        dom.imageMultiPreviews.querySelectorAll('.thumb-remove').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const idx = parseInt(btn.getAttribute('data-index'));
                state.uploadedRefImages.splice(idx, 1);
                renderMultiPreviews();
            });
        });
    }

    // 提交图片批量生成
    dom.imageForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (state.isGenerating) return;

        const rawPrompts = dom.imagePromptsInput.value.trim();
        const prompts = rawPrompts.split('\n').map(p => p.trim()).filter(p => p.length > 0);
        if (prompts.length === 0) return;

        const model = getSelectedRadioValue('image-model-group');
        const ratio = getSelectedRadioValue('image-ratio-group');
        const outputPath = dom.imageOutputPath.value.trim();

        const payload = {
            prompts,
            images: state.uploadedRefImages,
            ratio,
            model,
            output_path: outputPath
        };

        document.getElementById('nav-tab-logs').click();
        setGeneratingState(true, 'Imagen 图片绘制中...');
        appendSystemLog(`🚀 图片批量绘制任务已提交: Model="${model}", Ratio="${ratio}", 数量=${prompts.length}`, 'system');

        try {
            const res = await fetch(`${API_BASE}/generate_images_batch`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (res.ok && data.status !== 'failed') {
                appendSystemLog(`🎉 图片批量绘制成功！共完成 ${data.success_count || prompts.length} 张图片`, 'success');
                refreshGallery();
                alert('图片生成成功！');
            } else {
                appendSystemLog(`❌ 绘制失败: ${data.detail || data.message || '未知错误'}`, 'error');
                alert(`图片绘制失败: ${data.detail || data.message}`);
            }
        } catch (err) {
            appendSystemLog(`❌ 后端通信异常: ${err.message}`, 'error');
        } finally {
            setGeneratingState(false);
        }
    });
}

// ==============================================================================
// 7. 媒体库管理与 FFmpeg 合并工坊
// ==============================================================================
function initGalleryHandlers() {
    dom.btnRefreshGallery.addEventListener('click', () => refreshGallery());

    // 调速滑块实时更新
    dom.mergeSpeedSlider.addEventListener('input', (e) => {
        dom.labelSpeedVal.textContent = `${parseFloat(e.target.value).toFixed(1)}x`;
    });

    // 执行合并
    dom.btnExecuteMerge.addEventListener('click', async () => {
        if (state.mergeQueue.length === 0) return;
        
        const outputFilename = dom.mergeOutputName.value.trim();
        const speed = parseFloat(dom.mergeSpeedSlider.value);
        const videoPaths = state.mergeQueue.map(item => item.path);

        const payload = {
            video_paths: videoPaths,
            output_filename: outputFilename,
            speed
        };

        dom.btnExecuteMerge.disabled = true;
        appendSystemLog(`⚙️ 正在执行 FFmpeg 视频合并: 片段数=${videoPaths.length}, 调速=${speed}x`, 'system');

        try {
            const res = await fetch(`${API_BASE}/merge_videos`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (res.ok && data.status === 'success') {
                appendSystemLog(`✅ 视频合并成功！输出文件: ${data.output_path}`, 'success');
                // 重置工作台
                state.mergeQueue = [];
                renderMergeWorkspace();
                refreshGallery();
                alert('视频片段合并调速成功！');
            } else {
                appendSystemLog(`❌ 合并失败: ${data.message || 'FFmpeg 执行异常'}`, 'error');
                alert(`合并失败: ${data.message}`);
            }
        } catch (err) {
            appendSystemLog(`❌ 请求合并出错: ${err.message}`, 'error');
        } finally {
            dom.btnExecuteMerge.disabled = false;
        }
    });
}

// 刷新并拉取 manifests/media files
async function refreshGallery() {
    dom.galleryGrid.innerHTML = `
        <div style="grid-column: 1/-1; text-align:center; padding: 40px; color: var(--text-muted);">
            <span class="spinner" style="display:inline-block; margin-bottom: 12px;"></span>
            <p>正在扫描本地输出媒体库...</p>
        </div>
    `;

    const customDir = dom.galleryDirInput.value.trim();
    const queryParam = customDir ? `?output_dir=${encodeURIComponent(customDir)}` : '';
    
    try {
        const res = await fetch(`${API_BASE}/task_manifest${queryParam}`);
        if (!res.ok) throw new Error('Failed to get manifest');
        const data = await res.json();
        
        // 如果后端传回了 output_dir，前台反填展示
        if (data.output_dir && !customDir) {
            dom.galleryDirInput.value = data.output_dir;
        }

        renderGalleryGrid(data);
    } catch (e) {
        dom.galleryGrid.innerHTML = `
            <div style="grid-column: 1/-1; text-align:center; padding: 40px; color: var(--color-danger);">
                <span class="material-symbols-outlined" style="font-size: 40px;">error</span>
                <p>扫描输出文件夹失败，请检查路径配置 (${e.message})</p>
            </div>
        `;
    }
}

// 渲染媒体网格
function renderGalleryGrid(manifest) {
    const list = manifest.local_mp4_files || [];
    const outputDir = manifest.output_dir;
    
    if (list.length === 0) {
        dom.galleryGrid.innerHTML = `
            <div style="grid-column: 1/-1; text-align:center; padding: 40px; color: var(--text-muted);">
                <span class="material-symbols-outlined" style="font-size: 40px; margin-bottom: 8px;">folder_open</span>
                <p>输出目录下暂无生成的视频文件 (MP4)</p>
            </div>
        `;
        return;
    }

    dom.galleryGrid.innerHTML = '';
    list.forEach(absPath => {
        // 将绝对路径映射为 Web 的 /media 静态路由资源
        // 例如：absPath = /Users/fly/Desktop/N8N-main/AI_video/test.mp4, outputDir = /Users/fly/Desktop/N8N-main/AI_video
        // 我们需要截断并拼成 /media/test.mp4
        const relativePath = absPath.replace(outputDir, '').replace(/^[/\\]+/, '');
        const mediaUrl = `${API_BASE}/media/${relativePath.replace(/\\/g, '/')}`;
        const filename = relativePath.split(/[/\\]/).pop();

        const card = document.createElement('div');
        card.className = 'media-card';
        card.innerHTML = `
            <div class="media-preview-container">
                <video src="${mediaUrl}" preload="metadata" muted loop></video>
                <div class="media-overlay-actions">
                    <button class="btn-icon-action play-lightbox" title="全屏播放">
                        <span class="material-symbols-outlined">play_arrow</span>
                    </button>
                    <button class="btn-icon-action add-merge" title="添加到合并工坊">
                        <span class="material-symbols-outlined">add</span>
                    </button>
                </div>
            </div>
            <div class="media-info">
                <span class="media-title" title="${filename}">${filename}</span>
                <span class="media-meta">大小: ${(0.0000009536743 * 1024 /* 模拟 */).toFixed(2)} MB</span>
            </div>
        `;

        // 绑定悬停静音播放
        const video = card.querySelector('video');
        const container = card.querySelector('.media-preview-container');
        container.addEventListener('mouseenter', () => video.play().catch(() => {}));
        container.addEventListener('mouseleave', () => {
            video.pause();
            video.currentTime = 0;
        });

        // 绑定全屏播放模态框
        card.querySelector('.play-lightbox').addEventListener('click', (e) => {
            e.stopPropagation();
            openLightbox(filename, absPath, mediaUrl);
        });

        // 绑定加入合并队列
        card.querySelector('.add-merge').addEventListener('click', (e) => {
            e.stopPropagation();
            addVideoToMergeQueue(filename, absPath, mediaUrl);
        });

        dom.galleryGrid.appendChild(card);
    });
}

// 合并托盘逻辑
function addVideoToMergeQueue(name, path, url) {
    // 检查去重
    if (state.mergeQueue.some(item => item.path === path)) {
        alert('该视频片段已加入合并队列');
        return;
    }

    state.mergeQueue.push({
        id: 'mq-' + Math.random().toString(36).substr(2, 9),
        name,
        path,
        url
    });

    renderMergeWorkspace();
}

function renderMergeWorkspace() {
    const count = state.mergeQueue.length;
    dom.mergeCountBadge.textContent = `已选择 ${count} 个片段`;

    if (count === 0) {
        dom.mergeEmptyTip.style.display = 'block';
        dom.mergeSlotsList.style.display = 'none';
        dom.mergeControlsPanel.style.display = 'none';
        return;
    }

    dom.mergeEmptyTip.style.display = 'none';
    dom.mergeSlotsList.style.display = 'flex';
    dom.mergeControlsPanel.style.display = 'flex';
    
    dom.mergeSlotsList.innerHTML = '';
    state.mergeQueue.forEach((item, idx) => {
        const slot = document.createElement('div');
        slot.className = 'merge-slot-item';
        slot.innerHTML = `
            <video src="${item.url}" preload="metadata" muted></video>
            <span class="merge-slot-name" title="${item.name}">${item.name}</span>
            <button class="merge-item-remove" title="移出队列">
                <span class="material-symbols-outlined">close</span>
            </button>
            <div style="display:flex; justify-content: space-between; margin-top:4px;">
                <button type="button" class="btn-move-left" style="background:none; border:none; color:var(--text-secondary); cursor:pointer;" title="左移">
                    <span class="material-symbols-outlined" style="font-size:16px;">arrow_back</span>
                </button>
                <button type="button" class="btn-move-right" style="background:none; border:none; color:var(--text-secondary); cursor:pointer;" title="右移">
                    <span class="material-symbols-outlined" style="font-size:16px;">arrow_forward</span>
                </button>
            </div>
        `;

        // 移除片段
        slot.querySelector('.merge-item-remove').addEventListener('click', () => {
            state.mergeQueue.splice(idx, 1);
            renderMergeWorkspace();
        });

        // 左右移动排序
        slot.querySelector('.btn-move-left').addEventListener('click', () => {
            if (idx > 0) {
                const temp = state.mergeQueue[idx];
                state.mergeQueue[idx] = state.mergeQueue[idx - 1];
                state.mergeQueue[idx - 1] = temp;
                renderMergeWorkspace();
            }
        });

        slot.querySelector('.btn-move-right').addEventListener('click', () => {
            if (idx < state.mergeQueue.length - 1) {
                const temp = state.mergeQueue[idx];
                state.mergeQueue[idx] = state.mergeQueue[idx + 1];
                state.mergeQueue[idx + 1] = temp;
                renderMergeWorkspace();
            }
        });

        dom.mergeSlotsList.appendChild(slot);
    });
}

// ==============================================================================
// 8. 实时控制台与日志流轮询
// ==============================================================================
function initTerminalHandlers() {
    dom.btnClearTerminal.addEventListener('click', () => {
        dom.terminalLogOutput.innerHTML = '<div class="log-line system">[SYSTEM] Terminal cleared.</div>';
    });
}

function startLogPolling() {
    // 每 2 秒轮询一次后端最新日志
    state.logPollingInterval = setInterval(async () => {
        try {
            const res = await fetch(`${API_BASE}/api/logs?lines=120`);
            if (!res.ok) return;
            const data = await res.json();
            const logs = data.logs || [];
            
            // 简单增量更新
            if (logs.length > 0) {
                renderLogs(logs);
            }
        } catch (e) {
            // 静默失败
        }
    }, 2000);
}

function renderLogs(logArray) {
    dom.terminalLogOutput.innerHTML = '';
    
    let lastPercent = 0;
    let lastTaskName = '无活动任务';
    
    logArray.forEach(line => {
        const div = document.createElement('div');
        div.className = 'log-line';
        
        // 日志色彩解析
        if (line.includes('❌') || line.includes('⚠️') || line.includes('failed') || line.includes('Error')) {
            div.classList.add('error');
        } else if (line.includes('✅') || line.includes('success') || line.includes('完成')) {
            div.classList.add('success');
        } else if (line.includes('📡') || line.includes('🚀') || line.includes('💡') || line.includes('⚙️')) {
            div.classList.add('system');
        }
        
        div.textContent = line;
        dom.terminalLogOutput.appendChild(div);
        
        // 从日志中解析生成百分比进度 (例如 "Veo 3.1 - Fast [===> ] 35%")
        // 匹配 "65%" 这样的字符串
        const progressMatch = line.match(/(\d+)\s*%/);
        if (progressMatch) {
            lastPercent = parseInt(progressMatch[1]);
        }
        
        // 从日志中解析当前任务名称
        if (line.includes('视频生成请求') || line.includes('批量图片生成')) {
            lastTaskName = line.split(':').slice(1).join(':').trim();
            if (lastTaskName.length > 50) lastTaskName = lastTaskName.slice(0, 50) + '...';
        }
    });

    // 自动滚动到终端底部
    dom.terminalLogOutput.scrollTop = dom.terminalLogOutput.scrollHeight;

    // 动态同步头部进度条与活动任务显示
    if (state.isGenerating || lastPercent > 0) {
        dom.progressTaskName.textContent = lastTaskName;
        dom.progressTaskPercent.textContent = `${lastPercent}%`;
        dom.progressBarFill.style.width = `${lastPercent}%`;
        
        if (lastPercent === 100) {
            setGeneratingState(false);
            dom.progressTaskName.textContent = '任务已完成';
            dom.progressBarFill.style.width = '100%';
        }
    } else {
        dom.progressTaskName.textContent = '没有进行中的任务';
        dom.progressTaskPercent.textContent = '0%';
        dom.progressBarFill.style.width = '0%';
    }
}

function appendSystemLog(message, type = '') {
    const div = document.createElement('div');
    div.className = 'log-line';
    if (type === 'system') div.classList.add('system');
    if (type === 'success') div.classList.add('success');
    if (type === 'error') div.classList.add('error');
    
    const timeStr = new Date().toLocaleTimeString();
    div.textContent = `[${timeStr}] ${message}`;
    
    dom.terminalLogOutput.appendChild(div);
    dom.terminalLogOutput.scrollTop = dom.terminalLogOutput.scrollHeight;
}

// ==============================================================================
// 9. 全屏灯箱播放器 Lightbox
// ==============================================================================
function initLightboxHandlers() {
    dom.btnCloseLightbox.addEventListener('click', () => closeLightbox());
    dom.videoLightbox.addEventListener('click', (e) => {
        if (e.target === dom.videoLightbox) closeLightbox();
    });
}

function openLightbox(title, path, url) {
    dom.lightboxVideoPlayer.src = url;
    dom.lightboxVideoTitle.textContent = title;
    dom.lightboxVideoPath.textContent = path;
    dom.btnLightboxDownload.href = url;
    
    dom.videoLightbox.style.display = 'flex';
    dom.lightboxVideoPlayer.play();
}

function closeLightbox() {
    dom.videoLightbox.style.display = 'none';
    dom.lightboxVideoPlayer.pause();
    dom.lightboxVideoPlayer.src = '';
}

// ==============================================================================
// 📖 故事脚本流自动化管线 (Orchestrator Pipeline)
// ==============================================================================

function initScriptFlowHandlers() {
    if (!dom.scriptForm) return;

    // 载入测试范例按钮事件
    dom.btnLoadScriptDemo.addEventListener('click', () => {
        dom.scriptFlowInput.value = `图片提示词
图片 1
一只非常可爱的橙色小猫咪在绿油油的草地上奔跑，阳光明媚，微距摄影
图片 2
橙色小猫咪抓到了一个红色的小皮球，开心地在草地上打滚
图片 3
橙色小猫咪抱着红色皮球，在温暖的阳光下静静地睡着了，特写

视频提示词
视频 1
橙色小猫咪在草地上奔跑，风吹拂草地，镜头平移
视频 2
橙色小猫咪趴在皮球旁边，好奇地用爪子拨动皮球`;
        appendSystemLog('📝 已自动载入故事脚本测试范例', 'system');
    });

    // 表单提交生成管线
    dom.scriptForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (state.isGenerating) return;

        const scriptText = dom.scriptFlowInput.value.trim();
        if (!scriptText) {
            alert('请先输入或载入故事脚本！');
            return;
        }

        // 1. 解析脚本
        const { images, videos } = parseStoryScript(scriptText);
        if (images.length === 0 && videos.length === 0) {
            alert('未能从脚本中解析出任何有效的图片或视频提示词！请检查格式。');
            return;
        }

        // 2. 收集参数配置
        const params = {
            projectName: dom.scriptProjectName.value.trim(),
            outputPath: dom.scriptOutputPath.value.trim() || dom.galleryDirInput.value.trim(),
            speed: parseFloat(dom.scriptMergeSpeed.value) || 2.0,
            imageModel: dom.scriptImageModel.value,
            videoModel: dom.scriptVideoModel.value,
            ratio: dom.scriptVideoRatio.value,
            videoDuration: dom.scriptVideoDuration.value.replace('s', '') // '8s' -> '8'
        };

        // 显示管线进度面板，隐藏上次的结果
        dom.pipelineStatusPanel.style.display = 'block';
        dom.pipelineResultBox.style.display = 'none';

        // 3. 初始化骨架
        renderPipelineSkeleton(images, videos);

        // 4. 锁定状态启动管线
        setGeneratingState(true, '故事脚本流自动合成中...');

        try {
            await runScriptFlowPipeline(images, videos, params);
        } catch (err) {
            appendSystemLog(`❌ 故事脚本流运行异常终止: ${err.message}`, 'error');
            alert(`故事脚本流生成失败: ${err.message}`);
        } finally {
            setGeneratingState(false);
        }
    });
}

/**
 * 脚本解析器 (Script Parser)
 * 提取图片提示词区与视频提示词区的各个带标号的提示词
 */
function parseStoryScript(text) {
    const lines = text.split('\n').map(l => l.trim());
    const images = [];
    const videos = [];
    
    let currentSection = null; // 'images' | 'videos'
    let currentPromptText = '';
    
    function commitCurrentPrompt() {
        if (currentPromptText) {
            if (currentSection === 'images') {
                images.push(currentPromptText);
            } else if (currentSection === 'videos') {
                videos.push(currentPromptText);
            }
            currentPromptText = '';
        }
    }
    
    for (let line of lines) {
        if (!line) continue;
        
        // 区域切换
        if (line.includes('图片提示词') || line.toLowerCase().includes('image prompt')) {
            commitCurrentPrompt();
            currentSection = 'images';
            continue;
        }
        if (line.includes('视频提示词') || line.toLowerCase().includes('video prompt')) {
            commitCurrentPrompt();
            currentSection = 'videos';
            continue;
        }
        
        // 标签匹配 (如 "图片 1"、"image 1"、"视频 1" 等)
        const isImageTag = /^图片\s*\d+|image\s*\d+/i.test(line);
        const isVideoTag = /^视频\s*\d+|video\s*\d+/i.test(line);
        
        if (isImageTag) {
            commitCurrentPrompt();
            currentSection = 'images';
            continue;
        }
        if (isVideoTag) {
            commitCurrentPrompt();
            currentSection = 'videos';
            continue;
        }
        
        // 追加正文
        if (currentSection) {
            if (currentPromptText) {
                currentPromptText += ' ' + line;
            } else {
                currentPromptText = line;
            }
        }
    }
    commitCurrentPrompt();
    
    return { images, videos };
}

/**
 * 渲染管线骨架 (列表占位符初始化)
 */
function renderPipelineSkeleton(images, videos) {
    dom.pipelineStepText.textContent = '初始化生成管线...';
    dom.pipelinePercentText.textContent = '0%';
    dom.pipelineProgressBar.style.width = '0%';

    // 图片列表
    dom.pipelineImagesList.innerHTML = '';
    if (images.length === 0) {
        dom.pipelineImagesList.innerHTML = '<div style="color:var(--text-muted); text-align:center; padding:12px;">无图片提示词</div>';
    } else {
        images.forEach((prompt, idx) => {
            const item = document.createElement('div');
            item.className = 'pipeline-step-item pending';
            item.id = `step-image-${idx}`;
            item.innerHTML = `
                <div class="step-status-icon pending">
                    <span class="material-symbols-outlined">hourglass_empty</span>
                </div>
                <div class="step-details">
                    <span class="step-prompt" title="${prompt}">图片 ${idx + 1}: ${prompt}</span>
                    <span class="step-subtext">等待执行...</span>
                </div>
            `;
            dom.pipelineImagesList.appendChild(item);
        });
    }

    // 视频列表
    dom.pipelineVideosList.innerHTML = '';
    if (videos.length === 0) {
        dom.pipelineVideosList.innerHTML = '<div style="color:var(--text-muted); text-align:center; padding:12px;">无视频提示词</div>';
    } else {
        videos.forEach((prompt, idx) => {
            const item = document.createElement('div');
            item.className = 'pipeline-step-item pending';
            item.id = `step-video-${idx}`;
            item.innerHTML = `
                <div class="step-status-icon pending">
                    <span class="material-symbols-outlined">hourglass_empty</span>
                </div>
                <div class="step-details">
                    <span class="step-prompt" title="${prompt}">视频 ${idx + 1}: ${prompt}</span>
                    <span class="step-subtext">等待执行...</span>
                </div>
            `;
            dom.pipelineVideosList.appendChild(item);
        });
    }
}

/**
 * 更新步骤执行状态与媒体缩略图预览
 */
function updateStepStatus(type, idx, status, subtext, resultPath = '') {
    const item = document.getElementById(`step-${type}-${idx}`);
    if (!item) return;

    item.classList.remove('pending', 'running', 'completed', 'failed');
    
    // completed 与 success 保持一致
    const resolvedStatus = (status === 'success' ? 'completed' : status);
    item.classList.add(resolvedStatus);

    const iconEl = item.querySelector('.step-status-icon');
    const subtextEl = item.querySelector('.step-subtext');

    if (iconEl) {
        iconEl.className = `step-status-icon ${resolvedStatus}`;
        if (resolvedStatus === 'running') {
            iconEl.innerHTML = `<span class="material-symbols-outlined">sync</span>`;
        } else if (resolvedStatus === 'completed') {
            iconEl.innerHTML = `<span class="material-symbols-outlined">check_circle</span>`;
        } else if (resolvedStatus === 'failed') {
            iconEl.innerHTML = `<span class="material-symbols-outlined">error</span>`;
        } else {
            iconEl.innerHTML = `<span class="material-symbols-outlined">hourglass_empty</span>`;
        }
    }

    if (subtextEl) {
        subtextEl.textContent = subtext;
    }

    // 若生成成功且附带本地绝对路径，则渲染预览卡片
    if (resolvedStatus === 'completed' && resultPath) {
        if (!item.querySelector('.step-thumbnail')) {
            const mediaUrl = getMediaUrl(resultPath);
            if (type === 'image') {
                const img = document.createElement('img');
                img.className = 'step-thumbnail';
                img.src = mediaUrl;
                img.alt = `图片 ${idx + 1} 预览`;
                img.style.cursor = 'pointer';
                img.addEventListener('click', () => {
                    openLightbox(`图片 ${idx + 1}`, resultPath, mediaUrl);
                });
                item.appendChild(img);
            } else if (type === 'video') {
                const vid = document.createElement('video');
                vid.className = 'step-thumbnail';
                vid.src = mediaUrl;
                vid.muted = true;
                vid.playsInline = true;
                vid.style.cursor = 'pointer';
                vid.addEventListener('mouseenter', () => vid.play().catch(() => {}));
                vid.addEventListener('mouseleave', () => { vid.pause(); vid.currentTime = 0; });
                vid.addEventListener('click', () => {
                    openLightbox(`视频 ${idx + 1}`, resultPath, mediaUrl);
                });
                item.appendChild(vid);
            }
        }
    }
}

/**
 * 更新管线头部大进度条
 */
function updatePipelineProgress(stepText, percent) {
    if (dom.pipelineStepText) dom.pipelineStepText.textContent = stepText;
    if (dom.pipelinePercentText) dom.pipelinePercentText.textContent = `${percent}%`;
    if (dom.pipelineProgressBar) dom.pipelineProgressBar.style.width = `${percent}%`;
}

/**
 * 更新视频合并状态与最终成片播放器绑定
 */
function updateMergeStatus(status, text, resultPath = '') {
    if (status === 'running') {
        updatePipelineProgress(text, 95);
    } else if (status === 'success') {
        updatePipelineProgress(text, 100);
        
        dom.pipelineResultBox.style.display = 'flex';
        const filename = resultPath.split(/[/\\]/).pop();
        dom.pipelineResultFilename.textContent = `输出故事成片：${filename}`;
        
        const mediaUrl = getMediaUrl(resultPath);
        
        // 重新绑定播放与下载链接 (克隆节点清空历史 listener)
        const newPlayBtn = dom.btnPlayPipelineResult.cloneNode(true);
        dom.btnPlayPipelineResult.parentNode.replaceChild(newPlayBtn, dom.btnPlayPipelineResult);
        dom.btnPlayPipelineResult = newPlayBtn;
        
        dom.btnPlayPipelineResult.addEventListener('click', () => {
            openLightbox(filename, resultPath, mediaUrl);
        });
        
        dom.btnDownloadPipelineResult.href = mediaUrl;
        dom.btnDownloadPipelineResult.download = filename;
    } else if (status === 'failed') {
        updatePipelineProgress(text, 90);
    }
}

/**
 * 根据本地绝对路径映射静态 media 服务可访问直链
 */
function getMediaUrl(absPath) {
    if (!absPath) return '';
    if (absPath.startsWith('http')) return absPath;
    
    // 临时上传的文件路由
    if (absPath.includes('temp_uploads')) {
        const filename = absPath.split(/[/\\]/).pop();
        return `/media/temp_uploads/${filename}`;
    }
    
    const baseDir = dom.galleryDirInput.value.trim();
    if (baseDir) {
        const relativePath = absPath.replace(baseDir, '').replace(/^[/\\]+/, '');
        return `/media/${relativePath.replace(/\\/g, '/')}`;
    }
    
    const filename = absPath.split(/[/\\]/).pop();
    return `/media/${filename}`;
}

/**
 * 核心管线执行器
 * 1. Chained Image Gen (链式绘图，图片 N 参考图片 N-1)
 * 2. Chained Video Gen (首尾双帧视频并发生成，视频 N 参考图片 N + 图片 N-1)
 * 3. FFmpeg Merging (合并与调速)
 */
async function runScriptFlowPipeline(imagePrompts, videoPrompts, params) {
    // 总步骤 = 图片数 + 视频并发(1步) + 合并(1步)
    const totalSteps = imagePrompts.length + (videoPrompts.length > 0 ? 1 : 0) + 1;
    let currentStepIndex = 0;

    // ── 步骤 1. 链式图片绘制 ──
    const generatedImages = [];
    if (imagePrompts.length > 0) {
        for (let i = 0; i < imagePrompts.length; i++) {
            currentStepIndex++;
            const percent = Math.round(((currentStepIndex - 1) / totalSteps) * 100);
            updatePipelineProgress(`正在绘制图片 ${i + 1}/${imagePrompts.length}...`, percent);
            updateStepStatus('image', i, 'running', '正在生成图片...');

            const refImages = i > 0 ? [generatedImages[i - 1]] : [];
            const payload = {
                prompts: [imagePrompts[i]],
                images: refImages,
                ratio: params.ratio,
                model: params.imageModel,
                output_path: params.outputPath
            };

            appendSystemLog(`[故事脚本流] 开始绘制图片 ${i + 1}/${imagePrompts.length}: "${imagePrompts[i]}"`, 'system');
            
            try {
                const res = await fetch(`${API_BASE}/generate_images_batch`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (res.ok && data.status === 'success' && data.image_urls && data.image_urls.length > 0) {
                    const imgPath = data.image_urls[0];
                    generatedImages.push(imgPath);
                    updateStepStatus('image', i, 'success', '生成成功', imgPath);
                    appendSystemLog(`[故事脚本流] 图片 ${i + 1} 绘制完成: ${imgPath}`, 'success');
                } else {
                    throw new Error(data.detail || data.message || '返回错误状态');
                }
            } catch (err) {
                updateStepStatus('image', i, 'failed', `生成失败: ${err.message}`);
                appendSystemLog(`[故事脚本流] 图片 ${i + 1} 绘制失败: ${err.message}`, 'error');
                throw err;
            }
        }
    }

    // ── 步骤 2. 首尾帧视频并发生成 ──
    let successVideoPaths = [];
    if (videoPrompts.length > 0) {
        currentStepIndex++;
        const percent = Math.round(((currentStepIndex - 1) / totalSteps) * 100);
        updatePipelineProgress(`正在并发生成视频片段 (共 ${videoPrompts.length} 个)...`, percent);

        const videoItems = [];
        for (let i = 0; i < videoPrompts.length; i++) {
            updateStepStatus('video', i, 'running', '正在生成视频...');
            // 视频 i 的首尾帧对应关系：首帧为图片 i，尾帧为图片 i+1
            const startFrame = generatedImages[i] || '';
            const endFrame = generatedImages[i + 1] || '';
            videoItems.push({
                prompt: videoPrompts[i],
                image: startFrame,
                end_image: endFrame,
                ratio: params.ratio,
                model: params.videoModel,
                duration: params.videoDuration,
                output_path: params.outputPath
            });
        }

        const payload = {
            items: videoItems,
            ratio: params.ratio,
            model: params.videoModel,
            duration: params.videoDuration,
            output_path: params.outputPath,
            concurrent: true,
            max_concurrent: 3
        };

        appendSystemLog(`[故事脚本流] 开始批量提交生成 ${videoPrompts.length} 个视频片段...`, 'system');

        try {
            const res = await fetch(`${API_BASE}/generate_videos_batch`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (res.ok && data.status === 'success' && data.video_urls) {
                const generatedVideos = data.video_urls;
                for (let i = 0; i < videoPrompts.length; i++) {
                    const vidPath = generatedVideos[i];
                    if (vidPath) {
                        successVideoPaths.push(vidPath);
                        updateStepStatus('video', i, 'success', '生成成功', vidPath);
                        appendSystemLog(`[故事脚本流] 视频片段 ${i + 1} 生成完成: ${vidPath}`, 'success');
                    } else {
                        updateStepStatus('video', i, 'failed', '生成失败');
                        appendSystemLog(`[故事脚本流] 视频片段 ${i + 1} 生成失败`, 'error');
                    }
                }
                if (successVideoPaths.length === 0) {
                    throw new Error('所有视频片段生成均失败');
                }
            } else {
                throw new Error(data.detail || data.message || '生成请求失败');
            }
        } catch (err) {
            for (let i = 0; i < videoPrompts.length; i++) {
                updateStepStatus('video', i, 'failed', `失败: ${err.message}`);
            }
            appendSystemLog(`[故事脚本流] 视频生成阶段异常: ${err.message}`, 'error');
            throw err;
        }
    }

    // ── 步骤 3. FFmpeg 视频合并与调速 ──
    if (successVideoPaths.length > 0) {
        currentStepIndex++;
        const percent = Math.round(((currentStepIndex - 1) / totalSteps) * 100);
        updatePipelineProgress('正在使用 FFmpeg 合并并重新编码所有视频片段...', percent);
        updateMergeStatus('running', '正在合并视频并重新编码...');

        const mergePayload = {
            video_paths: successVideoPaths,
            output_filename: params.projectName ? `${params.projectName}_merged.mp4` : 'script_flow_merged.mp4',
            output_dir: params.outputPath,
            speed: params.speed
        };

        appendSystemLog(`[故事脚本流] 正在执行 FFmpeg 重新编码与调速合并: 片段数=${successVideoPaths.length}, 速度=${params.speed}x`, 'system');

        try {
            const res = await fetch(`${API_BASE}/merge_videos`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(mergePayload)
            });
            const data = await res.json();
            if (res.ok && data.status === 'success' && data.output_path) {
                updateMergeStatus('success', '故事脚本视频生成并合并完成！', data.output_path);
                appendSystemLog(`[故事脚本流] 故事生成全部完成！最终文件：${data.output_path}`, 'success');
            } else {
                throw new Error(data.message || 'FFmpeg 合并处理异常');
            }
        } catch (err) {
            updateMergeStatus('failed', `最终合并失败: ${err.message}`);
            appendSystemLog(`[故事脚本流] 视频合并失败: ${err.message}`, 'error');
            throw err;
        }
    } else {
        throw new Error('未成功生成任何视频片段，跳过合并步骤');
    }
}
