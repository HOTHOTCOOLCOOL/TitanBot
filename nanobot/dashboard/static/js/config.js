let currentConfig = null;
let currentVersionHash = null;
let capabilitiesData = [];
let currentToolSelection = 'exec'; // default tool

async function fetchConfiguration() {
    try {
        const [configRes, capRes] = await Promise.all([
            fetch('/api/config', { headers: authHeaders() }),
            fetch('/api/capabilities', { headers: authHeaders() })
        ]);

        if (configRes.ok) {
            const data = await configRes.json();
            currentConfig = data.config;
            currentVersionHash = data.version_hash;
            document.getElementById('config-editor').value = JSON.stringify(currentConfig, null, 2);
        }

        if (capRes.ok) {
            const capData = await capRes.json();
            capabilitiesData = capData.capabilities;
        }
        
        renderCapabilityChecklist();

    } catch (e) {
        showToast('❌ Failed to load config');
        console.error(e);
    }
}

function toggleConfigMode(mode) {
    const rawBtn = document.getElementById('btn-raw-mode');
    const visualBtn = document.getElementById('btn-visual-mode');
    const rawEd = document.getElementById('config-raw-editor');
    const visualEd = document.getElementById('config-visual-editor');

    if (mode === 'raw') {
        rawBtn.style.background = 'var(--accent-hover)';
        visualBtn.style.background = 'var(--card-bg)';
        rawBtn.style.color = 'white';
        visualBtn.style.color = 'var(--text-color)';
        visualBtn.style.border = '1px solid var(--border-color)';
        rawBtn.style.border = 'none';
        
        rawEd.style.display = 'flex';
        visualEd.style.display = 'none';
        
        // Sync visual to raw
        document.getElementById('config-editor').value = JSON.stringify(currentConfig, null, 2);
    } else {
        visualBtn.style.background = 'var(--accent-hover)';
        rawBtn.style.background = 'var(--card-bg)';
        visualBtn.style.color = 'white';
        rawBtn.style.color = 'var(--text-color)';
        rawBtn.style.border = '1px solid var(--border-color)';
        visualBtn.style.border = 'none';
        
        visualEd.style.display = 'block';
        rawEd.style.display = 'none';
        
        // Sync raw back to visual
        try {
            currentConfig = JSON.parse(document.getElementById('config-editor').value);
            renderCapabilityChecklist();
        } catch (e) {
            showToast('⚠️ Raw JSON is invalid, visual editor might be out of sync');
        }
    }
}

function getCapabilityMask(toolName) {
    if (!currentConfig || !currentConfig.agents || !currentConfig.agents.sandbox || !currentConfig.agents.sandbox.capability_overrides) {
        return 0;
    }
    return currentConfig.agents.sandbox.capability_overrides[toolName] || 0;
}

function setCapabilityMask(toolName, maskValue) {
    if (!currentConfig) return;
    if (!currentConfig.agents) currentConfig.agents = {};
    if (!currentConfig.agents.sandbox) currentConfig.agents.sandbox = {};
    if (!currentConfig.agents.sandbox.capability_overrides) currentConfig.agents.sandbox.capability_overrides = {};
    
    currentConfig.agents.sandbox.capability_overrides[toolName] = maskValue;
    // Keep raw editor updated
    document.getElementById('config-editor').value = JSON.stringify(currentConfig, null, 2);
}

function renderCapabilityChecklist() {
    const container = document.getElementById('capability-checklist');
    if (!container || capabilitiesData.length === 0) return;

    const KNOWN_TOOLS = ['exec', 'web_search', 'web_fetch', 'mcp_servers', 'run_python'];
    let existingTools = Object.keys(getCapabilityOverrides());
    let toolKeys = Array.from(new Set([...KNOWN_TOOLS, ...existingTools])).sort();

    let selectorHtml = `<div style="margin-bottom: 15px;">
        <label>Select Tool (Sandbox Constraint Scope): </label>
        <select id="config-tool-selector" onchange="currentToolSelection = this.value; renderCapabilityChecklist()" style="background:var(--bg-color); color:white; border: 1px solid var(--border-color); padding: 6px; border-radius: 4px; min-width: 200px; margin-left: 10px;">
            ${toolKeys.map(t => `<option value="${t}" ${t === currentToolSelection ? 'selected' : ''}>${t}</option>`).join('')}
        </select>
    </div>`;

    let tipsHtml = `<div style="margin-bottom: 15px;">
        <details style="background: rgba(255, 255, 255, 0.05); border: 1px dashed #64748b; border-radius: 6px; padding: 10px;">
            <summary style="cursor: pointer; font-weight: bold; color: #60a5fa;">💡 Sandbox Configuration Tips (Click to expand)</summary>
            <div style="margin-top: 12px; font-size: 0.85rem; color: #cbd5e1; line-height: 1.5;">
                <p style="color: #93c5fd; margin-bottom: 4px;"><b>What happens when I check a box?</b></p>
                <p style="margin-bottom: 10px;">By default, Nanobot uses smart analysis (e.g., \`exec\` freely runs \`ls\`, but triggers Human-in-the-Loop review for \`rm -rf\`). When you check a box below, you <b>hardcode</b> the tool's override mask, fully replacing the smart defaults.</p>
                <p style="color: #93c5fd; margin-bottom: 4px;"><b>Example: Configuring 'exec'</b></p>
                <ul style="margin-left: 20px; list-style-type: disc;">
                    <li><b>Safest:</b> Click "Remove Override". Let the system dynamically catch dangerous commands.</li>
                    <li><b>Custom Override:</b> Check ☑️ <b>Shell Execution</b> & ☑️ <b>State Mutation</b>.</li>
                    <li><span style="color: #f87171;"><b>DANGER:</b></span> Do <b>NOT</b> check 🚫 <i>Destructive Operation</i> or 🚫 <i>Untrusted External</i>. If checked, the agent can delete files permanently without ever asking for your permission!</li>
                </ul>
            </div>
        </details>
    </div>`;

    const isOverridden = typeof getCapabilityOverrides()[currentToolSelection] !== 'undefined';
    let currentMask = getCapabilityMask(currentToolSelection);
    
    let html = selectorHtml + tipsHtml;

    if (!isOverridden) {
        html += `<div style="background: rgba(59, 130, 246, 0.1); border-left: 3px solid #3b82f6; padding: 10px; margin-bottom: 15px; font-size: 0.85rem;">
            ℹ️ <b>Default Behavior:</b> This tool currently uses its intrinsic system defaults. Selecting any capability below will force an explicit override for this tool.
        </div>`;
    }
    
    capabilitiesData.forEach(cap => {
        const isChecked = (currentMask & cap.value) === cap.value;
        const color = cap.risk === 'high' ? 'var(--danger)' : (cap.risk === 'medium' ? 'var(--warning)' : 'var(--success)');
        const riskIcon = cap.risk === 'high' ? '🔴 High Risk! ⚠' : (cap.risk === 'medium' ? '🟡 Med' : '🟢 Low');
        
        // Use backend provided title/desc, or fallback if backend hasn't been restarted yet
        let title = cap.title;
        let desc = cap.desc;
        if (!title || !desc) {
            const fallbacks = {
                'DATA_READ': ['Data Read', 'Allow reading local data and workspace files'],
                'DATA_WRITE': ['Data Write', 'Allow creating or modifying local files'],
                'INFO_RETRIEVAL': ['Info Retrieval', 'Allow fetching data from external APIs or resources'],
                'SYS_COMMUNICATION': ['System Communication', 'Allow sending outbound notifications to humans (e.g., email)'],
                'SHELL_EXECUTION': ['Shell Execution', 'Allow executing shell scripts or OS terminal commands'],
                'CODE_EVALUATION': ['Code Evaluation', 'Allow compiling and executing arbitrary code dynamically (e.g., Python)'],
                'MUTATIVE': ['State Mutation', 'Allow state-changing side effects that persist in the system'],
                'DESTRUCTIVE': ['Destructive Operation', 'Allow data deletion or formatting operations (Extremely dangerous)'],
                'UNTRUSTED_EXTERNAL': ['Untrusted External', 'Tool originates from unverified third parties (e.g., external MCP servers)']
            };
            title = (fallbacks[cap.name] || [])[0] || cap.name;
            desc = (fallbacks[cap.name] || [])[1] || '';
        }

        html += `<div style="display:flex; align-items:flex-start; gap:10px; margin-bottom: 10px; padding: 10px; border: 1px solid var(--border-color); border-radius: 6px; background: rgba(0,0,0,0.2);">
            <input style="margin-top:5px; transform: scale(1.2);" type="checkbox" onchange="handleCapChange(${cap.value}, this.checked, '${title}', '${cap.risk}')" ${isChecked ? 'checked' : ''}>
            <div style="flex:1;">
                <div style="font-weight:bold;">${title} <span style="color:${color}; font-size:0.75rem; margin-left: 8px;">${riskIcon}</span></div>
                <div style="font-size:0.85rem; color: #94a3b8; margin-top:4px;">${desc}</div>
                <div style="font-size:0.7rem; color: #64748b; margin-top:4px; font-family:monospace;">System Tag: ${cap.name}</div>
            </div>
        </div>`;
    });

    let displayRisk = "🟢 Low Risk (No HITL)";
    if (capabilitiesData.some(cap => (currentMask & cap.value) === cap.value && cap.risk === 'high')) {
        displayRisk = "🔴 HIGH RISK (HITL Hard Stop)";
    } else if (capabilitiesData.some(cap => (currentMask & cap.value) === cap.value && cap.risk === 'medium')) {
        displayRisk = "🟡 Medium Risk (Monitored)";
    }

    if (isOverridden) {
        html += `<div style="margin-top:15px; padding: 10px; border-radius: 4px; background: var(--bg-color); border: 1px dashed var(--border-color); font-size:0.9rem;">
            Resolved Security Classification: <b>${displayRisk}</b>
            <button onclick="clearCustomOverride()" style="margin-left: 15px; background: none; border: none; color: #ef4444; cursor: pointer; text-decoration: underline; font-size: 0.8rem;">Remove Override (Restore Default)</button>
        </div>`;
    }

    container.innerHTML = html;
}

window.clearCustomOverride = function() {
    if (!currentConfig || !currentConfig.agents || !currentConfig.agents.sandbox || !currentConfig.agents.sandbox.capability_overrides) return;
    delete currentConfig.agents.sandbox.capability_overrides[currentToolSelection];
    document.getElementById('config-editor').value = JSON.stringify(currentConfig, null, 2);
    renderCapabilityChecklist();
}

function getCapabilityOverrides() {
    return (currentConfig && currentConfig.agents && currentConfig.agents.sandbox && currentConfig.agents.sandbox.capability_overrides) || {};
}

window.handleCapChange = function(capValue, isChecked, capName, capRisk) {
    let currentMask = getCapabilityMask(currentToolSelection);

    if (isChecked && capRisk === 'high') {
        const confirmMsg = `WARNING: Enabling ${capName} is a HIGH RISK operation!\n\nAre you absolutely sure you want to grant this capability to the sandbox?`;
        if (!confirm(confirmMsg)) {
            // Re-render to revert checkbox
            renderCapabilityChecklist();
            return;
        }
    }

    if (isChecked) {
        currentMask |= capValue;
    } else {
        currentMask &= ~capValue;
    }

    setCapabilityMask(currentToolSelection, currentMask);
    renderCapabilityChecklist();
}

window.saveConfiguration = async function() {
    let payloadConfig = currentConfig;

    // Flush any raw changes
    const rawEd = document.getElementById('config-raw-editor');
    if (rawEd.style.display !== 'none') {
        try {
            payloadConfig = JSON.parse(document.getElementById('config-editor').value);
        } catch (e) {
            showToast('❌ Invalid JSON formatting in Raw Editor!');
            return;
        }
    }

    try {
        const res = await fetch('/api/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', ...authHeaders()},
            body: JSON.stringify({
                config: payloadConfig,
                version_hash: currentVersionHash
            })
        });

        if (res.ok) {
            showToast('✅ Configuration saved & backed up!');
            document.getElementById('config-banner').style.display = 'block';
            await fetchConfiguration(); // reload new hash
        } else if (res.status === 409) {
            showToast('❌ Save failed: Config modified externally (Optimistic Lock). Please refresh page to sync.');
            // explicitly NOT calling fetchConfiguration() to avoid wiping user edits and bypassing the lock
        } else {
            const err = await res.json();
            showToast('❌ Error: ' + (err.detail || 'check logs'));
        }
    } catch (e) {
        showToast('❌ Error saving configuration');
        console.error(e);
    }
}
